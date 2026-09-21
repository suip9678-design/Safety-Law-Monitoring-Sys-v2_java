import datetime

from sqlalchemy import (
    Boolean,
    and_,
    not_,
    or_,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.ext.hybrid import hybrid_property
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base

# 검토 상태값
REVIEW_STATUSES = ["미검토", "검토중", "반영완료", "해당없음"]

# 추적 대상 구분 (법령 vs 행정규칙(고시/예규/훈령 등))
SOURCE_TYPES = ["law", "admrul"]

DOC_TYPES = ["절차서", "지침서", "작업표준", "기타"]


# 중대재해 뉴스 피드에서 "실제 사망사고"로 볼 제목 키워드.
# ponytail: 제목 문자열 매칭이라 "사망자 감소" 같은 통계 기사나 "추락사고"(사망 아님)도 걸린다 - 필요하면 제외어를 추가.
FATAL_KEYWORDS = ("사망", "숨져", "숨진", "숨졌", "참변", "참사", "유족", "추락사", "끼임사", "목숨", "압사", "질식사", "익사")


def now() -> datetime.datetime:
    return datetime.datetime.utcnow()


class TrackedLaw(Base):
    __tablename__ = "tracked_laws"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source_type: Mapped[str] = mapped_column(String(16))  # "law" | "admrul"
    external_id: Mapped[str] = mapped_column(String(64))  # 법령일련번호(MST) - 특정 공포 버전을 가리킴, 개정되면 값이 바뀜
    master_id: Mapped[str | None] = mapped_column(String(64), nullable=True)  # 법령ID/행정규칙ID - 버전이 바뀌어도 고정되는 영구 식별자
    name: Mapped[str] = mapped_column(String(255))
    category: Mapped[str | None] = mapped_column(String(64), nullable=True)  # 법률/시행령/시행규칙/고시/예규/훈령 등
    department: Mapped[str | None] = mapped_column(String(128), nullable=True)

    current_promulgation_no: Mapped[str | None] = mapped_column(String(64), nullable=True)
    current_promulgation_date: Mapped[str | None] = mapped_column(String(16), nullable=True)
    current_enforcement_date: Mapped[str | None] = mapped_column(String(16), nullable=True)
    detail_link: Mapped[str | None] = mapped_column(String(512), nullable=True)

    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    last_synced_at: Mapped[datetime.datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=now)
    updated_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=now, onupdate=now)

    revisions: Mapped[list["LawRevision"]] = relationship(
        back_populates="tracked_law", cascade="all, delete-orphan", order_by="desc(LawRevision.detected_at)"
    )
    mappings: Mapped[list["DocumentLawMapping"]] = relationship(
        back_populates="tracked_law", cascade="all, delete-orphan"
    )

    __table_args__ = (UniqueConstraint("source_type", "external_id", name="uq_tracked_law_source_external"),)


class LawRevision(Base):
    __tablename__ = "law_revisions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tracked_law_id: Mapped[int] = mapped_column(ForeignKey("tracked_laws.id"))

    promulgation_no: Mapped[str | None] = mapped_column(String(64), nullable=True)
    promulgation_date: Mapped[str | None] = mapped_column(String(16), nullable=True)
    enforcement_date: Mapped[str | None] = mapped_column(String(16), nullable=True)

    previous_promulgation_no: Mapped[str | None] = mapped_column(String(64), nullable=True)
    previous_promulgation_date: Mapped[str | None] = mapped_column(String(16), nullable=True)
    previous_enforcement_date: Mapped[str | None] = mapped_column(String(16), nullable=True)

    detected_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=now)
    review_status: Mapped[str] = mapped_column(String(16), default="미검토")
    reviewer: Mapped[str | None] = mapped_column(String(64), nullable=True)
    reviewed_at: Mapped[datetime.datetime | None] = mapped_column(DateTime, nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    raw_data: Mapped[str | None] = mapped_column(Text, nullable=True)

    tracked_law: Mapped["TrackedLaw"] = relationship(back_populates="revisions")


class CompanyDocument(Base):
    __tablename__ = "company_documents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    doc_type: Mapped[str] = mapped_column(String(16), default="절차서")
    doc_number: Mapped[str | None] = mapped_column(String(64), nullable=True)
    title: Mapped[str] = mapped_column(String(255))
    revision_no: Mapped[str | None] = mapped_column(String(32), nullable=True)
    revision_date: Mapped[str | None] = mapped_column(String(16), nullable=True)
    owner: Mapped[str | None] = mapped_column(String(64), nullable=True)
    file_link: Mapped[str | None] = mapped_column(String(512), nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    # 쉼표로 구분된 키워드(해시태그) 목록, "#" 없이 저장(예: "밀폐공간,공기호흡기").
    # 명시적으로 매핑해두지 않은 법령이라도, 이 키워드가 법령명이나 본문
    # 캐시(ScrapedLawContent)에 포함되어 있으면 그 개정을 이 문서의 개정
    # 필요 사항 목록에 자동으로 띄우기 위해 사용한다.
    tags: Mapped[str | None] = mapped_column(String(512), nullable=True)

    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=now)
    updated_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=now, onupdate=now)

    mappings: Mapped[list["DocumentLawMapping"]] = relationship(
        back_populates="document", cascade="all, delete-orphan"
    )


