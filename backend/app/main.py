import datetime
import logging
import zoneinfo

from apscheduler.schedulers.background import BackgroundScheduler
from fastapi import Depends, FastAPI
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session

from . import models, settings_store
from .auth import BasicAuthMiddleware
from .config import settings
from .database import SessionLocal, engine, ensure_columns, get_db
from .routers import (
    content_cache,
    dashboard,
    documents,
    kosha_guides,
    laws,
    mappings,
    news,
    revisions,
    settings as settings_router,
    sync,
)

logger = logging.getLogger("safety_law_tracker")

# 스케줄러가 KST(Asia/Seoul) 기준으로 도는데, run_date처럼 "지금부터 N초
# 뒤"를 직접 계산해서 넘길 때 datetime.now()(naive, OS 시스템 시간대 기준)를
# 쓰면 실제 서버의 시스템 시간대가 KST가 아닌 경우(예: UTC로 맞춰진 클라우드
# 서버) 몇 시간씩 어긋난다 - naive 값은 스케줄러가 자기 시간대(KST)로 그냥
# 해석해버리기 때문. 항상 이 tzinfo로 명시적인 aware datetime을 만들어야
# 시스템 시간대와 무관하게 정확하다.
_KST = zoneinfo.ZoneInfo("Asia/Seoul")

models.Base.metadata.create_all(bind=engine)
ensure_columns()

app = FastAPI(title="안전보건 정보 모니터링")
app.add_middleware(BasicAuthMiddleware)

app.include_router(laws.router)
app.include_router(revisions.router)
app.include_router(documents.router)
app.include_router(mappings.router)
app.include_router(sync.router)
app.include_router(settings_router.router)
app.include_router(dashboard.router)
app.include_router(content_cache.router)
app.include_router(news.router)
app.include_router(kosha_guides.router)

_scheduler: BackgroundScheduler | None = None

# 매일 새벽 1시에 도는 작업이 "마지막으로 언제 끝났는지"를 DB에 남겨둔다
# (app_settings 테이블 재사용, 사용자가 설정 화면에서 보거나 바꾸는 값은
# 아니라 settings_store를 거치지 않고 직접 읽고 쓴다). 컴퓨터를 매일 켜두는
# 게 아니라 필요할 때만 켜는 사용 방식이라, 새벽 1시에 컴퓨터가 꺼져 있으면
# 그 cron은 그냥 못 돌고 지나간다 - 그래서 서버가 켜질 때마다 "오늘 이미
# 돌았는지"를 확인해서, 안 돌았으면 그때 바로 한 번 실행해 따라잡는다.
_LAST_MAINTENANCE_KEY = "last_daily_maintenance_at"


def _get_last_maintenance_at(db) -> datetime.datetime | None:
    row = db.get(models.AppSetting, _LAST_MAINTENANCE_KEY)
    if not row or not row.value:
        return None
    try:
        return datetime.datetime.fromisoformat(row.value)
    except ValueError:
        return None


def _set_last_maintenance_at(db, when: datetime.datetime) -> None:
    row = db.get(models.AppSetting, _LAST_MAINTENANCE_KEY)
    if row is None:
        db.add(models.AppSetting(key=_LAST_MAINTENANCE_KEY, value=when.isoformat()))
    else:
        row.value = when.isoformat()
    db.commit()


def _scheduled_sync():
    from . import content_cache_service, settings_store
    from .law_api import build_client
    from .sync_service import sync_all

    db = SessionLocal()
    try:
        oc = settings_store.get(db, "law_api_oc")
        client = build_client(oc)
        new_revisions, errors = sync_all(db, client)
        content_cache_service.refresh_tracked_law_content(db, client)
        if errors:
            logger.warning("자동 동기화 중 오류: %s", errors)
        logger.info("자동 동기화 완료: 신규 개정 %d건", len(new_revisions))
    finally:
        db.close()


