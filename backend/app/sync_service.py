import datetime
import json
import logging

from sqlalchemy.orm import Session

from . import models
from .law_api import LawApiError

logger = logging.getLogger("safety_law_tracker")

# scan_new_admrul()이 키워드 하나당 목록 조회를 몇 건씩/최대 몇 페이지까지
# 훑을지. 2000페이지 * 100건 = 최대 20만 건/키워드(전체 법령 자동 캐시의
# 안전장치와 동일한 규모) - "화학물질" 정도가 아니라 훨씬 흔한 키워드라도
# 현실적으로 이 한도에 걸리지 않는다. 그래도 정말 걸리는 경우를 대비해,
# 조용히 잘라내지 않고 아래에서 경고 로그를 남긴다(더 있을 수 있다는 걸
# 알 수 있게).
_SCAN_PAGE_SIZE = 100
_SCAN_MAX_PAGES = 2000


# ---------- 개별 법령/고시 개정 확인 (sync_one/sync_all) ----------


def _changed(law: models.TrackedLaw, match: dict) -> bool:
    return (
        (match.get("promulgation_no") or None) != law.current_promulgation_no
        or (match.get("promulgation_date") or None) != law.current_promulgation_date
        or (match.get("enforcement_date") or None) != law.current_enforcement_date
    )


def _find_match(law: models.TrackedLaw, results: list[dict]) -> dict | None:
    """Identify which search result corresponds to this tracked law.

    Prefer matching by master_id (법령ID/행정규칙ID) since that stays fixed
    across amendments - this is what lets us notice the 법령일련번호(MST)
    itself has changed, i.e. a real revision. Falls back to matching by the
    currently stored MST (works until the next amendment), then by exact
    name (weakest, for rows added before master_id was tracked).
    """
    if law.master_id:
        for r in results:
            if r.get("master_id") and r["master_id"] == law.master_id:
                return r
    for r in results:
        if r.get("external_id") == law.external_id:
            return r
    for r in results:
        if r.get("name") == law.name:
            return r
    return None


def sync_one(db: Session, law: models.TrackedLaw, client) -> models.LawRevision | None:
    """Re-search for this law/admrul by name and record a revision if its
    current promulgation/enforcement info (or its MST itself) changed since
    the last check. Returns the new LawRevision row, or None if nothing was
    recorded.

    The very first check for a law (law.last_synced_at is still unset) also
    records a "미검토" entry - registering a law for tracking is itself
    something the user should look over once, the same as a real amendment,
    so it must show up on the dashboard until acknowledged. It's
    distinguishable from a genuine revision by having no previous_* values
    (there was nothing to compare against yet)."""

    is_first_check = law.last_synced_at is None

    try:
        results = client.search(law.source_type, law.name)
    finally:
        law.last_synced_at = datetime.datetime.utcnow()

    match = _find_match(law, results)
    if not match:
        db.commit()
        return None

    revision = None

    should_record = (
        bool(match.get("promulgation_date") or match.get("enforcement_date"))
        if is_first_check
        else _changed(law, match)
    )
    if should_record:
        revision = models.LawRevision(
            tracked_law_id=law.id,
            promulgation_no=match.get("promulgation_no"),
            promulgation_date=match.get("promulgation_date"),
            enforcement_date=match.get("enforcement_date"),
            previous_promulgation_no=None if is_first_check else law.current_promulgation_no,
            previous_promulgation_date=None if is_first_check else law.current_promulgation_date,
            previous_enforcement_date=None if is_first_check else law.current_enforcement_date,
            review_status="미검토",
            raw_data=json.dumps(match, ensure_ascii=False),
        )
        db.add(revision)

    if match.get("master_id"):
        law.master_id = match["master_id"]
    if match.get("external_id"):
        law.external_id = match["external_id"]
    if match.get("promulgation_no"):
        law.current_promulgation_no = match["promulgation_no"]
    if match.get("promulgation_date"):
        law.current_promulgation_date = match["promulgation_date"]
    if match.get("enforcement_date"):
        law.current_enforcement_date = match["enforcement_date"]
    if match.get("detail_link"):
        law.detail_link = match["detail_link"]

    db.commit()
    if revision:
        db.refresh(revision)
    return revision


def sync_all(db: Session, client) -> tuple[list[models.LawRevision], list[str]]:
    """Sync every active tracked law. Returns (new_revisions, error_messages)."""

    laws = db.query(models.TrackedLaw).filter(models.TrackedLaw.is_active.is_(True)).all()
    new_revisions: list[models.LawRevision] = []
    errors: list[str] = []

    for law in laws:
        try:
            revision = sync_one(db, law, client)
            if revision:
                new_revisions.append(revision)
        except LawApiError as exc:
            errors.append(f"{law.name}: {exc}")

    return new_revisions, errors


# ---------- 신규 제정 고시 자동 탐지 (scan_new_admrul과 그 정리 로직) ----------