class DocumentLawMapping(Base):
    __tablename__ = "document_law_mappings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    document_id: Mapped[int] = mapped_column(ForeignKey("company_documents.id"))
    tracked_law_id: Mapped[int] = mapped_column(ForeignKey("tracked_laws.id"))
    note: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=now)

    document: Mapped["CompanyDocument"] = relationship(back_populates="mappings")
    tracked_law: Mapped["TrackedLaw"] = relationship(back_populates="mappings")

    __table_args__ = (UniqueConstraint("document_id", "tracked_law_id", name="uq_mapping_doc_law"),)


class NewAdmrulCandidate(Base):
    """아직 등록하지 않은, 새로 제정된 것으로 보이는 고시/예규/훈령 후보.

    등록해둔 고시가 "개정"되는 게 아니라 매년 새로 "제정"되는 경우가 많아서,
    TrackedLaw의 "등록된 항목이 바뀌었는지" 추적만으로는 이런 신규 제정을
    놓친다. 소관부처(department) + 키워드 이중 필터로 찾은 후보를 여기 저장해
    사용자가 등록/무시를 고르게 한다. 무시한 것도 행이 남아있어야(status만
    변경) 다음 스캔에서 같은 항목이 다시 후보로 뜨지 않는다."""

    __tablename__ = "new_admrul_candidates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source_type: Mapped[str] = mapped_column(String(16), default="admrul")
    external_id: Mapped[str] = mapped_column(String(64))
    master_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    name: Mapped[str] = mapped_column(String(255))
    category: Mapped[str | None] = mapped_column(String(64), nullable=True)
    department: Mapped[str | None] = mapped_column(String(128), nullable=True)
    promulgation_no: Mapped[str | None] = mapped_column(String(64), nullable=True)
    promulgation_date: Mapped[str | None] = mapped_column(String(16), nullable=True)
    enforcement_date: Mapped[str | None] = mapped_column(String(16), nullable=True)
    detail_link: Mapped[str | None] = mapped_column(String(512), nullable=True)
    matched_keyword: Mapped[str | None] = mapped_column(String(64), nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="신규")  # 신규 | 등록됨 | 무시됨
    first_seen_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=now)

    __table_args__ = (UniqueConstraint("source_type", "external_id", name="uq_new_admrul_source_external"),)


class ScrapedLawContent(Base):
    """법령/행정규칙 본문(조문) 캐시.

    국가법령정보 공동활용 API의 "목록 조회"(lawSearch.do)는 법령명 검색만
    지원하고 본문 전체를 대상으로 한 검색은 제공하지 않는다(본문은 "상세
    조회"로 한 건씩만 받아올 수 있음). 그래서 본문검색 기능과, 사규 태그가
    법령 개정 내용과 겹치는지 판단하는 기능 모두 이 캐시 테이블에 미리
    받아둔 본문 텍스트를 대상으로 로컬 검색한다.

    - 추적 중인(TrackedLaw) 법령/고시는 매 동기화(sync)마다 자동으로
      본문이 갱신된다(태그 매칭이 최신 개정 내용을 반영하도록).
    - 아직 등록하지 않은 법령까지 포함한 더 넓은 범위는 설정 화면의
      "본문 캐시 새로고침"을 눌러야 채워진다(API 호출이 많아 자동으로는
      하지 않음)."""

    __tablename__ = "scraped_law_contents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source_type: Mapped[str] = mapped_column(String(16))
    external_id: Mapped[str] = mapped_column(String(64))
    master_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    name: Mapped[str] = mapped_column(String(255))
    category: Mapped[str | None] = mapped_column(String(64), nullable=True)
    department: Mapped[str | None] = mapped_column(String(128), nullable=True)
    promulgation_no: Mapped[str | None] = mapped_column(String(64), nullable=True)
    promulgation_date: Mapped[str | None] = mapped_column(String(16), nullable=True)
    enforcement_date: Mapped[str | None] = mapped_column(String(16), nullable=True)
    detail_link: Mapped[str | None] = mapped_column(String(512), nullable=True)
    content: Mapped[str | None] = mapped_column(Text, nullable=True)
    # content 앞부분 중 조문단위에서 나와 조번호 라벨이 붙었을 수 있는
    # 구간의 길이(글자 수). 검색어가 이 구간 밖(별표/서식/부칙 등)에서
    # 매칭되면 조번호를 알 수 없으므로 조문 링크를 만들지 않는다.
    article_content_len: Mapped[int] = mapped_column(Integer, default=0)
    cached_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=now, onupdate=now)

    __table_args__ = (
        UniqueConstraint("source_type", "external_id", name="uq_scraped_content_source_external"),
    )


