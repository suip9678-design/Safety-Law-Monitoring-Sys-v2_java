"""법령/행정규칙 본문 캐시(ScrapedLawContent) 관리.

국가법령정보 공동활용 API는 법령명 검색만 지원하고 조문 본문을 대상으로
한 전체 검색은 제공하지 않는다. 그래서 본문검색 기능과 사규 태그-법령
자동 매칭 기능 모두, 상세 조회 API로 미리 받아온 본문 텍스트를 이
테이블에 캐시해두고 그 안에서 로컬 검색을 한다."""

import datetime
import logging
import re
import time
import urllib.parse

from sqlalchemy import func
from sqlalchemy.orm import Session

from . import models
from .law_api import LawApiError

logger = logging.getLogger("safety_law_tracker")


def _upsert(
    db: Session,
    source_type: str,
    external_id: str,
    master_id: str | None,
    detail: dict,
) -> None:
    row = (
        db.query(models.ScrapedLawContent)
        .filter(
            models.ScrapedLawContent.source_type == source_type,
            models.ScrapedLawContent.external_id == external_id,
        )
        .first()
    )
    if row is None:
        row = models.ScrapedLawContent(source_type=source_type, external_id=external_id)
        db.add(row)

    row.master_id = master_id or detail.get("master_id")
    row.name = detail.get("name") or row.name or ""
    row.category = detail.get("category")
    row.department = detail.get("department")
    row.promulgation_no = detail.get("promulgation_no")
    row.promulgation_date = detail.get("promulgation_date")
    row.enforcement_date = detail.get("enforcement_date")
    row.detail_link = detail.get("detail_link")
    row.content = detail.get("content") or ""
    # 조번호 라벨이 붙은 "조문" 구간의 길이. 없으면(예: 데모 fixtures처럼
    # 조문 구조를 따로 나누지 않는 경우) 본문 전체를 조문 구간으로 본다.
    article_content_len = detail.get("article_content_len")
    row.article_content_len = article_content_len if article_content_len is not None else len(row.content)
    row.cached_at = datetime.datetime.utcnow()


def refresh_tracked_law_content(db: Session, client) -> int:
    """추적 중인 모든 법령/고시의 본문을 다시 받아 캐시에 반영한다.

    매 동기화(sync)마다 호출되어, 사규 태그 자동 매칭이 항상 최신 개정
    본문을 기준으로 이뤄지게 한다."""
    laws = db.query(models.TrackedLaw).filter(models.TrackedLaw.is_active.is_(True)).all()
    count = 0
    for law in laws:
        try:
            detail = client.get_detail(law.source_type, law.external_id)
        except LawApiError:
            continue
        if not detail:
            continue
        # 상세조회(get_detail) API 응답에는 상세링크 태그가 없을 수 있다
        # (검색 응답에만 있는 필드일 가능성) - 등록 시점에 검색 응답으로
        # 이미 확보해둔 TrackedLaw.detail_link를 대신 채워, 키워드 검색
        # 결과의 링크가 비지 않게 한다.
        if not detail.get("detail_link"):
            detail["detail_link"] = law.detail_link
        _upsert(db, law.source_type, law.external_id, law.master_id, detail)
        count += 1
    if count:
        db.commit()
    return count


def refresh_candidate_content(db: Session, client, keywords: list[str], department: str) -> int:
    """추적 중인 법령뿐 아니라, 소관부처+키워드로 찾아지는 안전보건 관련
    후보 법령/고시까지 포함해 더 넓은 범위의 본문을 캐시에 채운다.

    API 호출이 많아(키워드 수 x 2개 대상 + 후보별 상세조회 1건씩)
    자동으로는 돌리지 않고, 설정 화면에서 사용자가 직접 실행한다."""
    candidates: dict[tuple[str, str], dict] = {}

    for law in db.query(models.TrackedLaw).filter(models.TrackedLaw.is_active.is_(True)).all():
        candidates[(law.source_type, law.external_id)] = {
            "master_id": law.master_id,
            "detail_link": law.detail_link,
        }

    for target in ("law", "admrul"):
        for kw in keywords:
            try:
                results = client.search(target, kw)
            except LawApiError:
                continue
            for r in results:
                external_id = r.get("external_id")
                if not external_id:
                    continue
                if department and target == "admrul" and department not in (r.get("department") or ""):
                    continue
                key = (r.get("source_type") or target, external_id)
                candidates.setdefault(
                    key, {"master_id": r.get("master_id"), "detail_link": r.get("detail_link")}
                )

    count = 0
    for (source_type, external_id), info in candidates.items():
        try:
            detail = client.get_detail(source_type, external_id)
        except LawApiError:
            continue
        if not detail:
            continue
        # 검색 응답(목록 조회)에서 이미 확보한 상세링크를, 상세조회 응답에
        # 없을 경우의 대체값으로 채운다(위 refresh_tracked_law_content와
        # 동일한 이유).
        if not detail.get("detail_link"):
            detail["detail_link"] = info.get("detail_link")
        _upsert(db, source_type, external_id, info.get("master_id"), detail)
        count += 1

    if count:
        db.commit()
    return count


