import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")


def _bool(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in ("1", "true", "yes", "on")


def _normalize_db_url(url: str) -> str:
    # Render/Neon/Heroku-style Postgres URLs use the "postgres://" scheme,
    # but SQLAlchemy 2.x requires "postgresql://".
    if url.startswith("postgres://"):
        return "postgresql://" + url[len("postgres://"):]
    return url


class Settings:
    DATABASE_URL: str = _normalize_db_url(
        os.getenv("DATABASE_URL", f"sqlite:///{BASE_DIR / 'safety_law_tracker.db'}")
    )

    LAW_API_OC: str = os.getenv("LAW_API_OC", "").strip()

    # KOSHA 가이드(KOSHA GUIDE) 동기화용 공공데이터포털 "한국산업안전보건공단_
    # 기술지원규정(코샤가이드) 조회서비스" Open API. 국가법령정보센터
    # (LAW_API_OC)와는 완전히 별개의 키/엔드포인트다. 자세한 내용은
    # kosha_guide_api.py 상단 설명 참고. 활용신청 상세페이지의 "서비스 URL"
    # 칸에는 `.../B552468/koshaguide`까지만 나오고 뒤의 오퍼레이션 경로
    # (/getKoshaGuide)는 빠져 있으니 붙여서 써야 한다. 이 API는 KOSHA
    # GUIDE 전체 목록을 페이지만 넘겨 받아올 수 있어(검색 키워드 불필요),
    # 예전 스마트검색 API처럼 동기화용 키워드 목록을 따로 설정해둘 필요가 없다.
    KOSHA_GUIDE_API_KEY: str = os.getenv("KOSHA_GUIDE_API_KEY", "").strip()
    KOSHA_GUIDE_API_URL: str = os.getenv(
        "KOSHA_GUIDE_API_URL",
        "https://apis.data.go.kr/B552468/koshaguide/getKoshaGuide",
    ).strip()

    AUTO_SYNC_INTERVAL_HOURS: int = int(os.getenv("AUTO_SYNC_INTERVAL_HOURS", "24") or "0")

    # 신규 제정 고시 자동 탐지: 아직 등록 안 한 고시/예규/훈령 중, 소관부처가
    # NEW_ADMRUL_DEPARTMENT와 일치하면서 이름에 NEW_ADMRUL_KEYWORDS 중
    # 하나라도 포함된 것만 후보로 찾아낸다(이중 필터). 등록해둔 고시가
    # "개정"되는게 아니라 매년 새로 "제정"되는 경우가 많아, 기존의
    # "등록된 항목이 바뀌었는지" 추적만으로는 놓치는 부분을 보완한다.
    NEW_ADMRUL_KEYWORDS: str = os.getenv(
        "NEW_ADMRUL_KEYWORDS",
        "안전보건,산업안전,중대재해,위험성평가,유해위험,보건관리,안전관리",
    ).strip()
    NEW_ADMRUL_DEPARTMENT: str = os.getenv("NEW_ADMRUL_DEPARTMENT", "고용노동부").strip()
    # 이 날짜(YYYYMMDD) 이전에 공포된 고시/예규/훈령은 "신규 제정" 후보에서
    # 제외한다. 비어있으면 필터 없이 전부 대상. 여러 사용자에게 배포될 때
    # 설치 시점마다 이 값을 다르게 잡을 수 있도록 설정 화면에서 바꿀 수 있다.
    NEW_ADMRUL_SINCE_DATE: str = os.getenv("NEW_ADMRUL_SINCE_DATE", "").strip()

    # 전체 법령(법률/시행령/시행규칙) 본문 자동 캐시 - 매일 새벽 1시(KST)에
    # 목록 조회 API를 끝까지 페이지 넘겨가며 훑어 등록 여부와 무관하게
    # 모든 법령의 본문을 캐시한다. 키워드 검색이 "안전보건 관련 키워드"
    # 범위를 벗어난 법령(예: 도로교통법)도 찾을 수 있게 하기 위함. 기본은
    # 꺼짐(수천 건 상세조회를 매일 자동으로 도는 건 부담이 커서, 사용자가
    # 설정에서 명시적으로 켜야 동작).
    FULL_LAW_CACHE_ENABLED: bool = _bool(os.getenv("FULL_LAW_CACHE_ENABLED"), False)

    # 배포 시 대시보드 보호용 (둘 다 설정해야 로그인 요구가 활성화됨)
    DASHBOARD_USERNAME: str = os.getenv("DASHBOARD_USERNAME", "").strip()
    DASHBOARD_PASSWORD: str = os.getenv("DASHBOARD_PASSWORD", "").strip()

    FRONTEND_DIR: Path = BASE_DIR.parent / "frontend"

    # KOSHA 가이드 원문 PDF 수동 첨부용 저장 폴더. 공공데이터포털
    # 스마트검색 API는 지침번호/제개정일자뿐 아니라 원문 링크(filepath)도
    # 실제로는 거의 항상 비어서 오는 경우가 많아(kosha_guide_api.py 상단
    # 설명 참고), API 동기화만으로는 "가이드를 눌러서 원문을 본다"는 게
    # 안 되는 경우가 많다. 이 폴더는 그럴 때 사용자가 가이드별로 PDF를
    # 직접 첨부해서, 그 파일을 서버가 대신 서빙해주기 위한 저장소다.
    KOSHA_GUIDE_FILES_DIR: Path = BASE_DIR / "kosha_guide_files"

    # 대시보드 안전보건 뉴스 자동 스크롤 게시판. 고용노동부/안전보건공단
    # 공식 사이트는 이 프로젝트를 만드는 개발 환경에서 네트워크 접근이
    # 막혀 있어 공식 RSS 주소를 검증하지 못했다(law_api.py의 국가법령정보센터
    # API와 같은 사정) - 기본값은 별도 승인 없이 어떤 네트워크에서도
    # 동작하는 구글 뉴스 RSS 검색으로 채워두었고, 소관부처의 공식 RSS
    # 주소를 확인하면 설정 탭에서 그 주소로 교체하면 된다(표준 RSS/Atom
    # 형식이면 어떤 URL이든 동작).
    NEWS_TICKER_ENABLED: bool = _bool(os.getenv("NEWS_TICKER_ENABLED"), True)
    NEWS_FETCH_INTERVAL_HOURS: int = int(os.getenv("NEWS_FETCH_INTERVAL_HOURS", "3") or "0")
    # 뉴스 1건당 용량이 URL/제목 정도라 매우 작아(건당 1KB 미만) 개수보다는
    # "발행일 기준 며칠까지 보관할지"로 관리하는 게 더 직관적이다. 이 기간이
    # 지난 뉴스는 자동 삭제되지만, 사용자가 "안전보건 뉴스" 화면에서 개별
    # 항목을 "보관" 처리해두면 기간이 지나도 삭제되지 않는다
    # (NewsItem.is_archived, news_service.sync_news 참고).
    NEWS_RETENTION_DAYS: int = int(os.getenv("NEWS_RETENTION_DAYS", "180") or "180")
    NEWS_SOURCE_MOEL_URL: str = os.getenv(
        "NEWS_SOURCE_MOEL_URL",
        "https://news.google.com/rss/search?q=%EA%B3%A0%EC%9A%A9%EB%85%B8%EB%8F%99%EB%B6%80%20%EC%95%88%EC%A0%84%EB%B3%B4%EA%B1%B4&hl=ko&gl=KR&ceid=KR:ko",
    ).strip()
    NEWS_SOURCE_KOSHA_URL: str = os.getenv(
        "NEWS_SOURCE_KOSHA_URL",
        "https://news.google.com/rss/search?q=%EC%95%88%EC%A0%84%EB%B3%B4%EA%B1%B4%EA%B3%B5%EB%8B%A8&hl=ko&gl=KR&ceid=KR:ko",
    ).strip()
    NEWS_SOURCE_ACCIDENT_URL: str = os.getenv(
        "NEWS_SOURCE_ACCIDENT_URL",
        "https://news.google.com/rss/search?q=%EC%A4%91%EB%8C%80%EC%9E%AC%ED%95%B4&hl=ko&gl=KR&ceid=KR:ko",
    ).strip()


settings = Settings()
settings.KOSHA_GUIDE_FILES_DIR.mkdir(parents=True, exist_ok=True)
