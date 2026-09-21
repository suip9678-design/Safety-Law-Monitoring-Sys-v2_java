"""KOSHA GUIDE(안전보건공단 기술지침) 라이브러리 - 등록/검색.

공공데이터포털 API 동기화(kosha_guide_api.py)나 사용자가 직접 입력/
붙여넣기(일괄 등록)로 지침번호·제목·원문 링크를 채운다. 다만 그 어느
경로로도 본문 텍스트 자체는 오지 않으므로(API는 메타데이터만, 실제 내용은
file_link가 가리키는 PDF 안에 있음), "본문 검색"이 진짜 내용까지 찾아
미리보기를 보여주게 하려면 PDF에서 텍스트를 뽑아 content에 저장해두는
과정이 따로 필요하다 - 그 추출은 kosha_guide_pdf.py가 맡는다."""

import re
import urllib.parse
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query, Response, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from .. import kosha_guide_pdf, models, schemas, settings_store
from ..content_cache_service import _snippet
from ..config import settings
from ..database import get_db
from ..kosha_guide_api import KoshaGuideApiError, build_client

router = APIRouter(prefix="/api/kosha-guides", tags=["kosha-guides"])

_FILE_SERVE_URL_PREFIX = "/api/kosha-guides/"
_FILE_SERVE_URL_SUFFIX = "/file"


def _uploaded_file_path(guide_id: int) -> Path:
    return settings.KOSHA_GUIDE_FILES_DIR / f"{guide_id}.pdf"


def _served_file_url(guide_id: int) -> str:
    return f"{_FILE_SERVE_URL_PREFIX}{guide_id}{_FILE_SERVE_URL_SUFFIX}"


_SERVED_FILE_URL_RE = re.compile(r"^/api/kosha-guides/(\d+)/file$")


def _extract_content_for_guide(guide: "models.KoshaGuide") -> str | None:
    """가이드의 file_link가 가리키는 PDF에서 본문 텍스트를 뽑아온다. 이
    서버가 직접 서빙 중인(수동 첨부한) 파일이면 네트워크 왕복 없이
    디스크에서 바로 읽고, 외부 URL(API 동기화로 받아온 kosha.or.kr
    다운로드 링크 등)이면 내려받아서 처리한다."""
    link = guide.file_link or ""
    served_match = _SERVED_FILE_URL_RE.match(link)
    if served_match:
        path = _uploaded_file_path(int(served_match.group(1)))
        if not path.exists():
            return None
        return kosha_guide_pdf.extract_pdf_text(path.read_bytes())
    if link.startswith("http://") or link.startswith("https://"):
        return kosha_guide_pdf.download_and_extract(link)
    return None


def _clean(value: str | None) -> str | None:
    value = (value or "").strip()
    return value or None


def _check_code_conflict(db: Session, code: str | None, exclude_id: int | None = None) -> None:
    if not code:
        return
    q = db.query(models.KoshaGuide).filter(models.KoshaGuide.code == code)
    if exclude_id is not None:
        q = q.filter(models.KoshaGuide.id != exclude_id)
    if q.first():
        raise HTTPException(status_code=409, detail=f"이미 등록된 지침번호입니다: {code}")


@router.get("", response_model=list[schemas.KoshaGuideOut])
def list_guides(field: str | None = None, db: Session = Depends(get_db)):
    q = db.query(models.KoshaGuide)
    if field:
        q = q.filter(models.KoshaGuide.field == field)
    return q.order_by(models.KoshaGuide.title).all()


@router.get("/search", response_model=list[schemas.KoshaGuideSearchResult])
def search_guides(query: str = Query(..., min_length=1), db: Session = Depends(get_db)):
    needle = query.strip()
    results: list[schemas.KoshaGuideSearchResult] = []
    for row in db.query(models.KoshaGuide).all():
        content = row.content or ""
        title = row.title or ""
        code = row.code or ""
        idx = content.find(needle)
        if idx != -1:
            matched_in = "content"
            snippet = _snippet(content, idx, len(needle))
        elif needle in title:
            matched_in = "title"
            snippet = ""
        elif needle in code:
            matched_in = "code"
            snippet = ""
        else:
            continue
        results.append(
            schemas.KoshaGuideSearchResult(
                id=row.id,
                code=row.code,
                field=row.field,
                title=row.title,
                issued_date=row.issued_date,
                file_link=row.file_link,
                matched_in=matched_in,
                snippet=snippet,
                content=content,
            )
        )
    return results


