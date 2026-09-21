from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import models, schemas
from ..database import get_db

router = APIRouter(prefix="/api/documents", tags=["documents"])


def _to_out(doc: models.CompanyDocument) -> schemas.CompanyDocumentOut:
    out = schemas.CompanyDocumentOut.model_validate(doc)
    out.mapped_law_count = len(doc.mappings)
    out.mapped_laws = [m.tracked_law.name for m in doc.mappings if m.tracked_law]
    return out


def _doc_tags(doc: models.CompanyDocument) -> list[str]:
    if not doc.tags:
        return []
    return [t.strip() for t in doc.tags.split(",") if t.strip()]


def compute_document_impacts(
    db: Session,
    statuses: list[str] | None = None,
    limit_docs: int | None = None,
    limit_revisions_per_doc: int | None = None,
) -> list[schemas.DocumentImpactOut]:
    """법령이 아니라 "어떤 절차서/지침서를 검토해야 하는가"를 축으로 재구성.

    statuses를 주면 그 상태의 개정만 포함하고(대시보드 위젯 - 미검토/검토중만,
    확인이 필요한 것만 보여줌), None이면 전체 상태를 포함한다(사규 개정 이력
    탭 - 처리 완료된 것까지 포함한 전체 이력).

    법령이 포함되는 두 가지 경로:
    - "mapping": 사용자가 문서-법령을 수동으로 매핑해둔 경우(기존 방식).
    - "tag": 문서에 등록된 키워드(해시태그)가, 매핑해두지 않은 법령이라도
      그 법령명이나 본문 캐시(ScrapedLawContent)에 포함되어 있는 경우.
      예: "#밀폐공간"으로 등록해두면, 별도로 매핑하지 않았어도 "밀폐공간"이
      들어간 법령/고시가 개정됐을 때만 그 문서가 뜬다."""
    from .revisions import _to_out as revision_to_out

    active_laws = db.query(models.TrackedLaw).filter(models.TrackedLaw.is_active.is_(True)).all()
    active_laws_by_id = {law.id: law for law in active_laws}

    content_by_key: dict[tuple[str, str], str] = {}
    for row in db.query(models.ScrapedLawContent).all():
        content_by_key[(row.source_type, row.external_id)] = row.content or ""

    def law_haystack(law: models.TrackedLaw) -> str:
        return (law.name or "") + "\n" + content_by_key.get((law.source_type, law.external_id), "")

    docs_with_mapping_ids = {
        row[0] for row in db.query(models.DocumentLawMapping.document_id).distinct().all()
    }
    docs_with_tags_ids = {
        doc.id
        for doc in db.query(models.CompanyDocument)
        .filter(models.CompanyDocument.tags.isnot(None), models.CompanyDocument.tags != "")
        .all()
        if _doc_tags(doc)
    }
    all_doc_ids = docs_with_mapping_ids | docs_with_tags_ids
    if not all_doc_ids:
        return []

    docs = db.query(models.CompanyDocument).filter(models.CompanyDocument.id.in_(all_doc_ids)).all()

    impacts: list[schemas.DocumentImpactOut] = []
    for doc in docs:
        law_matched_by: dict[int, str] = {}
        for mapping in doc.mappings:
            if mapping.tracked_law and mapping.tracked_law.is_active:
                law_matched_by[mapping.tracked_law_id] = "mapping"

        tags = _doc_tags(doc)
        if tags:
            for law in active_laws:
                if law.id in law_matched_by:
                    continue
                haystack = law_haystack(law)
                if any(tag in haystack for tag in tags):
                    law_matched_by[law.id] = "tag"

        if not law_matched_by:
            continue

        pairs = [
            (rev, matched_by)
            for law_id, matched_by in law_matched_by.items()
            for rev in active_laws_by_id[law_id].revisions
            if statuses is None or rev.review_status in statuses
        ]
        if not pairs:
            continue
        pairs.sort(key=lambda pair: pair[0].detected_at, reverse=True)
        if limit_revisions_per_doc:
            pairs = pairs[:limit_revisions_per_doc]

        out_revisions = []
        for rev, matched_by in pairs:
            r_out = revision_to_out(rev)
            r_out.matched_by = matched_by
            out_revisions.append(r_out)

        impacts.append(
            schemas.DocumentImpactOut(
                document_id=doc.id,
                document_title=doc.title,
                doc_type=doc.doc_type,
                revisions=out_revisions,
            )
        )
    impacts.sort(key=lambda d: d.revisions[0].detected_at, reverse=True)
    if limit_docs:
        impacts = impacts[:limit_docs]
    return impacts


@router.get("", response_model=list[schemas.CompanyDocumentOut])
def list_documents(doc_type: str | None = None, db: Session = Depends(get_db)):
    q = db.query(models.CompanyDocument)
    if doc_type:
        q = q.filter(models.CompanyDocument.doc_type == doc_type)
    docs = q.order_by(models.CompanyDocument.title).all()
    return [_to_out(d) for d in docs]


@router.get("/impacts", response_model=list[schemas.DocumentImpactOut])
def list_document_impacts(status: str | None = None, db: Session = Depends(get_db)):
    # "사규 개정 이력" 탭 전용 - 대시보드 위젯과 달리 상태 제한/개수 제한
    # 없이 사규-법령 매핑 기준 전체 이력을 보여준다. status를 주면 그
    # 상태의 개정만 필터링.
    statuses = [status] if status else None
    return compute_document_impacts(db, statuses=statuses)


@router.post("", response_model=schemas.CompanyDocumentOut, status_code=201)
def create_document(payload: schemas.CompanyDocumentCreate, db: Session = Depends(get_db)):
    if payload.doc_type not in models.DOC_TYPES:
        raise HTTPException(status_code=400, detail=f"doc_type은 {models.DOC_TYPES} 중 하나여야 합니다.")
    doc = models.CompanyDocument(**payload.model_dump())
    db.add(doc)
    db.commit()
    db.refresh(doc)
    return _to_out(doc)


@router.get("/{doc_id}", response_model=schemas.CompanyDocumentOut)
def get_document(doc_id: int, db: Session = Depends(get_db)):
    doc = db.get(models.CompanyDocument, doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="문서를 찾을 수 없습니다.")
    return _to_out(doc)


@router.put("/{doc_id}", response_model=schemas.CompanyDocumentOut)
def update_document(doc_id: int, payload: schemas.CompanyDocumentCreate, db: Session = Depends(get_db)):
    doc = db.get(models.CompanyDocument, doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="문서를 찾을 수 없습니다.")
    if payload.doc_type not in models.DOC_TYPES:
        raise HTTPException(status_code=400, detail=f"doc_type은 {models.DOC_TYPES} 중 하나여야 합니다.")
    for key, value in payload.model_dump().items():
        setattr(doc, key, value)
    db.commit()
    db.refresh(doc)
    return _to_out(doc)


@router.delete("/{doc_id}", status_code=204)
def delete_document(doc_id: int, db: Session = Depends(get_db)):
    doc = db.get(models.CompanyDocument, doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="문서를 찾을 수 없습니다.")
    db.delete(doc)
    db.commit()
    return None