def _scheduled_news_sync():
    from . import news_service, settings_store

    db = SessionLocal()
    try:
        values = settings_store.get_all(db)
        if values.get("news_ticker_enabled", "true").strip().lower() not in ("1", "true", "yes", "on"):
            return
        retention_days = int(values.get("news_retention_days") or settings.NEWS_RETENTION_DAYS)
        added = news_service.sync_news(db, news_service.configured_sources(db), retention_days)
        logger.info("안전보건 뉴스 게시판 동기화 완료: 신규 %d건", added)
    except Exception:  # noqa: BLE001 - 뉴스 게시판 갱신 실패가 다른 스케줄 작업을 막으면 안 됨
        logger.exception("안전보건 뉴스 게시판 동기화 중 오류")
    finally:
        db.close()


def _scheduled_daily_maintenance():
    """매일 새벽 1시(KST)에 도는 작업 모음. (컴퓨터가 그 시각에 꺼져 있었다면
    서버가 켜질 때 대신 한 번 실행됨 - on_startup()의 "따라잡기" 로직 참고)

    - 신규 제정 고시 탐지: 원래 대시보드의 "새로고침" 버튼을 눌러야만
      돌던 작업이다. 하루에 한 번이면 충분한 가벼운 작업(키워드 몇 개로
      검색하는 정도)이라, 사용자가 직접 새로고침을 누르지 않아도 매일
      자동으로 돌도록 여기에 포함했다(별도 켜고 끄는 설정 없이 항상 실행).
    - 본문 캐시 새로고침(설정 화면의 "본문 캐시 새로고침" 버튼과 동일):
      추적 중인 법령 + 키워드/소관부처로 찾은 후보의 본문을 다시 받아
      캐시에 반영한다. 신규 제정 고시 탐지와 같은 키워드/부처 조건을
      쓰고, 하루 한 번이면 충분해 이 작업 바로 뒤에 묶어 항상 실행한다.
    - 전체 법령 자동 캐시: 상세조회를 수천 건씩 호출하는 무거운 작업이라,
      설정에서 켠 경우에만 실행한다."""
    from . import content_cache_service, settings_store
    from .law_api import build_client
    from .sync_service import scan_new_admrul

    db = SessionLocal()
    try:
        oc = settings_store.get(db, "law_api_oc")
        client = build_client(oc)

        keywords = [k.strip() for k in settings_store.get(db, "new_admrul_keywords").split(",") if k.strip()]
        department = settings_store.get(db, "new_admrul_department").strip()
        since_date = settings_store.get(db, "new_admrul_since_date").strip()
        try:
            new_candidates = scan_new_admrul(db, client, keywords, department, since_date)
            logger.info("신규 제정 고시 자동 탐지 완료: %d건", len(new_candidates))
        except Exception:  # noqa: BLE001 - 이 작업 실패가 아래 작업들까지 막으면 안 됨
            logger.exception("신규 제정 고시 자동 탐지 중 오류")

        try:
            cached_count = content_cache_service.refresh_candidate_content(db, client, keywords, department)
            logger.info("본문 캐시 자동 새로고침 완료: %d건", cached_count)
        except Exception:  # noqa: BLE001 - 이 작업 실패가 아래 전체 법령 캐시까지 막으면 안 됨
            logger.exception("본문 캐시 자동 새로고침 중 오류")

        enabled = settings_store.get(db, "full_law_cache_enabled").strip().lower() in ("1", "true", "yes", "on")
        if enabled:
            count = content_cache_service.refresh_full_law_content(db, client)
            logger.info("전체 법령 자동 캐시 완료: %d건", count)
    finally:
        _set_last_maintenance_at(db, datetime.datetime.utcnow())
        db.close()