@router.post("", response_model=schemas.KoshaGuideOut, status_code=201)
def create_guide(payload: schemas.KoshaGuideCreate, db: Session = Depends(get_db)):
    title = payload.title.strip()
    if not title:
        raise HTTPException(status_code=400, detail="제목은 비워둘 수 없습니다.")
    code = _clean(payload.code)
    _check_code_conflict(db, code)
    guide = models.KoshaGuide(
        code=code,
        field=_clean(payload.field),
        title=title,
        issued_date=_clean(payload.issued_date),
        file_link=_clean(payload.file_link),
        content=payload.content or None,
        content_stale=not bool(payload.content),
        note=payload.note or None,
    )
    db.add(guide)
    db.commit()
    db.refresh(guide)
    return guide


@router.put("/{guide_id}", response_model=schemas.KoshaGuideOut)
def update_guide(guide_id: int, payload: schemas.KoshaGuideCreate, db: Session = Depends(get_db)):
    guide = db.get(models.KoshaGuide, guide_id)
    if not guide:
        raise HTTPException(status_code=404, detail="가이드를 찾을 수 없습니다.")
    title = payload.title.strip()
    if not title:
        raise HTTPException(status_code=400, detail="제목은 비워둘 수 없습니다.")
    code = _clean(payload.code)
    _check_code_conflict(db, code, exclude_id=guide_id)
    new_file_link = _clean(payload.file_link)
    link_changed = new_file_link != guide.file_link
    guide.code = code
    guide.field = _clean(payload.field)
    guide.title = title
    guide.issued_date = _clean(payload.issued_date)
    guide.file_link = new_file_link
    guide.note = payload.note or None
    if payload.content:
        guide.content = payload.content
        guide.content_stale = False
    elif link_changed:
        # 원문 링크를 새로 바꿨는데 본문은 같이 안 채워줬다 - 예전 링크
        # 기준의 본문을 그대로 남겨두면 새 링크와 안 맞을 수 있으니 비우고
        # "본문 캐시 채우기" 대상으로 다시 표시한다.
        guide.content = None
        guide.content_stale = bool(new_file_link)
    db.commit()
    db.refresh(guide)
    return guide


@router.delete("/{guide_id}", status_code=204)
def delete_guide(guide_id: int, db: Session = Depends(get_db)):
    guide = db.get(models.KoshaGuide, guide_id)
    if not guide:
        raise HTTPException(status_code=404, detail="가이드를 찾을 수 없습니다.")
    db.delete(guide)
    db.commit()
    _uploaded_file_path(guide_id).unlink(missing_ok=True)
    return None


@router.post("/{guide_id}/file", response_model=schemas.KoshaGuideOut)
def upload_guide_file(guide_id: int, file: UploadFile, db: Session = Depends(get_db)):
    """API 동기화가 원문 링크를 못 채워온 가이드에, 사용자가 PDF를 직접
    올려 첨부한다. 파일은 이 서버(사내 PC/서버)의 로컬 폴더에만 저장되고
    외부로 전송되지 않으며, 이후 이 가이드의 "원문 링크"는 그 파일을
    서빙하는 이 서버 자신의 주소(/api/kosha-guides/{id}/file)가 된다."""
    guide = db.get(models.KoshaGuide, guide_id)
    if not guide:
        raise HTTPException(status_code=404, detail="가이드를 찾을 수 없습니다.")
    filename = (file.filename or "").lower()
    if file.content_type not in ("application/pdf", "application/x-pdf") and not filename.endswith(".pdf"):
        raise HTTPException(status_code=400, detail="PDF 파일만 첨부할 수 있습니다.")
    data = file.file.read()
    _uploaded_file_path(guide_id).write_bytes(data)
    guide.file_link = _served_file_url(guide_id)
    # 업로드한 김에 본문도 바로 추출해둔다 - 이미 브라우저에서 받은
    # 바이트가 메모리에 있으니 추가 다운로드 없이 바로 처리할 수 있다.
    # 스캔 이미지 PDF 등 텍스트 추출이 안 되는 경우는 조용히 건너뛴다.
    # 이 파일로는 이게 최종 시도이므로(로컬 파일이라 나중에 다시 해봐도
    # 결과가 똑같다), 성공/실패 어느 쪽이든 "본문 캐시 채우기" 대상에서는
    # 빼둔다 - 실패한 경우는 다른 PDF로 다시 첨부해야 해결된다.
    extracted = kosha_guide_pdf.extract_pdf_text(data)
    if extracted:
        guide.content = extracted
    guide.content_stale = False
    db.commit()
    db.refresh(guide)
    return guide


