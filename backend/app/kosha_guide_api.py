"""Client for the 공공데이터포털(data.go.kr) "한국산업안전보건공단_기술지원규정
(코샤가이드) 조회서비스" Open API (제공기관 코드 B552468, 서비스명 koshaguide).

이전에는 같은 제공기관(B552468)의 "안전보건법령 스마트검색" API를 category=7
(KOSHA GUIDE)로 좁혀서 썼었는데, 그 API는 지침번호·제개정일자·원문 링크를
거의 항상 비운 채로 응답해(smartSearch는 법령/고시/미디어 등을 모두 다루는
범용 검색이라 KOSHA GUIDE 전용 필드가 부실하다), "동기화해도 원문을 열어볼
방법이 없다"는 문제가 계속 있었다. 이 API는 KOSHA GUIDE만을 위한 전용
조회서비스라 지침번호·명칭·공표일자·다운로드링크가 모두 정식으로 문서화돼
있고 실제로 채워져서 온다 - 그래서 이 파일은 smartSearch 대신 이 API 하나만
쓴다.

아래는 사용자가 실제로 받은 공식 "오픈API 활용가이드" 문서(한국산업안전보건
공단 기술지원규정(코샤가이드) 조회서비스, 버전 1.0, 서비스 시작일
2025-06-26)로 확인한 값이다:
  - Call Back URL: `http://apis.data.go.kr/B552468/koshaguide/getKoshaGuide`
    (data.go.kr 활용신청 상세페이지의 "서비스 URL" 칸에는
    `.../B552468/koshaguide`까지만 나와 있어, smartSearch 때와 마찬가지로
    뒤에 오퍼레이션 경로(`/getKoshaGuide`)가 빠져 있다 - 활용가이드 문서의
    "Call Back URL"/"요청메시지 예제"에 전체 경로가 나온다.)
  - 요청 파라미터: serviceKey(필수, 인증키), callApiId(필수, 고정값
    "1050"), pageNo(기본 1), numOfRows(기본 10), techGdlnNm(선택, 기술
    지원규정명 검색), techGdlnNo(선택, 지침번호), ofancYmd(선택, 공표일자
    YYYYMMDD). 키워드 없이 페이지만 넘기면 전체 목록을 순서대로 받아올
    수 있다(문서 예제 기준 총 1039건) - smartSearch처럼 검색 키워드 목록을
    미리 설정해둘 필요가 없다.
  - 응답(JSON): smartSearch와 달리 "response" 한 겹 없이
    `{"header": {...}, "body": {...}}`가 최상위에 바로 온다.
    header.resultCode가 "00"이 아니면 오류. body.totalCount(총건수),
    body.items.item[] 각 항목에 techGdlnNm(기술지원규정명),
    techGdlnNo(기술지원규정번호), techGdlnOfancYmd(공표일자,
    "YYYY-MM-DD"), fileDownloadUrl(파일 다운로드 URL, kosha.or.kr 도메인)
    이 온다. "분야"에 해당하는 필드는 이 API에 없어 항상 비어 있다.
  - 공공데이터포털 자체 오류(인증키 오류 등)는 XML(OpenAPI_ServiceResponse
    표준 오류 포맷)로만 온다고 문서에 명시되어 있어, JSON 파싱이 안 되면
    이 포맷으로 다시 시도해 원인을 그대로 보여준다.

동기화 후 KoshaGuide 목록이 비어 있거나 이상하면, 설정 화면에서 "동기화"를
누를 때 실패 원인(오류 응답 본문)이 그대로 화면에 표시된다."""

from __future__ import annotations

import urllib.parse
import xml.etree.ElementTree as ET
from typing import Any

# 회사 네트워크의 SSL 검사 프록시(Windows/macOS 시스템 인증서 저장소는
# 신뢰하지만 Python 기본 certifi 번들에는 없는 사내 루트 CA를 쓰는 경우)
# 때문에 CERTIFICATE_VERIFY_FAILED로 막히는 걸 피하려고 law_api.py와
# 동일하게 OS 인증서 저장소를 신뢰한다.
import truststore

truststore.inject_into_ssl()

import httpx

_client = httpx.Client(timeout=15.0)

# 활용가이드 문서에 "기술지원규정 호출 (필수입력 고정값)"이라고 명시된 값.
_CALL_API_ID = "1050"
# 한 번의 "동기화"에서 끝없이 페이지를 넘기지 않도록 하는 안전장치
# (활용가이드 문서 기준 전체 약 1,000여건이라 100페이지면 충분히 여유있다).
_MAX_PAGES = 100


class KoshaGuideApiError(RuntimeError):
    pass