@app.on_event("startup")
def on_startup():
    global _scheduler
    _scheduler = BackgroundScheduler(timezone=_KST)
    if settings.AUTO_SYNC_INTERVAL_HOURS > 0:
        _scheduler.add_job(
            _scheduled_sync,
            "interval",
            hours=settings.AUTO_SYNC_INTERVAL_HOURS,
            id="auto_sync",
            next_run_time=None,
        )
        logger.info("자동 동기화 스케줄러 등록 (%d시간 주기)", settings.AUTO_SYNC_INTERVAL_HOURS)
    if settings.NEWS_FETCH_INTERVAL_HOURS > 0:
        # 서버를 켤 때마다 20초 뒤에 한 번 바로 실행해, 최초 실행 시에도
        # 몇 시간을 기다리지 않고 대시보드 게시판이 곧바로 채워지게 한다.
        _scheduler.add_job(
            _scheduled_news_sync,
            "interval",
            hours=settings.NEWS_FETCH_INTERVAL_HOURS,
            id="news_sync",
            next_run_time=datetime.datetime.now(_KST) + datetime.timedelta(seconds=20),
        )
        logger.info("안전보건 뉴스 게시판 자동 수집 스케줄러 등록 (%d시간 주기)", settings.NEWS_FETCH_INTERVAL_HOURS)
    # 신규 제정 고시 탐지 + 본문 캐시 새로고침(둘 다 항상 실행) + (설정에서
    # 켠 경우) 전체 법령 자동 캐시를 매일 새벽 1시(KST)에 함께 실행한다.
    # 전체 법령 자동 캐시는 매번 켜져 있는지만 여기서 확인하므로, 서버
    # 재시작 없이 설정 화면에서 껐다 켰다 할 수 있다.
    _scheduler.add_job(
        _scheduled_daily_maintenance,
        "cron",
        hour=1,
        minute=0,
        id="daily_maintenance",
    )
    _scheduler.start()
    logger.info("스케줄러 시작")

    # "새벽 1시" cron은 그 시각에 컴퓨터가 켜져 있어야만 실행된다 - 상시
    # 켜두는 서버가 아니라 필요할 때 run.bat으로 켜는 사용 방식이라, 컴퓨터가
    # 꺼져 있는 새벽 시간대라면 그날 하루는 그냥 건너뛰게 된다. 그래서 서버가
    # 시작될 때마다 "최근 20시간 안에 이미 돌았는지"를 확인해서, 안 돌았으면
    # (즉 오늘 아직 못 돈 것으로 보이면) 시작 15초 뒤에 한 번 대신 실행한다
    # (다른 시동 작업과 겹치지 않게 약간 늦춤). 20시간으로 잡은 건 매일 켜는
    # 시각이 조금씩 들쭉날쭉해도 하루씩 안 밀리게 하기 위함.
    db = SessionLocal()
    try:
        last_at = _get_last_maintenance_at(db)
    finally:
        db.close()
    if last_at is None or (datetime.datetime.utcnow() - last_at) >= datetime.timedelta(hours=20):
        _scheduler.add_job(
            _scheduled_daily_maintenance,
            "date",
            run_date=datetime.datetime.now(_KST) + datetime.timedelta(seconds=15),
            id="daily_maintenance_catchup",
        )
        logger.info("최근 20시간 안에 일일 유지보수 실행 기록이 없어, 시작 15초 뒤 한 번 대신 실행합니다.")


@app.on_event("shutdown")
def on_shutdown():
    if _scheduler:
        _scheduler.shutdown(wait=False)


@app.get("/api/health")
def health(db: Session = Depends(get_db)):
    # settings.DEMO_MODE(.env 파일 기준, 서버 시작 시 한 번만 읽음)가 아니라
    # settings_store(대시보드 설정 화면에서 저장한 값이 .env보다 우선함)를
    # 봐야 한다 - 실제 법령/KOSHA 검색도 전부 이 값을 쓰므로(routers/laws.py,
    # sync.py 등), 상단 "데모 모드" 배지도 여기 맞춰야 실제 동작과 어긋나지
    # 않는다. .env가 아니라 설정 화면에서만 OC 키를 입력해둔 경우, 예전에는
    # 실제로는 정상 연결되어 있는데도 배지가 계속 "데모 모드"로 잘못 표시됐다.
    demo_mode = not bool(settings_store.get(db, "law_api_oc"))
    return {"status": "ok", "demo_mode": demo_mode}


if settings.FRONTEND_DIR.exists():
    app.mount("/", StaticFiles(directory=str(settings.FRONTEND_DIR), html=True), name="frontend")