def _active_tracked_admrul_keys(db: Session) -> set[tuple[str, str]]:
    """현재 활성 상태로 추적 중인 행정규칙(admrul)의 (source_type,
    external_id) 집합. "이미 추적 중이라 후보에서 빠져야 하는지"를 판단하는
    기준은 스캔 시점과 유령 후보 정리 시점 둘 다 항상 이 함수로 통일한다 -
    예전에 두 곳에서 각자 조회하다 한쪽에 is_active 조건이 빠져, 삭제
    (비활성화)한 법령이 한쪽 기준에서는 영원히 "추적 중"으로 남아 신규
    탐지에서 다시는 발견되지 않는 버그가 있었다."""
    return {
        (t.source_type, t.external_id)
        for t in db.query(models.TrackedLaw)
        .filter(models.TrackedLaw.source_type == "admrul", models.TrackedLaw.is_active.is_(True))
        .all()
    }


def _delete_and_count(db: Session, rows: list) -> int:
    for row in rows:
        db.delete(row)
    if rows:
        db.commit()
    return len(rows)


def _candidate_matches_filter(
    candidate: models.NewAdmrulCandidate, keywords: list[str], department: str, since_date: str
) -> bool:
    """이 후보가 "지금 설정된" 소관부처+키워드+기준일 조건에 여전히
    맞는지 확인한다(실제 API를 다시 부르지 않고, 이미 저장된 값만으로
    로컬에서 판단 - 처음 찾을 때 쓴 이름/부처/공포일자 기준과 똑같은
    방식으로 비교한다).

    소관부처 필드는 API 응답에서 못 가져와 비어있을 수 있다(law_api.py의
    _FIELD_CANDIDATES 참고 - 실제 응답으로 검증되지 않은 태그명 추정치).
    이 값이 비어있다고 무조건 걸러내면, 데이터 누락 때문에 진짜 맞는
    후보를 놓치게 된다 - since_date 필터가 이미 이 원칙을 따르고 있어(공포일
    정보가 없으면 거르지 않음) 여기도 동일하게 "정보가 있고 안 맞을 때만"
    걸러낸다."""
    if department and candidate.department and department not in candidate.department:
        return False
    if keywords:
        name = candidate.name or ""
        if not any(kw in name for kw in keywords):
            return False
    if since_date and candidate.promulgation_date and candidate.promulgation_date < since_date:
        return False
    return True


def prune_stale_new_admrul_candidates(
    db: Session, keywords: list[str], department: str, since_date: str
) -> int:
    """설정(소관부처/키워드/기준일)을 바꿔 저장했을 때, 이미 찾아둔 "신규"
    후보 중 새 조건에 더는 맞지 않는 것들을 목록에서 지운다. 안 지우면
    예전 설정으로 찾아둔 항목들이 화면에 계속 섞여 보여서, 설정을 바꿔도
    목록이 그대로인 것처럼 오해하기 쉽다(실제로 사용자가 그렇게 겪었다).
    이미 등록했거나 무시한 항목은 대시보드에 안 보이므로(status=="신규"만
    표시) 건드리지 않는다."""
    stale = db.query(models.NewAdmrulCandidate).filter(models.NewAdmrulCandidate.status == "신규").all()
    to_remove = [c for c in stale if not _candidate_matches_filter(c, keywords, department, since_date)]
    return _delete_and_count(db, to_remove)


def prune_orphaned_registered_candidates(db: Session) -> int:
    """대시보드 후보에서 "등록"을 누르면 candidate.status가 "등록됨"으로
    바뀌고(mark_new_admrul_candidate_registered), scan_new_admrul()의
    existing_keys는 상태에 상관없이 모든 후보 행을 다시 만들지 않는
    기준으로 삼는다 - 그래야 등록한 고시가 다시 "신규 후보"로 중복
    등장하지 않는다.

    문제는, 그 뒤 사용자가 "법령 마스터"에서 그 법령을 삭제(비활성화)하면
    TrackedLaw는 더는 추적 대상이 아닌데 candidate.status는 "등록됨"으로
    영원히 남는다는 것 - "무시됨" 상태가 겪었던 것과 똑같이, 이 유령
    행이 existing_keys에 계속 걸려서 재검색해도 다시는 후보로 뜨지
    않는다(대시보드/무시 목록 어디에도 안 보여서 사용자가 원인을 알 방법도
    없었다). 실제로 추적 중인 법령에 대응하는 "등록됨" 후보만 그 상태를
    유지할 이유가 있으므로, 대응하는 TrackedLaw가 더 이상 활성 상태가
    아닌 "등록됨" 후보는 지워서 다음 스캔에서 다시 정상적으로 발견될 수
    있게 한다."""
    tracked_keys = _active_tracked_admrul_keys(db)
    registered = db.query(models.NewAdmrulCandidate).filter(models.NewAdmrulCandidate.status == "등록됨").all()
    to_remove = [c for c in registered if (c.source_type, c.external_id) not in tracked_keys]
    return _delete_and_count(db, to_remove)


