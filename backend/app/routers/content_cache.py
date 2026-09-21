from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from .. import content_cache_service, schemas, settings_store
from ..database import SessionLocal, get_db
from ..law_api import build_client

router = APIRouter(prefix="/api/content-cache", tags=["content-cache"])


@router.get("/status")
def get_status(db: Session = Depends(get_db)):
    return content_cache_service.cache_status(db)


def _run_full_refresh():
    db = SessionLocal()
    try:
        oc = settings_store.get(db, "law_api_oc")
        client = build_client(oc)
        content_cache_service.refresh_full_law_content(db, client)
    finally:
        db.close()


@router.post("/full-refresh")
def start_full_refresh(background_tasks: BackgroundTasks):
    # 수천~수만 건을 순회할 수 있어 요청-응답 안에서 끝내지 않고 백그라운드로
    # 돌린다 - 프런트는 /full-refresh-status를 주기적으로 조회해 진행 상황을 본다.
    if content_cache_service.full_cache_status()["running"]:
        raise HTTPException(status_code=409, detail="이미 전체 법령 캐시가 진행 중입니다.")
    background_tasks.add_task(_run_full_refresh)
    return {"started": True}


@router.get("/full-refresh-status")
def get_full_refresh_status():
    return content_cache_service.full_cache_status()


@router.get("/search", response_model=list[schemas.KeywordSearchResult])
def search(
    query: str = Query(..., min_length=1),
    source_type: str = Query("all", pattern="^(all|law|admrul)$"),
    db: Session = Depends(get_db),
):
    return content_cache_service.search_cache(db, source_type, query)


@router.post("/refresh")
def refresh(db: Session = Depends(get_db)):
    oc = settings_store.get(db, "law_api_oc")
    client = build_client(oc)
    keywords = [k.strip() for k in settings_store.get(db, "new_admrul_keywords").split(",") if k.strip()]
    department = settings_store.get(db, "new_admrul_department").strip()
    cached_count = content_cache_service.refresh_candidate_content(db, client, keywords, department)
    return content_cache_service.cache_status(db) | {"refreshed": cached_count}
