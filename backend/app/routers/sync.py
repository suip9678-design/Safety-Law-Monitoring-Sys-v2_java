from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from .. import content_cache_service, models, schemas, settings_store
from ..database import get_db
from ..law_api import build_client
from ..sync_service import scan_new_admrul, sync_all

router = APIRouter(prefix="/api/sync", tags=["sync"])


@router.post("", response_model=schemas.SyncResult)
def run_sync(db: Session = Depends(get_db)):
    oc = settings_store.get(db, "law_api_oc")
    client = build_client(oc)

    laws_before = db.query(models.TrackedLaw).filter(models.TrackedLaw.is_active.is_(True)).count()
    new_revisions, errors = sync_all(db, client)
    content_cache_service.refresh_tracked_law_content(db, client)

    keywords = [k.strip() for k in settings_store.get(db, "new_admrul_keywords").split(",") if k.strip()]
    department = settings_store.get(db, "new_admrul_department").strip()
    since_date = settings_store.get(db, "new_admrul_since_date").strip()
    try:
        new_candidates = scan_new_admrul(db, client, keywords, department, since_date)
    except Exception as exc:  # noqa: BLE001 - 신규 고시 탐색 실패가 전체 동기화를 막으면 안 됨
        new_candidates = []
        errors.append(f"신규 고시 탐색 실패: {exc}")

    return schemas.SyncResult(
        checked=laws_before,
        new_revisions=len(new_revisions),
        new_admrul_candidates=len(new_candidates),
        errors=errors,
    )
