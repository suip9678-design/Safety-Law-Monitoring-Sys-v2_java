from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from .. import content_cache_service, models, schemas, settings_store
from ..database import get_db
from ..law_api import LawApiError, build_client

router = APIRouter(prefix="/api/laws", tags=["laws"])


@router.get("/search", response_model=list[schemas.LawSearchResult])
def search_laws(
    source_type: str = Query(..., pattern="^(law|admrul)$"),
    query: str = Query(..., min_length=1),
    db: Session = Depends(get_db),
):
    oc = settings_store.get(db, "law_api_oc")
    client = build_client(oc)
    try:
        results = client.search(source_type, query)
    except LawApiError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return results


def _law_with_counts(db: Session, law: models.TrackedLaw) -> schemas.TrackedLawOut:
    out = schemas.TrackedLawOut.model_validate(law)
    out.mapped_document_count = len(law.mappings)
    out.unreviewed_revision_count = sum(1 for r in law.revisions if r.review_status == "미검토")
    return out


@router.get("", response_model=list[schemas.TrackedLawOut])
def list_laws(
    active_only: bool = True,
    source_type: str | None = None,
    db: Session = Depends(get_db),
):
    q = db.query(models.TrackedLaw)
    if active_only:
        q = q.filter(models.TrackedLaw.is_active.is_(True))
    if source_type:
        q = q.filter(models.TrackedLaw.source_type == source_type)
    laws = q.order_by(models.TrackedLaw.name).all()
    return [_law_with_counts(db, law) for law in laws]


@router.post("", response_model=schemas.TrackedLawOut, status_code=201)
def add_law(payload: schemas.TrackedLawCreate, db: Session = Depends(get_db)):
    existing = (
        db.query(models.TrackedLaw)
        .filter(
            models.TrackedLaw.source_type == payload.source_type,
            models.TrackedLaw.external_id == payload.external_id,
        )
        .first()
    )
    if existing and existing.is_active:
        raise HTTPException(status_code=409, detail="이미 추적 중인 법령/고시입니다.")

    if existing:
        # 이전에 추적하다 삭제(비활성화)한 법령을 다시 등록하는 경우. 그 사이
        # 실제로 개정이 있었을 수 있으니 최초 등록과 동일하게 다시 확인
        # 대상으로 취급한다 - last_synced_at을 비워 아래 sync_one()이
        # "최초 확인"으로 처리하게 함(그래야 미검토 이력이 다시 생김).
        law = existing
        law.is_active = True
        law.master_id = payload.master_id
        law.name = payload.name
        law.category = payload.category
        law.department = payload.department
        law.current_promulgation_no = payload.promulgation_no
        law.current_promulgation_date = payload.promulgation_date
        law.current_enforcement_date = payload.enforcement_date
        law.detail_link = payload.detail_link
        law.last_synced_at = None
    else:
        law = models.TrackedLaw(
            source_type=payload.source_type,
            external_id=payload.external_id,
            master_id=payload.master_id,
            name=payload.name,
            category=payload.category,
            department=payload.department,
            # 검색 결과에서 이미 확인된 값으로 바로 채워둔다. 상세 재조회가
            # 실패하더라도 화면에 빈 값이 남지 않도록 하기 위함.
            current_promulgation_no=payload.promulgation_no,
            current_promulgation_date=payload.promulgation_date,
            current_enforcement_date=payload.enforcement_date,
            detail_link=payload.detail_link,
        )
        db.add(law)

    db.commit()
    db.refresh(law)

    oc = settings_store.get(db, "law_api_oc")
    client = build_client(oc)
    try:
        from ..sync_service import sync_one

        sync_one(db, law, client)
        content_cache_service.refresh_tracked_law_content(db, client)
    except LawApiError:
        pass

    db.refresh(law)
    return _law_with_counts(db, law)


@router.post("/new-admrul-candidates/{candidate_id}/dismiss", status_code=204)
def dismiss_new_admrul_candidate(candidate_id: int, db: Session = Depends(get_db)):
    candidate = db.get(models.NewAdmrulCandidate, candidate_id)
    if not candidate:
        raise HTTPException(status_code=404, detail="후보를 찾을 수 없습니다.")
    candidate.status = "무시됨"
    db.commit()
    return None


@router.get("/new-admrul-candidates/dismissed", response_model=list[schemas.NewAdmrulCandidateOut])
def list_dismissed_new_admrul_candidates(db: Session = Depends(get_db)):
    # 한 번 "무시"하면 다음 스캔부터 다시 후보로 안 뜨는데(같은 항목이
    # 계속 재등장하지 않게 하려는 의도), 실수로 무시했거나 나중에 마음이
    # 바뀌어도 화면 어디서도 확인/되돌릴 방법이 없었다 - 이 목록과 아래
    # 복원 기능으로 그걸 보완한다.
    return (
        db.query(models.NewAdmrulCandidate)
        .filter(models.NewAdmrulCandidate.status == "무시됨")
        .order_by(models.NewAdmrulCandidate.first_seen_at.desc())
        .all()
    )


@router.post("/new-admrul-candidates/{candidate_id}/restore", status_code=204)
def restore_new_admrul_candidate(candidate_id: int, db: Session = Depends(get_db)):
    candidate = db.get(models.NewAdmrulCandidate, candidate_id)
    if not candidate:
        raise HTTPException(status_code=404, detail="후보를 찾을 수 없습니다.")
    candidate.status = "신규"
    db.commit()
    return None


@router.post("/new-admrul-candidates/bulk-restore", status_code=204)
def bulk_restore_new_admrul_candidates(
    payload: schemas.BulkNewAdmrulCandidateIds, db: Session = Depends(get_db)
):
    if not payload.ids:
        raise HTTPException(status_code=400, detail="선택된 항목이 없습니다.")
    db.query(models.NewAdmrulCandidate).filter(
        models.NewAdmrulCandidate.id.in_(payload.ids),
        models.NewAdmrulCandidate.status == "무시됨",
    ).update({"status": "신규"}, synchronize_session=False)
    db.commit()
    return None


@router.post("/new-admrul-candidates/{candidate_id}/registered", status_code=204)
def mark_new_admrul_candidate_registered(candidate_id: int, db: Session = Depends(get_db)):
    # 프런트에서 이 후보를 POST /api/laws로 등록한 직후 호출해, 신규 후보
    # 목록에서 사라지게 한다(같은 external_id로는 다시 후보가 안 생김).
    candidate = db.get(models.NewAdmrulCandidate, candidate_id)
    if not candidate:
        raise HTTPException(status_code=404, detail="후보를 찾을 수 없습니다.")
    candidate.status = "등록됨"
    db.commit()
    return None


@router.get("/{law_id}", response_model=schemas.TrackedLawOut)
def get_law(law_id: int, db: Session = Depends(get_db)):
    law = db.get(models.TrackedLaw, law_id)
    if not law:
        raise HTTPException(status_code=404, detail="추적 중인 법령을 찾을 수 없습니다.")
    return _law_with_counts(db, law)


@router.delete("/{law_id}", status_code=204)
def remove_law(law_id: int, db: Session = Depends(get_db)):
    law = db.get(models.TrackedLaw, law_id)
    if not law:
        raise HTTPException(status_code=404, detail="추적 중인 법령을 찾을 수 없습니다.")
    law.is_active = False
    db.commit()
    return None