# 전체 법령(law: 법률/시행령/시행규칙) + 전체 행정규칙(admrul: 모든 부처의
# 고시/예규/훈령) 본문 자동 캐시. "신규 제정 고시" 키워드에 안 걸리는
# 법령(예: 도로교통법의 "과속")도 키워드 검색에서 찾을 수 있게 하려는
# 용도. 목록 조회 API를 query 없이 페이지 번호만 올려가며 끝까지 순회한다.
#
# admrul은 소관부처로 걸러내지 않고 전체를 담는다 - 처음 한 번은 수만 건을
# 다 받아오느라 매우 오래 걸리지만(공포번호 확인용 목록 조회 자체는 가볍고,
# 무거운 건 상세조회 쪽), 그다음부터는 공포번호가 바뀐 것만 다시 받아오므로
# 훨씬 빨라진다(아래 existing_promulgation 참고).
#
# 이 세션은 law.go.kr에 직접 접근할 수 없어, query를 생략하면 전체
# 목록이 페이지네이션되어 반환된다는 것을 실제 응답으로 검증하지
# 못했다 - 여러 공개 문서/예제에서 target만으로 호출하는 사례를
# 확인했지만 100% 확신은 아니다. 만약 실제로는 query가 필수라 빈 결과만
# 온다면 이 함수는 첫 페이지에서 바로 0건으로 끝난다(무한 호출이나
# 장애로 이어지지 않는 안전한 실패). "지금 시작" 버튼으로 실행한 뒤
# 캐시된 건수를 보고 이 가정이 맞는지 확인할 것.
_FULL_CACHE_PAGE_SIZE = 100
_FULL_CACHE_MAX_PAGES = 2000  # 안전장치: 대상당 최대 100*2000 = 200,000건(행정규칙 전체 부처 대비 여유)
_FULL_CACHE_REQUEST_DELAY = 0.2  # 정부 서버에 과도한 연속 요청을 피하기 위한 간격(초)

_full_cache_status = {
    "running": False,
    "processed": 0,
    "skipped": 0,
    "total": None,
    "started_at": None,
    "finished_at": None,
    "error": None,
}


def full_cache_status() -> dict:
    return dict(_full_cache_status)