class KoshaGuide(Base):
    """KOSHA GUIDE(한국산업안전보건공단이 발간하는 기술지침) 라이브러리.

    국가법령정보 공동활용 API와 달리 KOSHA GUIDE는 공개 조회 API가 없고
    안전보건공단 홈페이지에 개별 PDF로 게시된다. 그래서 사용자가 한 건씩
    입력하거나(가이드 추가) 갖고 있는 목록을 붙여넣기(일괄 등록)로
    채워두면, 그 범위 안에서 지침번호/제목/본문(입력해둔 경우)을 대상으로
    로컬 키워드 검색을 제공한다 - 법령 키워드 검색(ScrapedLawContent)과
    같은 검색 경험을, 자동 수집이 안 되는 이 데이터셋에 대해서도 제공하는
    것이 목적이다."""

    __tablename__ = "kosha_guides"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str | None] = mapped_column(String(64), nullable=True)  # 지침번호, 예: "G-68-2022"
    field: Mapped[str | None] = mapped_column(String(64), nullable=True)  # 분야(안전분야/보건분야/화학물질 등, 자유 입력)
    title: Mapped[str] = mapped_column(String(512))
    issued_date: Mapped[str | None] = mapped_column(String(16), nullable=True)  # 제개정일자 YYYYMMDD
    file_link: Mapped[str | None] = mapped_column(String(512), nullable=True)
    # 본문 텍스트(선택) - 입력해두면 제목/지침번호뿐 아니라 이 내용까지
    # 키워드 검색 대상에 포함된다. PDF 원문에서 직접 복사해 붙여넣는 것을
    # 가정하며, 없어도(빈 값이어도) 제목/지침번호 검색은 그대로 동작한다.
    content: Mapped[str | None] = mapped_column(Text, nullable=True)
    # 원문 링크가 새로 생겼거나 바뀌었는데(API 재동기화로 감지된 개정,
    # 또는 "수정"에서 링크를 직접 바꾼 경우) 아직 그 새 PDF에서 본문을
    # 다시 뽑아오지 못한 상태인지 - "본문 캐시 채우기"가 매번 전체를
    # 다시 훑지 않고 True인 항목만 처리하게 하기 위한 표시. 새로 만들어질
    # 때는 아직 캐시된 적이 없으니 기본값 True.
    content_stale: Mapped[bool] = mapped_column(Boolean, default=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=now)
    updated_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=now, onupdate=now)

    # code가 없는(모르는) 항목은 NULL로 저장되고, SQLite는 NULL끼리 서로
    # 다른 값으로 취급해 유니크 제약에 걸리지 않는다 - 지침번호를 모르는
    # 여러 건을 등록해도 문제없다. 지침번호가 있는 항목끼리만 중복을 막는다.
    __table_args__ = (UniqueConstraint("code", name="uq_kosha_guide_code"),)


class AppSetting(Base):
    __tablename__ = "app_settings"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[str | None] = mapped_column(Text, nullable=True)


class NewsItem(Base):
    """대시보드 자동 스크롤 게시판에 표시되는 안전보건 뉴스 한 건.

    고용노동부/안전보건공단 안전보건 이슈, 중대재해 뉴스 세 카테고리(category:
    "moel" | "kosha" | "accident")로 나뉘며, 각각 설정에서 지정한 RSS/Atom
    피드 주소를 주기적으로 읽어와 채워진다(news_service.sync_news 참고).
    같은 카테고리 안에서 guid(피드의 고유 식별자, 보통 원문 링크)가 같으면
    중복 저장하지 않는다."""

    __tablename__ = "news_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    category: Mapped[str] = mapped_column(String(16))  # "moel" | "kosha" | "accident"
    source_name: Mapped[str] = mapped_column(String(64))
    title: Mapped[str] = mapped_column(String(512))
    link: Mapped[str] = mapped_column(String(1024))
    guid: Mapped[str] = mapped_column(String(512))
    published_at: Mapped[datetime.datetime | None] = mapped_column(DateTime, nullable=True)
    fetched_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=now)
    # 실제 피드를 못 가져왔을 때(네트워크 차단 등) 화면이 비어 보이지 않도록
    # 채워 넣는 예시 데이터인지 여부. 실제 데이터가 들어오기 시작하면 같은
    # 카테고리의 예시 항목은 정리된다.
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False)
    # 사용자가 "안전보건 뉴스" 화면에서 직접 표시하는 보관 여부. 보관 처리된
    # 항목은 news_service.sync_news의 발행일 기준 보관 기간(기본 6개월)
    # 정리 대상에서 제외되어 기간이 지나도 삭제되지 않는다.
    is_archived: Mapped[bool] = mapped_column(Boolean, default=False)

    __table_args__ = (UniqueConstraint("category", "guid", name="uq_news_category_guid"),)

    @hybrid_property
    def is_nonfatal_accident(self) -> bool:
        return self.category == "accident" and not any(k in self.title for k in FATAL_KEYWORDS)

    @is_nonfatal_accident.expression
    def is_nonfatal_accident(cls):
        return and_(cls.category == "accident", not_(or_(*[cls.title.contains(k) for k in FATAL_KEYWORDS])))
