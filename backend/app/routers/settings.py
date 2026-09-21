from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from .. import models, schemas, settings_store
from ..config import settings as env_settings
from ..database import get_db

router = APIRouter(prefix="/api/settings", tags=["settings"])

# 도움말 자동 팝업 여부 - 사용자가 설정 화면에서 바꾸는 값이 아니라 "이 설치본에서
# 도움말을 한 번이라도 띄운 적이 있는지"만 기억하는 내부 마커라, 다른 설정처럼
# settings_store를 거치지 않고 app_settings 테이블에 직접 읽고 쓴다. 브라우저의
# localStorage가 아니라 서버(DB)에 저장해서, 브라우저를 바꾸거나 캐시를 지워도
# "설치 후 최초 실행"에만 한 번 뜨고 그 뒤로는(재실행/재접속 포함) 다시 자동으로
# 뜨지 않는다.
_HELP_SHOWN_KEY = "help_shown_once"


def _news_showing_demo(db: Session, category: str) -> bool | None:
    """이 카테고리의 가장 최근에 받아온 뉴스가 예시(데모) 데이터인지.
    실제 피드 URL이 잘못됐거나 막혀 있으면 news_service.sync_news가 항상
    fixtures로 채우므로, 이 값이 계속 True로 남아있으면 "이 피드 URL을
    확인해야 한다"는 신뢰할 수 있는 신호가 된다. 아직 한 번도 동기화된
    적이 없으면(None) 판단할 근거가 없으므로 "문제 있음"으로 취급하지
    않는다."""
    latest = (
        db.query(models.NewsItem)
        .filter(models.NewsItem.category == category)
        .order_by(models.NewsItem.fetched_at.desc())
        .first()
    )
    return bool(latest.is_demo) if latest else None


@router.get("", response_model=schemas.SettingsOut)
def get_settings(db: Session = Depends(get_db)):
    values = settings_store.get_all(db)
    return schemas.SettingsOut(
        demo_mode=not bool(values.get("law_api_oc")),
        law_api_oc_set=bool(values.get("law_api_oc")),
        law_api_oc=values.get("law_api_oc") or None,
        kosha_guide_api_key_set=bool(values.get("kosha_guide_api_key")),
        kosha_guide_api_key=values.get("kosha_guide_api_key") or None,
        kosha_guide_api_url=values.get("kosha_guide_api_url") or None,
        auto_sync_interval_hours=env_settings.AUTO_SYNC_INTERVAL_HOURS,
        new_admrul_keywords=values.get("new_admrul_keywords") or None,
        new_admrul_department=values.get("new_admrul_department") or None,
        new_admrul_since_date=values.get("new_admrul_since_date") or None,
        full_law_cache_enabled=str(values.get("full_law_cache_enabled", "false")).lower() in ("1", "true", "yes", "on"),
        news_ticker_enabled=str(values.get("news_ticker_enabled", "true")).lower() in ("1", "true", "yes", "on"),
        news_source_moel_url=values.get("news_source_moel_url") or None,
        news_source_kosha_url=values.get("news_source_kosha_url") or None,
        news_source_accident_url=values.get("news_source_accident_url") or None,
        news_retention_days=int(values.get("news_retention_days") or 180),
        news_moel_showing_demo=_news_showing_demo(db, "moel"),
        news_kosha_showing_demo=_news_showing_demo(db, "kosha"),
        news_accident_showing_demo=_news_showing_demo(db, "accident"),
    )


_BOOL_FIELDS = ("full_law_cache_enabled", "news_ticker_enabled")


@router.put("", response_model=schemas.SettingsOut)
def update_settings(payload: schemas.SettingsUpdate, db: Session = Depends(get_db)):
    updates = payload.model_dump(exclude_unset=True)
    for key in _BOOL_FIELDS:
        if key in updates:
            updates[key] = "true" if updates[key] else "false"
    settings_store.set_values(db, updates)
    return get_settings(db)


@router.get("/help-shown")
def get_help_shown(db: Session = Depends(get_db)):
    row = db.get(models.AppSetting, _HELP_SHOWN_KEY)
    return {"shown": bool(row and row.value == "1")}


@router.post("/help-shown", status_code=204)
def mark_help_shown(db: Session = Depends(get_db)):
    row = db.get(models.AppSetting, _HELP_SHOWN_KEY)
    if row is None:
        db.add(models.AppSetting(key=_HELP_SHOWN_KEY, value="1"))
    else:
        row.value = "1"
    db.commit()
    return None