def refresh_full_law_content(db: Session, client, source_types: tuple[str, ...] = ("law", "admrul")) -> int:
    """target별로 목록 조회 API를 페이지 끝까지 순회해, 등록 여부와
    무관하게 법령·행정규칙(모든 부처) 본문을 캐시한다.

    목록 조회 결과에는 공포번호(promulgation_no)가 이미 들어있는데(상세조회
    없이도 알 수 있음), 이미 캐시된 항목이면서 공포번호가 그대로면 실제
    내용도 안 바뀌었다고 보고 무거운 상세조회를 건너뛴다. 그래서 최초
    실행은 전부 새로 받아오느라 오래 걸리지만, 그다음부터는(예: 매일
    새벽) 실제로 개정·신규 제정된 것만 다시 받아와 훨씬 빨라진다.

    시간이 오래 걸릴 수 있어 매 상세조회 사이에 짧은 지연을 두고, 진행
    상황을 _full_cache_status에 기록해 API로 조회할 수 있게 한다. 200건마다
    중간 커밋해서, 도중에 실패해도 그때까지 받은 건 남게 한다."""
    _full_cache_status.update(
        running=True, processed=0, skipped=0, total=None,
        started_at=datetime.datetime.utcnow().isoformat() + "Z", finished_at=None, error=None,
    )
    # 진행률 표시용 총 건수(대상별 totalCnt 합). 실패해도(None) 캐시 자체는
    # 계속 진행한다 - 진행 건수만 보이고 "/총건수"는 생략된다.
    total = 0
    for source_type in source_types:
        source_total = client.count_total(source_type)
        if source_total is None:
            total = None
            break
        total += source_total
    _full_cache_status["total"] = total

    # 기존에 캐시된 항목들의 공포번호를 미리 한 번에 읽어와서(각 항목마다
    # DB를 따로 조회하지 않기 위함), 검색 결과의 공포번호와 비교한다.
    existing_promulgation = {
        (row.source_type, row.external_id): row.promulgation_no
        for row in db.query(
            models.ScrapedLawContent.source_type,
            models.ScrapedLawContent.external_id,
            models.ScrapedLawContent.promulgation_no,
        ).all()
    }

    seen: set[tuple[str, str]] = set()
    count = 0
    skipped = 0
    try:
        for source_type in source_types:
            for page in range(1, _FULL_CACHE_MAX_PAGES + 1):
                try:
                    results = client.search(source_type, "", display=_FULL_CACHE_PAGE_SIZE, page=page)
                except LawApiError as exc:
                    logger.warning("전체 법령 캐시 중 목록 조회 실패(%s, %d페이지): %s", source_type, page, exc)
                    break
                if not results:
                    break
                for r in results:
                    external_id = r.get("external_id")
                    if not external_id:
                        continue
                    key = (r.get("source_type") or source_type, external_id)
                    if key in seen:
                        continue
                    seen.add(key)

                    new_promulgation_no = r.get("promulgation_no")
                    already_cached = key in existing_promulgation
                    if already_cached and new_promulgation_no and existing_promulgation[key] == new_promulgation_no:
                        # 공포번호가 그대로 - 상세조회 없이 건너뛴다.
                        skipped += 1
                        _full_cache_status["skipped"] = skipped
                        continue

                    try:
                        detail = client.get_detail(key[0], key[1])
                    except LawApiError:
                        continue
                    if not detail:
                        continue
                    if not detail.get("detail_link"):
                        detail["detail_link"] = r.get("detail_link")
                    # 목록 조회(search)와 상세조회(get_detail)는 같은 "공포번호"를
                    # 서로 다른 방식으로 추출한다(목록은 항목 바로 아래에서 직접
                    # 찾고, 상세는 트리 전체를 훑어 처음 걸리는 태그를 쓴다) - 실사용
                    # 중 이 둘이 같은 값인데도 텍스트가 미묘하게 달라 나오는 항목이
                    # 있어, 저장 후 다음 실행 때 "값이 다르다"고 오판해 안 바뀐
                    # 항목을 매번 다시 상세조회하는 문제가 있었다(며칠 새 다시 실행해도
                    # 항상 같은 수십 건이 "새로 받음"으로 나옴). 다음 비교 기준이
                    # 되는 값은 항상 이번에 건너뛰기 판단에도 쓴 목록 조회 값으로
                    # 통일해 저장해, 같은 값이 두 가지로 갈라지지 않게 한다.
                    if new_promulgation_no:
                        detail["promulgation_no"] = new_promulgation_no
                    _upsert(db, key[0], key[1], r.get("master_id"), detail)
                    count += 1
                    _full_cache_status["processed"] = count
                    if count % 200 == 0:
                        db.commit()
                    time.sleep(_FULL_CACHE_REQUEST_DELAY)
                if len(results) < _FULL_CACHE_PAGE_SIZE:
                    break
            else:
                # for-else: 500페이지를 다 돌 때까지 "마지막 페이지"를 못
                # 만났다는 뜻 - 안전장치(_FULL_CACHE_MAX_PAGES)에 걸려
                # 중간에 멈춘 것이므로, 조용히 끝난 것처럼 보이지 않게 남긴다.
                logger.warning(
                    "전체 법령 캐시: %s 대상이 최대 페이지 수(%d)에 도달해 중단됨(더 남아있을 수 있음)",
                    source_type, _FULL_CACHE_MAX_PAGES,
                )
        db.commit()
    except Exception as exc:  # noqa: BLE001 - 원인이 뭐든 상태에 남겨서 화면에 보이게 함
        db.rollback()
        _full_cache_status["error"] = str(exc)
        logger.exception("전체 법령 캐시 중 오류")
    finally:
        _full_cache_status.update(running=False, finished_at=datetime.datetime.utcnow().isoformat() + "Z")
    return count


