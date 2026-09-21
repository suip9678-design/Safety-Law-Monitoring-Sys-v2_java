from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlalchemy.orm import Session

from .. import models, schemas
from ..database import get_db
from .documents import compute_document_impacts
from .revisions import _to_out

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])

# 대시보드 목록들의 안전장치용 상한. 화면에서는 표 영역이 스크롤되도록
# 되어 있어(page-scroll이 아니라 표 안에서만 스크롤) 원래 "전부 다
# 보여준다"는 게 의도인데, 예전에 10건으로 하드코딩되어 있어 실제로는
# 10건 뒤가 잘려 나가고 있었다 - 스크롤을 내려도 더 볼 게 없어서 스크롤
# 기능 자체가 무의미해지는 문제. 사실상 다 보이도록 넉넉하게 올리되,
# 쿼리 자체가 무한정 커지는 건 막기 위해 상한은 남겨둔다.
_DASHBOARD_LIST_LIMIT = 500


@router.get("/summary", response_model=schemas.DashboardSummary)
def summary(db: Session = Depends(get_db)):
    tracked_law_count = db.query(models.TrackedLaw).filter(models.TrackedLaw.is_active.is_(True)).count()

    # 취소(비활성화)한 법령의 개정 이력은 더 이상 추적 대상이 아니므로 대시보드
    # 요약/알람에서 제외한다 - "개정 이력" 탭에는 감사 기록으로 계속 남아있음.
    status_counts = dict(
        db.query(models.LawRevision.review_status, func.count(models.LawRevision.id))
        .join(models.TrackedLaw, models.LawRevision.tracked_law_id == models.TrackedLaw.id)
        .filter(models.TrackedLaw.is_active.is_(True))
        .group_by(models.LawRevision.review_status)
        .all()
    )

    document_count = db.query(models.CompanyDocument).count()

    mapped_law_ids = {row[0] for row in db.query(models.DocumentLawMapping.tracked_law_id).distinct().all()}
    unmapped_query = db.query(models.TrackedLaw).filter(models.TrackedLaw.is_active.is_(True))
    if mapped_law_ids:
        unmapped_query = unmapped_query.filter(~models.TrackedLaw.id.in_(mapped_law_ids))
    unmapped_law_count = unmapped_query.count()

    last_sync = (
        db.query(func.max(models.TrackedLaw.last_synced_at))
        .filter(models.TrackedLaw.is_active.is_(True))
        .scalar()
    )

    # 반영완료/해당없음으로 처리된 건 더 이상 "확인이 필요한 개정"이 아니므로
    # 대시보드에서는 빠진다 - 처리 이력 전체는 "개정 이력" 탭에서 계속 볼 수 있다.
    recent = (
        db.query(models.LawRevision)
        .join(models.TrackedLaw, models.LawRevision.tracked_law_id == models.TrackedLaw.id)
        .filter(models.TrackedLaw.is_active.is_(True))
        .filter(models.LawRevision.review_status.in_(["미검토", "검토중"]))
        .order_by(models.LawRevision.detected_at.desc())
        .limit(_DASHBOARD_LIST_LIMIT)
        .all()
    )

    # 회사 문서 기준으로 재구성: 법령이 아니라 "어떤 절차서/지침서를 검토해야
    # 하는가"를 축으로 보여준다. 아직 처리되지 않은(미검토/검토중) 개정만
    # 대상으로 하고, 전부 반영완료/해당없음 처리되면 그 문서는 목록에서 빠진다.
    # (처리 완료된 것까지 포함한 전체 이력은 "사규 개정 이력" 탭에서 볼 수 있음)
    document_impacts = compute_document_impacts(
        db, statuses=["미검토", "검토중"], limit_docs=_DASHBOARD_LIST_LIMIT, limit_revisions_per_doc=5
    )

    new_admrul_candidates = (
        db.query(models.NewAdmrulCandidate)
        .filter(models.NewAdmrulCandidate.status == "신규")
        .order_by(models.NewAdmrulCandidate.first_seen_at.desc())
        .limit(_DASHBOARD_LIST_LIMIT)
        .all()
    )

    return schemas.DashboardSummary(
        tracked_law_count=tracked_law_count,
        unreviewed_count=status_counts.get("미검토", 0),
        in_review_count=status_counts.get("검토중", 0),
        reflected_count=status_counts.get("반영완료", 0),
        document_count=document_count,
        unmapped_law_count=unmapped_law_count,
        last_sync_at=last_sync,
        recent_revisions=[_to_out(r) for r in recent],
        recent_document_impacts=document_impacts,
        new_admrul_candidates=[
            schemas.NewAdmrulCandidateOut.model_validate(c) for c in new_admrul_candidates
        ],
    )