@router.get("/{guide_id}/file")
def download_guide_file(guide_id: int, db: Session = Depends(get_db)):
    guide = db.get(models.KoshaGuide, guide_id)
    if not guide:
        raise HTTPException(status_code=404, detail="가이드를 찾을 수 없습니다.")
    path = _uploaded_file_path(guide_id)
    if not path.exists():
        raise HTTPException(status_code=404, detail="첨부된 파일이 없습니다.")
    return FileResponse(path, media_type="application/pdf", filename=f"{guide.title}.pdf")


@router.get("/{guide_id}/original")
def open_guide_original(guide_id: int, db: Session = Depends(get_db)):
    """가이드의 "원문"을 연다 - 로컬에 첨부해둔 PDF면 그 파일을 그대로
    서빙하고, 외부 URL(API 동기화로 받아온 kosha.or.kr 다운로드 링크 등)
    이면 이 서버가 대신 받아서 전달한다.

    브라우저가 kosha.or.kr 다운로드 링크로 직접 들어가면 일부 파일에서
    ERR_RESPONSE_HEADERS_MULTIPLE_CONTENT_DISPOSITION로 아예 열리지 않는
    경우가 있다(그쪽 서버가 Content-Disposition 헤더를 중복으로 보내는
    문제로 보인다) - 이 서버가 대신 받아 헤더를 새로 정리해서 내려주면
    이 문제를 피할 수 있어, 제목/미리보기의 "원문 열기"는 항상 여기를
    거치도록 한다."""
    guide = db.get(models.KoshaGuide, guide_id)
    if not guide or not guide.file_link:
        raise HTTPException(status_code=404, detail="원문 링크가 없습니다.")
    served_match = _SERVED_FILE_URL_RE.match(guide.file_link)
    if served_match:
        return download_guide_file(int(served_match.group(1)), db)
    if not guide.file_link.startswith(("http://", "https://")):
        raise HTTPException(status_code=400, detail="원문 링크 형식을 확인할 수 없습니다.")
    try:
        data, content_type = kosha_guide_pdf.fetch_original(guide.file_link)
    except kosha_guide_pdf.KoshaGuideFileError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    # HTTP 헤더 값은 latin-1만 허용되어, 제목이 한글(대부분의 경우)이면
    # 그대로 filename="..."에 넣다가는 UnicodeEncodeError로 서버가 죽는다.
    # FileResponse가 하는 것과 같은 방식(RFC 5987 filename*=utf-8''...)으로
    # 직접 인코딩해야 한다 - Response는 이 처리를 자동으로 해주지 않는다.
    filename = f"{guide.title}.pdf"
    encoded_filename = urllib.parse.quote(filename)
    content_disposition = (
        f"inline; filename*=utf-8''{encoded_filename}"
        if encoded_filename != filename
        else f'inline; filename="{filename}"'
    )
    return Response(
        content=data,
        media_type=content_type,
        headers={"Content-Disposition": content_disposition},
    )


