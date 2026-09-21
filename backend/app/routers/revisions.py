from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
import datetime

from .. import models, schemas
from ..database import get_db

router = APIRouter(prefix="/api/revisions", tags=["revisions"])


def _to_out(rev: models.LawRevision) -> schemas.LawRevisionOut:
    out = schemas.LawRevisionOut.model_validate(rev)
    out.tracked_law_name = rev.tracked_law.name if rev.tracked_law else ""
    out.tracked_law_category = rev.tracked_law.category if rev.tracked_law else None
    out.tracked_law_source_type = rev.tracked_law.source_type if rev.tracked_law else ""
    out.tracked_law_external_id = rev.tracked_law.external_id if rev.tracked_law else None
    out.tracked_law_detail_link = rev.tracked_law.detail_link if rev.tracked_law else None
    out.mapped_documents = (
        [m.document.title for m in rev.tracked_law.mappings] if rev.tracked_law else []
    )
    return out


@router.get("", response_model=list[schemas.LawRevisionOut])
def list_revisions(
    status: str | None = None,
    tracked_law_id: int | None = None,
    has_mapped_documents: bool = False,
    limit: int = 200,
    db: Session = Depends(get_db),
):
    q = db.query(models.LawRevision)
    if status:
        q = q.filter(models.LawRevision.review_status == status)
    if tracked_law_id:
        q = q.filter(models.LawRevision.tracked_law_id == tracked_law_id)
    if has_mapped_documents:
        # "사규 개정 이력" 탭 전용 - 사규(회사 문서)와 매핑된 법령의 개정
        # 이력만 보여준다. 매핑이 하나도 없는 법령의 개정은 여기서 제외.
        mapped_law_ids = db.query(models.DocumentLawMapping.tracked_law_id).distinct()
        q = q.filter(models.LawRevision.tracked_law_id.in_(mapped_law_ids))
    revisions = q.order_by(models.LawRevision.detected_at.desc()).limit(limit).all()
    return [_to_out(r) for r in revisions]


@router.patch("/bulk-status", response_model=list[schemas.LawRevisionOut])
def bulk_update_status(payload: schemas.BulkRevisionStatusUpdate, db: Session = Depends(get_db)):
    if payload.review_status not in models.REVIEW_STATUSES:
        raise HTTPException(status_code=400, detail=f"review_status는 {models.REVIEW_STATUSES} 중 하나여야 합니다.")
    if not payload.ids:
        raise HTTPException(status_code=400, detail="선택된 항목이 없습니다.")

    revisions = db.query(models.LawRevision).filter(models.LawRevision.id.in_(payload.ids)).all()
    now = datetime.datetime.utcnow()
    for rev in revisions:
        rev.review_status = payload.review_status
        rev.reviewed_at = now
    db.commit()
    for rev in revisions:
        db.refresh(rev)
    return [_to_out(r) for r in revisions]


@router.post("/bulk-delete", status_code=204)
def bulk_delete(payload: schemas.BulkRevisionDelete, db: Session = Depends(get_db)):
    if not payload.ids:
        raise HTTPException(status_code=400, detail="선택된 항목이 없습니다.")
    db.query(models.LawRevision).filter(models.LawRevision.id.in_(payload.ids)).delete(
        synchronize_session=False
    )
    db.commit()
    return None


@router.patch("/{revision_id}", response_model=schemas.LawRevisionOut)
def update_revision(revision_id: int, payload: schemas.RevisionUpdate, db: Session = Depends(get_db)):
    rev = db.get(models.LawRevision, revision_id)
    if not rev:
        raise HTTPException(status_code=404, detail="개정 이력을 찾을 수 없습니다.")

    if payload.review_status is not None:
        if payload.review_status not in models.REVIEW_STATUSES:
            raise HTTPException(status_code=400, detail=f"review_status는 {models.REVIEW_STATUSES} 중 하나여야 합니다.")
        rev.review_status = payload.review_status
        rev.reviewed_at = datetime.datetime.utcnow()
    if payload.reviewer is not None:
        rev.reviewer = payload.reviewer
    if payload.note is not None:
        rev.note = payload.note

    db.commit()
    db.refresh(rev)
    return _to_out(rev)