def scan_new_admrul(
    db: Session, client, keywords: list[str], department: str, since_date: str = ""
) -> list[models.NewAdmrulCandidate]:
    """소관부처(department) + 키워드(keywords) 이중 필터로 아직 등록하지
    않은 고시/예규/훈령을 찾아 NewAdmrulCandidate로 저장한다.

    고시는 기존 것이 "개정"되는 게 아니라 매년 새로 "제정"되는 경우가 많아
    (기존 TrackedLaw는 새 external_id를 가진 완전히 다른 항목이 됨), 이미
    등록된 항목의 변경만 확인하는 sync_one()으로는 이런 신규 제정을 감지할
    수 없다. 이미 후보로 저장해둔 것(무시했던 것 포함)은 다시 만들지 않아,
    한 번 무시하면 그 항목은 재등장하지 않는다.

    since_date(YYYYMMDD 문자열)를 주면 그보다 이전에 공포된 항목은 후보에서
    제외한다. 이 프로그램을 여러 사용자에게 배포해 서로 다른 시점에
    설치하게 될 경우, 설치 시점 기준 과거의 고시들이 전부 "신규"로 쏟아져
    나오는 걸 막기 위함(설치 시 기준일을 설정해두면 그 이후 것만 보임).
    공포일 정보 자체가 없는 항목은 걸러내지 않는다(데이터 누락으로 진짜
    신규 항목을 놓치지 않기 위해). 소관부처 정보도 마찬가지로, API 응답에
    그 항목이 아예 없으면 걸러내지 않는다(law_api.py의 소관부처 태그명은
    실제 응답으로 검증되지 않았다 - 값이 비어있다고 무조건 걸러내면, 실제로는
    소관부처가 맞는데도 태그명이 달라 값을 못 읽어온 항목까지 영영 후보에서
    빠지게 된다).

    키워드별로 목록 조회를 끝까지 페이지 넘겨가며 훑는다 - 예전에는 첫
    페이지(기본 display=20)만 확인해서, "화학물질"처럼 수십 년 치 고시가
    쌓여 많이 걸리는 키워드는 최신 항목이 그 20건 밖에 있으면 실제로
    법제처에 새 고시가 있어도 영영 발견하지 못하는 문제가 있었다(목록
    조회는 최신순 정렬이 보장되지 않아, 뒷페이지에 최근 것이 있을 수
    있다)."""

    # 새로 스캔하기 전에, 지금 조건에 더 이상 안 맞는 예전 후보부터 먼저
    # 지운다 - 이렇게 해야 existing_keys에서도 빠져서, 지운 항목이라도
    # 지금 조건에 다시 맞는 걸로 밝혀지면(예: 부처는 안 맞았지만 다른
    # 키워드로는 맞는 경우) 아래에서 정상적으로 재발견된다.
    prune_stale_new_admrul_candidates(db, keywords, department, since_date)
    prune_orphaned_registered_candidates(db)

    tracked_keys = _active_tracked_admrul_keys(db)
    existing_keys = {
        (c.source_type, c.external_id) for c in db.query(models.NewAdmrulCandidate).all()
    }

    new_candidates: list[models.NewAdmrulCandidate] = []
    for kw in keywords:
        for page in range(1, _SCAN_MAX_PAGES + 1):
            try:
                results = client.search("admrul", kw, display=_SCAN_PAGE_SIZE, page=page)
            except LawApiError:
                break
            if not results:
                break
            for r in results:
                key = (r.get("source_type") or "admrul", r.get("external_id"))
                if not key[1] or key in tracked_keys or key in existing_keys:
                    continue
                r_department = r.get("department")
                if department and r_department and department not in r_department:
                    continue
                promulgation_date = r.get("promulgation_date")
                if since_date and promulgation_date and promulgation_date < since_date:
                    continue
                candidate = models.NewAdmrulCandidate(
                    source_type=key[0],
                    external_id=key[1],
                    master_id=r.get("master_id"),
                    name=r.get("name") or "",
                    category=r.get("category"),
                    department=r.get("department"),
                    promulgation_no=r.get("promulgation_no"),
                    promulgation_date=r.get("promulgation_date"),
                    enforcement_date=r.get("enforcement_date"),
                    detail_link=r.get("detail_link"),
                    matched_keyword=kw,
                )
                db.add(candidate)
                existing_keys.add(key)
                new_candidates.append(candidate)
            if len(results) < _SCAN_PAGE_SIZE:
                break
        else:
            # for-else: 최대 페이지 수까지 다 돌 때까지 "마지막 페이지"를
            # 못 만났다는 뜻 - 안전장치(_SCAN_MAX_PAGES)에 걸려 중간에
            # 멈춘 것이므로, 조용히 끝난 것처럼 보이지 않게 남긴다(더
            # 남아있을 수 있다는 뜻).
            logger.warning(
                "신규 제정 고시 탐지: 키워드 '%s'가 최대 페이지 수(%d)에 도달해 중단됨(더 남아있을 수 있음)",
                kw, _SCAN_MAX_PAGES,
            )

    if new_candidates:
        db.commit()
        for c in new_candidates:
            db.refresh(c)
    return new_candidates