@router.delete("/{guide_id}/file", response_model=schemas.KoshaGuideOut)
def delete_guide_file(guide_id: int, db: Session = Depends(get_db)):
    guide = db.get(models.KoshaGuide, guide_id)
    if not guide:
        raise HTTPException(status_code=404, detail="가이드를 찾을 수 없습니다.")
    _uploaded_file_path(guide_id).unlink(missing_ok=True)
    if guide.file_link == _served_file_url(guide_id):
        guide.file_link = None
        db.commit()
        db.refresh(guide)
    return guide


@router.post("/bulk-delete", status_code=204)
def bulk_delete_guides(payload: schemas.KoshaGuideBulkDelete, db: Session = Depends(get_db)):
    if not payload.ids:
        raise HTTPException(status_code=400, detail="선택된 항목이 없습니다.")
    db.query(models.KoshaGuide).filter(models.KoshaGuide.id.in_(payload.ids)).delete(synchronize_session=False)
    db.commit()
    for guide_id in payload.ids:
        _uploaded_file_path(guide_id).unlink(missing_ok=True)
    return None


def _upsert(db: Session, code: str | None, field: str | None, title: str, issued_date: str | None,
            file_link: str | None, content: str | None = None) -> str:
    """지침번호(code)가 있고 이미 등록된 것과 같으면 덮어쓰고("updated"),
    아니면 새로 추가한다("added"). bulk-import와 sync가 함께 쓴다.

    code가 없으면 제목(title)으로 대신 매칭한다 - 공공데이터포털 스마트검색
    API는 지침번호를 거의 항상 비워서 응답하는데(kosha_guide_api.py 상단
    설명 참고), code로만 매칭하면 "이미 등록된 것과 같은지"를 절대 알 수
    없어 동기화를 누를 때마다 같은 가이드가 계속 새로 쌓이는 문제가 있었다.
    사용자가 수동으로 첨부해둔 file_link(PDF 첨부)는 API 재동기화로 다시
    비워지지 않도록, 새 값이 없을 때는 기존 값을 그대로 유지한다.

    원문 링크가 실제로 바뀐 경우(=개정으로 새 PDF가 올라온 경우)만
    content_stale을 세워 "본문 캐시 채우기"의 재처리 대상으로 표시한다 -
    링크가 그대로인 항목은 이미 캐시해둔 본문이 여전히 맞으므로 매번
    다시 내려받지 않고 건너뛴다."""
    q = db.query(models.KoshaGuide).filter(models.KoshaGuide.code == code) if code \
        else db.query(models.KoshaGuide).filter(models.KoshaGuide.code.is_(None), models.KoshaGuide.title == title)
    existing = q.first()
    if existing:
        existing.field = field
        existing.title = title
        existing.issued_date = issued_date
        link_changed = bool(file_link) and file_link != existing.file_link
        if file_link:
            existing.file_link = file_link
        if content:
            existing.content = content
            existing.content_stale = False
        elif link_changed:
            existing.content_stale = True
        return "updated"
    db.add(
        models.KoshaGuide(
            code=code, field=field, title=title, issued_date=issued_date, file_link=file_link,
            content=content, content_stale=not bool(content),
        )
    )
    return "added"


@router.post("/bulk-import", response_model=schemas.KoshaGuideBulkImportResult)
def bulk_import(payload: schemas.KoshaGuideBulkImportItems, db: Session = Depends(get_db)):
    """붙여넣기로 여러 건을 한 번에 등록한다. 지침번호(code)가 있고 이미
    등록된 것과 같으면 그 항목을 덮어쓰고(같은 목록을 다시 붙여넣어도
    중복 생성되지 않게), 지침번호가 없거나 새 값이면 새로 추가한다."""
    added = updated = skipped = 0
    for item in payload.items:
        title = (item.title or "").strip()
        if not title:
            skipped += 1
            continue
        outcome = _upsert(
            db, _clean(item.code), _clean(item.field), title, _clean(item.issued_date),
            _clean(item.file_link), item.content or None,
        )
        if outcome == "updated":
            updated += 1
        else:
            added += 1
    db.commit()
    return schemas.KoshaGuideBulkImportResult(added=added, updated=updated, skipped=skipped)