def cache_status(db: Session) -> dict:
    count = db.query(models.ScrapedLawContent).count()
    last_cached_at = db.query(func.max(models.ScrapedLawContent.cached_at)).scalar()
    # DB에는 항상 naive UTC로 저장되는데(datetime.utcnow()), 이 값은 다른
    # 시각 필드들과 달리 Pydantic 스키마(UtcDateTimeOpt)를 안 거치고
    # 그대로 반환돼서 "Z"가 안 붙어 있었다 - 그러면 브라우저가 이걸 이미
    # 로컬 시간(KST)인 것으로 잘못 해석해 9시간 어긋나게 표시된다.
    return {
        "cached_count": count,
        "last_cached_at": last_cached_at.isoformat() + "Z" if last_cached_at else None,
    }


def _snippet(content: str, idx: int, needle_len: int, radius: int = 40) -> str:
    start = max(0, idx - radius)
    end = min(len(content), idx + needle_len + radius)
    prefix = "…" if start > 0 else ""
    suffix = "…" if end < len(content) else ""
    return f"{prefix}{content[start:end].strip()}{suffix}"


_ARTICLE_NO_RE = re.compile(r"제(\d+)조")


def _build_article_link(name: str, content: str, match_idx: int, article_content_len: int) -> str | None:
    """검색어가 매칭된 위치 앞에서 가장 최근에 나온 "제N조"를 찾아 법제처의
    조문 링크(LsiJoLinkP.do)를 만든다.

    match_idx가 article_content_len 밖(별표/서식/부칙 등 조번호를 모르는
    구간)이면 애초에 시도하지 않는다 - 그 앞의 마지막 조문 번호를 엉뚱하게
    가져다 붙이는 걸 막기 위함(예: 별표에 있는 내용이 그 앞 조문의 링크로
    잘못 연결되는 문제).

    본문 캐시는 조문 경계를 따로 저장하지 않고 텍스트를 이어붙인 통짜
    문자열이라, 실제 조문 텍스트가 관행대로 "제N조(...)"로 시작한다는
    점에 기대어 역방향으로 가장 가까운 조번호를 찾는 근사치다. 못 찾으면
    None을 돌려주고, 호출부는 법령 상세 링크(detail_link)로 대체한다.
    이 URL 형식은 이 세션이 law.go.kr에 직접 접근할 수 없어 실제 응답으로
    검증하지 못했다 - 조문으로 정상 이동하지 않으면 실제 법제처에서 조문
    링크를 열어 URL 형식을 다시 확인할 것."""
    if match_idx >= article_content_len:
        return None
    found = list(_ARTICLE_NO_RE.finditer(content[: match_idx + 1]))
    if not found:
        return None
    article_no = int(found[-1].group(1))
    params = {
        "docType": "JO",
        "lsNm": name,
        "joNo": f"{article_no:04d}00000",
        "languageType": "KO",
        "paras": "1",
    }
    return "https://www.law.go.kr/LSW/LsiJoLinkP.do?" + urllib.parse.urlencode(params)


def search_cache(db: Session, source_type: str, query: str) -> list[dict]:
    """키워드 검색 페이지용 로컬 캐시 검색.

    각 결과가 법령명에서 매칭됐는지 본문에서 매칭됐는지(matched_in)와,
    본문에서 매칭된 경우 검색어 주변 발췌문(snippet) + 그 조문으로 바로
    이동하는 링크(article_link)를 함께 돌려줘 "이 법령의 어디에 해당하는
    내용인지" 바로 보여주고 클릭해서 확인할 수 있게 한다. 본문 매칭이
    있으면 이름 매칭보다 더 구체적인 정보이므로 본문 쪽을 우선한다."""
    q = db.query(models.ScrapedLawContent)
    if source_type != "all":
        q = q.filter(models.ScrapedLawContent.source_type == source_type)
    needle = (query or "").strip()
    if not needle:
        return []

    results = []
    for row in q.all():
        content = row.content or ""
        name = row.name or ""
        snippet = ""
        article_link = None
        idx = content.find(needle)
        if idx != -1:
            matched_in = "content"
            snippet = _snippet(content, idx, len(needle))
            article_link = _build_article_link(name, content, idx, row.article_content_len)
        elif needle in name:
            matched_in = "name"
        else:
            continue
        results.append(
            {
                "source_type": row.source_type,
                "external_id": row.external_id,
                "master_id": row.master_id,
                "name": row.name,
                "category": row.category,
                "department": row.department,
                "promulgation_no": row.promulgation_no,
                "promulgation_date": row.promulgation_date,
                "enforcement_date": row.enforcement_date,
                "detail_link": row.detail_link,
                "matched_in": matched_in,
                "snippet": snippet,
                "article_link": article_link,
            }
        )
    return results
