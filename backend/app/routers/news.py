import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, not_
from sqlalchemy.orm import Session

from .. import models, news_service, schemas, settings_store
from ..database import get_db

router = APIRouter(prefix="/api/news", tags=["news"])

# 검색 페이지가 한 번에 돌려받는 결과 상한. 총 건수(total)는 이 상한과
# 별도로 항상 정확하게 계산해 화면에서 "N건 중 최근 M건 표시"를 보여줄 수
# 있게 한다.
_SEARCH_LIMIT_MAX = 300


def _is_enabled(db: Session) -> bool:
    return settings_store.get(db, "news_ticker_enabled").strip().lower() in ("1", "true", "yes", "on")


def _parse_date(value: str | None) -> datetime.datetime | None:
    if not value:
        return None
    try:
        return datetime.datetime.strptime(value.strip(), "%Y-%m-%d")
    except ValueError:
        return None


def _out(row: models.NewsItem) -> schemas.NewsItemOut:
    """중대재해 피드 기사 중 사망사고가 아닌 것은 "안전보건 이슈"(issue)로 보여준다."""
    out = schemas.NewsItemOut.model_validate(row)
    if row.is_nonfatal_accident:
        out.category, out.source_name = "issue", "안전보건 이슈"
    return out


def _by_category(query, category: str | None, include_issues: bool):
    """category="accident"는 사망사고만, "issue"는 그 외 중대재해 피드 기사만.
    category가 없을 때는 include_issues인 화면(뉴스 탭)만 이슈를 함께 보여준다."""
    if category == "issue":
        return query.filter(models.NewsItem.is_nonfatal_accident)
    if category:
        query = query.filter(models.NewsItem.category == category)
    if category or not include_issues:
        query = query.filter(not_(models.NewsItem.is_nonfatal_accident))
    return query


@router.get("", response_model=list[schemas.NewsItemOut])
def list_news(category: str | None = None, limit: int = 40, db: Session = Depends(get_db)):
    if not _is_enabled(db):
        return []
    # 발행일(published_at)이 없는 항목(일부 피드는 안 줄 수 있음)은 가져온
    # 시각(fetched_at)을 대신 써서 정렬한다 - 둘 다 최신순이라는 목적은 같다.
    order_col = func.coalesce(models.NewsItem.published_at, models.NewsItem.fetched_at).desc()
    query = _by_category(db.query(models.NewsItem), category, include_issues=False)
    rows = query.order_by(order_col).limit(min(max(limit, 1), 200)).all()
    return [_out(r) for r in rows]


@router.get("/search", response_model=schemas.NewsSearchResult)
def search_news(
    q: str | None = None,
    category: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    archived: bool | None = None,
    limit: int = 200,
    db: Session = Depends(get_db),
):
    """"안전보건 뉴스" 별도 페이지 전용 검색. 대시보드 게시판 표시 여부
    설정(news_ticker_enabled)과 무관하게 항상 동작한다 - 그 설정은 대시보드
    위젯을 보여줄지에 대한 것이지, 뉴스를 검색하는 이 화면과는 별개다.

    날짜는 published_at(피드가 안 준 경우 fetched_at)을 기준으로 하루
    단위로 거른다. 검색 범위는 news_service.sync_news가 보관하는 만큼(설정
    "보관 기간")으로 한정된다 - 그 기간이 지나고 "보관" 처리도 안 해둔
    기사는 이미 정리되어 DB에 없다."""
    order_col = func.coalesce(models.NewsItem.published_at, models.NewsItem.fetched_at)
    query = _by_category(db.query(models.NewsItem), category, include_issues=True)
    if q and q.strip():
        query = query.filter(models.NewsItem.title.ilike(f"%{q.strip()}%"))
    if archived is not None:
        query = query.filter(models.NewsItem.is_archived.is_(archived))
    parsed_from = _parse_date(date_from)
    if parsed_from:
        query = query.filter(order_col >= parsed_from)
    parsed_to = _parse_date(date_to)
    if parsed_to:
        query = query.filter(order_col < parsed_to + datetime.timedelta(days=1))

    total = query.count()
    items = query.order_by(order_col.desc()).limit(min(max(limit, 1), _SEARCH_LIMIT_MAX)).all()
    return schemas.NewsSearchResult(items=[_out(r) for r in items], total=total)


@router.patch("/{news_id}/archive", response_model=schemas.NewsItemOut)
def set_news_archived(news_id: int, payload: schemas.NewsArchiveUpdate, db: Session = Depends(get_db)):
    """뉴스 한 건을 "보관" 처리(또는 해제)한다. 보관 처리된 항목은 발행일
    기준 보관 기간이 지나도 news_service.sync_news의 자동 정리에서
    제외된다."""
    item = db.get(models.NewsItem, news_id)
    if item is None:
        raise HTTPException(status_code=404, detail="해당 뉴스를 찾을 수 없습니다.")
    item.is_archived = payload.is_archived
    db.commit()
    db.refresh(item)
    return _out(item)


@router.post("/sync")
def sync_now(db: Session = Depends(get_db)):
    values = settings_store.get_all(db)
    retention_days = int(values.get("news_retention_days") or 180)
    added = news_service.sync_news(db, news_service.configured_sources(db), retention_days)
    return {"added": added}