@router.post("/sync", response_model=schemas.KoshaGuideSyncResult)
def sync_from_api(db: Session = Depends(get_db)):
    """설정에 저장해둔 공공데이터포털 인증키로 "기술지원규정(코샤가이드)
    조회서비스"(kosha_guide_api.py 상단 설명 참고) 전체 목록을 페이지를
    넘겨가며 받아와 등록/갱신한다. 이 API는 KOSHA GUIDE 전용이라 검색
    키워드를 미리 등록해둘 필요 없이 전체를 한 번에 받아올 수 있다."""
    values = settings_store.get_all(db)
    service_key = values.get("kosha_guide_api_key", "").strip()
    if not service_key:
        raise HTTPException(status_code=400, detail="설정에서 KOSHA 가이드 Open API 인증키를 먼저 저장하세요.")
    base_url = values.get("kosha_guide_api_url", "").strip()
    if not base_url:
        raise HTTPException(status_code=400, detail="설정에서 KOSHA 가이드 Open API 요청 URL을 먼저 저장하세요.")

    client = build_client(service_key, base_url)
    found = added = updated = 0
    errors: list[str] = []
    try:
        results = client.list_all()
    except KoshaGuideApiError as exc:
        errors.append(str(exc))
        results = []

    for item in results:
        title = (item.get("title") or "").strip()
        if not title:
            continue
        found += 1
        outcome = _upsert(
            db, _clean(item.get("code")), _clean(item.get("field")), title,
            _clean(item.get("issued_date")), _clean(item.get("file_link")),
            item.get("content") or None,
        )
        if outcome == "updated":
            updated += 1
        else:
            added += 1
    db.commit()
    return schemas.KoshaGuideSyncResult(found=found, added=added, updated=updated, errors=errors)


def _content_pending_query(db: Session):
    # content_stale은 "원문 링크는 있는데 아직 그 링크 기준으로 캐시를
    # 못(안) 한 상태"를 뜻한다 - 새로 만들어진 항목은 기본 True, 링크가
    # 안 바뀐 채 재동기화된 항목은 False로 남아 매번 다시 처리되지 않고
    # 건너뛴다(_upsert 설명 참고).
    return (
        db.query(models.KoshaGuide)
        .filter(models.KoshaGuide.file_link.isnot(None))
        .filter(models.KoshaGuide.content_stale.is_(True))
    )


@router.post("/cache-content", response_model=schemas.KoshaGuideContentCacheResult)
def cache_content(limit: int = 20, db: Session = Depends(get_db)):
    """원문 링크(file_link)는 있지만 아직 캐시되지 않았거나(신규) 링크가
    바뀌어 다시 캐시해야 하는(개정) 가이드를 최대 limit건 골라 PDF에서
    텍스트를 뽑아 저장한다 - "본문 검색"이 실제 내용까지 찾아 미리보기를
    보여주려면 이 캐시가 있어야 한다. 이미 캐시해뒀고 그 뒤로 링크가
    바뀌지 않은 항목은 건너뛴다. 외부 PDF를 매번 새로 내려받아야 해서
    한 번에 너무 많이 처리하면 오래 걸리므로, 한 번 호출에 처리할 건수를
    제한해두고 남은 건수를 함께 돌려준다 - 프론트엔드가 remaining이
    0이 될 때까지(또는 진행이 멈출 때까지) 이 엔드포인트를 반복 호출해
    끝까지 채운다."""
    candidates = _content_pending_query(db).limit(max(1, min(limit, 100))).all()
    processed = succeeded = failed = 0
    for guide in candidates:
        processed += 1
        text = _extract_content_for_guide(guide)
        if text:
            guide.content = text
            guide.content_stale = False
            succeeded += 1
        else:
            # 실패 원인(끊긴 링크, 일시적 네트워크 오류, 텍스트가 없는
            # 스캔본 등)을 구분할 수 없으니 stale로 남겨 다음 호출에서
            # 다시 시도해볼 수 있게 한다.
            failed += 1
    db.commit()
    remaining = _content_pending_query(db).count()
    return schemas.KoshaGuideContentCacheResult(
        processed=processed, succeeded=succeeded, failed=failed, remaining=remaining,
    )