def _clean(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _normalize_row(row: dict) -> dict | None:
    title = _clean(row.get("techGdlnNm"))
    if not title:
        return None
    issued_date = _clean(row.get("techGdlnOfancYmd"))
    if issued_date:
        issued_date = issued_date.replace("-", "")
    return {
        "code": _clean(row.get("techGdlnNo")),
        "field": None,  # 이 API 응답에는 분야 필드가 없다.
        "title": title,
        "issued_date": issued_date,
        "file_link": _clean(row.get("fileDownloadUrl")),
        "content": None,
    }


def _items_from_body(body: dict) -> list[dict]:
    items = (body or {}).get("items")
    if not isinstance(items, dict):
        return []
    item = items.get("item")
    if item is None:
        return []
    if isinstance(item, list):
        return [x for x in item if isinstance(x, dict)]
    if isinstance(item, dict):
        return [item]
    return []


class KoshaGuideApiClient:
    def __init__(self, service_key: str, base_url: str, timeout: float = 15.0):
        # 공공데이터포털은 인증키를 "Encoding"(이미 URL 퍼센트 인코딩된
        # 형태, 예: 슬래시가 %2F로 표시됨)과 "Decoding"(원본 그대로) 두
        # 가지로 제공한다. httpx는 params에 넣은 값을 URL에 실을 때 항상
        # 다시 인코딩하므로, 사용자가 Encoding 키를 그대로 붙여넣으면
        # "%2F" 안의 "%"까지 또 인코딩돼 "%252F"처럼 이중 인코딩되어
        # 완전히 다른(무효한) 키로 서버에 전달된다. 여기서 한 번 디코딩해
        # 두면, Encoding 키를 붙여넣든 Decoding 키를 붙여넣든 httpx가 그
        # 원본을 정확히 한 번만 인코딩해서 보내므로 어느 쪽을 넣어도 항상
        # 올바르게 동작한다.
        self.service_key = urllib.parse.unquote(service_key)
        self.base_url = base_url
        self.timeout = timeout

    def _request_page(self, page_no: int, num_of_rows: int) -> tuple[list[dict], int]:
        """한 페이지를 조회해 (그 페이지의 정규화된 항목들, 총건수)를 돌려준다."""
        params: dict[str, Any] = {
            "serviceKey": self.service_key,
            "callApiId": _CALL_API_ID,
            "pageNo": page_no,
            "numOfRows": num_of_rows,
        }

        try:
            resp = _client.get(self.base_url, params=params, timeout=self.timeout)
        except httpx.HTTPError as exc:
            raise KoshaGuideApiError(
                f"KOSHA 가이드 조회 API 호출에 실패했습니다: {exc} "
                f"(요청 URL이 맞는지 설정 화면에서 확인해보세요 — 현재: {self.base_url})"
            ) from exc

        if resp.status_code >= 400:
            body_preview = resp.text.strip()
            if len(body_preview) > 500:
                body_preview = body_preview[:500] + "…"
            raise KoshaGuideApiError(
                f"KOSHA 가이드 조회 API가 {resp.status_code} 오류를 반환했습니다: {body_preview or '(응답 본문 없음)'} "
                f"(요청 URL이 맞는지, 인증키가 맞는지 설정 화면에서 확인해보세요 — 현재 요청 URL: {self.base_url})"
            )

        content = resp.content
        stripped = content.lstrip()
        if stripped.startswith(b"{") or stripped.startswith(b"["):
            try:
                data = resp.json()
            except ValueError as exc:
                raise KoshaGuideApiError(f"KOSHA 가이드 조회 API 응답을 해석할 수 없습니다: {exc}") from exc
            header = data.get("header", {}) if isinstance(data, dict) else {}
            result_code = header.get("resultCode")
            if result_code and result_code != "00":
                raise KoshaGuideApiError(
                    f"KOSHA 가이드 조회 API가 오류를 반환했습니다: {header.get('resultMsg') or '(메시지 없음)'} (코드 {result_code})"
                )
            body_data = data.get("body", {}) if isinstance(data, dict) else {}
            rows = [row for row in (_normalize_row(r) for r in _items_from_body(body_data)) if row]
            total_count = int(body_data.get("totalCount") or 0)
            return rows, total_count

        # 공공데이터포털 자체 오류(인증키 오류, 활용신청 안 된 서비스 등)는
        # OpenAPI_ServiceResponse 표준 XML 오류 포맷으로 온다고 문서에
        # 명시되어 있다.
        try:
            root = ET.fromstring(content)
        except ET.ParseError as exc:
            raise KoshaGuideApiError(f"KOSHA 가이드 조회 API 응답을 해석할 수 없습니다: {exc}") from exc
        err_msg = (
            root.findtext(".//returnAuthMsg")
            or root.findtext(".//errMsg")
            or root.findtext(".//resultMsg")
        )
        result_code = root.findtext(".//returnReasonCode") or root.findtext(".//resultCode")
        if err_msg:
            raise KoshaGuideApiError(f"KOSHA 가이드 조회 API가 오류를 반환했습니다: {err_msg} (코드 {result_code or '?'})")
        raise KoshaGuideApiError("KOSHA 가이드 조회 API 응답을 해석할 수 없습니다 (JSON도 오류 XML도 아닌 응답).")

    def list_all(self, num_of_rows: int = 100) -> list[dict]:
        """키워드 없이 페이지를 끝까지 넘겨 KOSHA GUIDE 전체 목록을
        정규화(code/field/title/issued_date/file_link/content)해서 돌려준다."""
        results: list[dict] = []
        page_no = 1
        total_count: int | None = None
        while page_no <= _MAX_PAGES:
            rows, total_count = self._request_page(page_no, num_of_rows)
            results.extend(rows)
            if not rows or page_no * num_of_rows >= total_count:
                break
            page_no += 1
        return results


def build_client(service_key: str, base_url: str) -> KoshaGuideApiClient:
    return KoshaGuideApiClient(service_key, base_url)
