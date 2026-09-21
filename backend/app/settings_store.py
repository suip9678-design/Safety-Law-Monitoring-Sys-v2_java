"""DB-backed runtime settings with .env as the initial default.

Lets the user change the law.go.kr OC key from the dashboard's 설정 tab
without restarting the server. Values are stored in the app_settings
table; anything not overridden there falls back to the value from
config.settings (i.e. the .env file).
"""

from sqlalchemy.orm import Session

from . import models
from .config import settings as env_settings

_KEYS = [
    "law_api_oc",
    "kosha_guide_api_key",
    "kosha_guide_api_url",
    "new_admrul_keywords",
    "new_admrul_department",
    "new_admrul_since_date",
    "full_law_cache_enabled",
    "news_ticker_enabled",
    "news_source_moel_url",
    "news_source_kosha_url",
    "news_source_accident_url",
    "news_retention_days",
]

_ENV_DEFAULTS = {
    "law_api_oc": env_settings.LAW_API_OC,
    "kosha_guide_api_key": env_settings.KOSHA_GUIDE_API_KEY,
    "kosha_guide_api_url": env_settings.KOSHA_GUIDE_API_URL,
    "new_admrul_keywords": env_settings.NEW_ADMRUL_KEYWORDS,
    "new_admrul_department": env_settings.NEW_ADMRUL_DEPARTMENT,
    "new_admrul_since_date": env_settings.NEW_ADMRUL_SINCE_DATE,
    "full_law_cache_enabled": "true" if env_settings.FULL_LAW_CACHE_ENABLED else "false",
    "news_ticker_enabled": "true" if env_settings.NEWS_TICKER_ENABLED else "false",
    "news_source_moel_url": env_settings.NEWS_SOURCE_MOEL_URL,
    "news_source_kosha_url": env_settings.NEWS_SOURCE_KOSHA_URL,
    "news_source_accident_url": env_settings.NEWS_SOURCE_ACCIDENT_URL,
    "news_retention_days": str(env_settings.NEWS_RETENTION_DAYS),
}


def get_all(db: Session) -> dict[str, str]:
    rows = {row.key: row.value for row in db.query(models.AppSetting).all()}
    result = dict(_ENV_DEFAULTS)
    for key in _KEYS:
        # 사용자가 화면에서 빈 값으로 저장한 것("필터 없음"처럼 빈 값
        # 자체가 의미 있는 설정)과, 아예 한 번도 저장한 적 없는 것을
        # 구분해야 한다. 예전에는 저장된 값이 빈 문자열이면 무조건 .env
        # 기본값으로 되돌아가 버려서, 소관부처 칸을 비워 저장해도 계속
        # NEW_ADMRUL_DEPARTMENT 기본값(예: "고용노동부")이 다시 채워지는
        # 문제가 있었다 - DB에 그 키의 행이 있는지(row가 존재하는지)로
        # "저장한 적 있는지"를 판단해야 사용자가 빈 값으로 되돌리는 것도
        # 그대로 존중된다.
        if key in rows and rows[key] is not None:
            result[key] = rows[key]
    return result


def get(db: Session, key: str) -> str:
    return get_all(db).get(key, "")


def set_values(db: Session, values: dict[str, str]) -> None:
    for key, value in values.items():
        if key not in _KEYS or value is None:
            continue
        row = db.get(models.AppSetting, key)
        if row is None:
            row = models.AppSetting(key=key, value=str(value))
            db.add(row)
        else:
            row.value = str(value)
    db.commit()
