from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .. import models, schemas
from ..database import get_db

router = APIRouter(prefix="/api/mappings", tags=["mappings"])


def _to_out(m: models.DocumentLawMapping) -> schemas.MappingOut:
    out = schemas.MappingOut.model_validate(m)
    out.document_title = m.document.title if m.document else ""
    out.tracked_law_name = m.tracked_law.name if m.tracked_law else ""
    return out


@router.get("", response_model=list[schemas.MappingOut])
def list_mappings(
    document_id: int | None = None,
    tracked_law_id: int | None = None,
    db: Session = Depends(get_db),
):
    q = db.query(models.DocumentLawMapping)
    if document_id:
        q = q.filter(models.DocumentLawMapping.document_id == document_id)
    if tracked_law_id:
        q = q.filter(models.DocumentLawMapping.tracked_law_id == tracked_law_id)
    return [_to_out(m) for m in q.all()]


@router.post("", response_model=schemas.MappingOut, status_code=201)
def create_mapping(payload: schemas.MappingCreate, db: Session = Depends(get_db)):
    if not db.get(models.CompanyDocument, payload.document_id):
        raise HTTPException(status_code=404, detail="문서를 찾을 수 없습니다.")
    if not db.get(models.TrackedLaw, payload.tracked_law_id):
        raise HTTPException(status_code=404, detail="추적 중인 법령을 찾을 수 없습니다.")

    mapping = models.DocumentLawMapping(**payload.model_dump())
    db.add(mapping)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="이미 매핑되어 있습니다.") from exc
    db.refresh(mapping)
    return _to_out(mapping)


@router.delete("/{mapping_id}", status_code=204)
def delete_mapping(mapping_id: int, db: Session = Depends(get_db)):
    mapping = db.get(models.DocumentLawMapping, mapping_id)
    if not mapping:
        raise HTTPException(status_code=404, detail="매핑을 찾을 수 없습니다.")
    db.delete(mapping)
    db.commit()
    return None
