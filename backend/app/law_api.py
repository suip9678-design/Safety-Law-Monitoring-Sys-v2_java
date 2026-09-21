"""Client for the 국가법령정보센터(law.go.kr) Open API.

Covers two targets relevant to 산업안전보건 tracking:
  - target=law     : 법률/시행령/시행규칙 등 "법령"
  - target=admrul  : 고시/예규/훈령 등 "행정규칙"

IMPORTANT: this session had no network access to open.law.go.kr while
writing this client, so field extraction below is based on the API's
well-documented public structure but has NOT been verified against a
live response. Field lookup tries several likely tag-name candidates
and falls back to a "search anywhere in the XML tree" strategy for
detail responses, to be resilient to minor naming differences. Once you
have a real OC key, run a manual search (see README "API 확인 방법") and
adjust _FIELD_CANDIDATES below if any field comes back empty.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET

# Trust the OS certificate store (Windows Certificate Store / macOS
# Keychain / Linux system trust) instead of the bundled certifi list.
# Company networks often intercept HTTPS with a corporate root CA that
# Windows itself trusts but Python's default cert bundle does not,
# which otherwise breaks this call with CERTIFICATE_VERIFY_FAILED.
import truststore

truststore.inject_into_ssl()

import httpx

from . import fixtures

LAW_SEARCH_URL = "https://www.law.go.kr/DRF/lawSearch.do"
LAW_SERVICE_URL = "https://www.law.go.kr/DRF/lawService.do"
LAW_SITE_BASE = "https://www.law.go.kr"

# A single, process-wide client so repeated searches reuse the same TLS
# connection (keep-alive) instead of paying a fresh TLS handshake on every
# request. On networks with SSL-inspecting proxies (see truststore above)
# the handshake itself is the slow part, so this materially speeds up
# typing-triggered searches.
_client = httpx.Client(timeout=10.0, limits=httpx.Limits(max_keepalive_connections=5, max_connections=10))

_LIST_ITEM_TAG = {"law": "law", "admrul": "admrul"}

_FIELD_CANDIDATES = {
    "external_id": {
        "law": ["법령일련번호", "MST"],
        "admrul": ["행정규칙일련번호", "ID"],
    },
    "master_id": {
        # 법령ID/행정규칙ID: 개정으로 법령일련번호(MST)가 바뀌어도 고정되는
        # 영구 식별자. 이걸로 "같은 법령의 새 버전"을 찾아낸다.
        "law": ["법령ID"],
        "admrul": ["행정규칙ID"],
    },
    "name": {
        "law": ["법령명한글", "법령명_한글", "법령명"],
        "admrul": ["행정규칙명"],
    },
    "category": {
        "law": ["법령구분명", "법종구분"],
        "admrul": ["행정규칙종류명", "행정규칙종류"],
    },
    "department": {
        "law": ["소관부처명", "소관부처"],
        # "소관부처명" 하나만으로는 실제 응답과 다를 경우 값을 통째로 못
        # 읽어와 소관부처 필터에 걸려 후보가 영영 안 보이는 문제가 있었다
        # (이 세션도 open.law.go.kr에 접근할 수 없어 검증하지 못함) - law와
        # 동일하게 "소관부처"도 후보로 둬 태그명이 다를 가능성에 대비한다.
        "admrul": ["소관부처명", "소관부처"],
    },
    "promulgation_no": {
        "law": ["공포번호"],
        "admrul": ["발령번호"],
    },
    "promulgation_date": {
        "law": ["공포일자"],
        "admrul": ["발령일자"],
    },
    "enforcement_date": {
        "law": ["시행일자"],
        "admrul": ["시행일자"],
    },
    "detail_link": {
        "law": ["법령상세링크"],
        "admrul": ["행정규칙상세링크"],
    },
}


class LawApiError(RuntimeError):
    pass


def _text(elem: ET.Element, tags: list[str]) -> str | None:
    for tag in tags:
        found = elem.find(tag)
        if found is not None and found.text and found.text.strip():
            return found.text.strip()
    return None


def _text_anywhere(root: ET.Element, tags: list[str]) -> str | None:
    for el in root.iter():
        if el.tag in tags and el.text and el.text.strip():
            return el.text.strip()
    return None


# 상세 조회(lawService.do) 응답에서 조문 본문을 모아올 때 후보로 볼 태그들.
# 법령/행정규칙 상세 XML은 조문 단위로 "조문내용"(조 전체 텍스트) 아래에
# 항/호/목이 별도 태그로 쪼개져 나오는 경우가 있어, 조문내용만으로 부족할
# 수 있는 항/호/목 텍스트도 함께 모은다. 이 세션은 open.law.go.kr에 접근할
# 수 없어 실제 응답으로 검증하지 못했다 - 본문 캐시 새로고침 후 내용이
# 비어 있으면 실제 상세 API 응답(XML)을 한 번 확인해 태그명을 조정할 것.
_CONTENT_TAGS = ["조문내용", "항내용", "호내용", "목내용"]

# 조문 하나를 감싸는 단위 태그와, 그 안에서 조번호를 찾는 태그. 실제 조문
# 텍스트(조문내용)에는 "제N조(제목)" 문구가 포함되지 않는 경우가 있어(조
# 번호/제목이 별도 태그로만 존재), 검색어 매칭 위치에서 "제N조" 문자열을
# 텍스트로 역추적하는 방식으로는 조문 링크(법제처 조문 이동 링크)를 만들
# 수 없는 경우가 있었다. 그래서 조문 단위별로 조번호를 명시적으로 앞에
# 붙여서 저장해, 어떤 경우든 본문 캐시 안에서 "제N조" 경계를 찾을 수 있게
# 한다.
_ARTICLE_UNIT_TAG = "조문단위"
_ARTICLE_NO_TAG = "조문번호"
_ARTICLE_SUB_NO_TAG = "조문가지번호"


def _article_label(unit: ET.Element) -> str | None:
    no_text = unit.findtext(_ARTICLE_NO_TAG)
    if not no_text or not no_text.strip().isdigit():
        return None
    label = f"제{int(no_text.strip())}조"
    sub_text = unit.findtext(_ARTICLE_SUB_NO_TAG)
    if sub_text and sub_text.strip().isdigit() and int(sub_text.strip()) > 0:
        label += f"의{int(sub_text.strip())}"
    return label


def _extract_full_text(root: ET.Element) -> tuple[str, int]:
    """조문(본칙) 텍스트는 조문단위별로 조번호를 앞에 붙여 모으고, 별표·
    서식·부칙 등 조문단위 밖에 있는 나머지 본문도 예전 방식(전체 트리
    스캔)대로 빠짐없이 모은다. 조문단위 안에서 이미 모은 요소는 중복으로
    넣지 않는다.

    이전 버전은 조문단위 밖의 텍스트를 통째로 빼먹는 회귀가 있었다(별표에
    있는 내용이 캐시에서 아예 사라짐) - 조문 링크를 만들기 위해 조번호를
    붙이더라도, 본문 캐시 자체의 커버리지는 절대 예전보다 줄어들면 안 된다.

    (content, article_len) 튜플을 돌려준다. article_len은 앞부분 중
    "조문단위에서 나와 조번호 라벨이 붙었을 수 있는" 구간의 길이 - 검색어가
    이 구간 안에서 매칭됐을 때만 조문 링크를 시도해야, 별표처럼 조번호를
    모르는 뒷부분 내용이 엉뚱하게 직전 조문의 링크로 잘못 연결되는 것을
    막을 수 있다(content_cache_service._build_article_link 참고)."""
    parts = []
    covered: set[int] = set()

    for unit in root.iter(_ARTICLE_UNIT_TAG):
        texts = []
        for el in unit.iter():
            if el.tag in _CONTENT_TAGS and el.text and el.text.strip():
                texts.append(el.text.strip())
                covered.add(id(el))
        block = " ".join(texts).strip()
        if not block:
            continue
        label = _article_label(unit)
        # 조문내용 자체에 이미 "제N조" 문구가 들어있는 경우(관행상 흔함)
        # 중복으로 덧붙이지 않는다.
        if label and label not in block[:20]:
            block = f"{label} {block}"
        parts.append(block)

    article_text = "\n".join(parts)
    article_len = len(article_text)

    # 조문단위 밖의 나머지(별표/서식/부칙 등) - 조번호를 알 수 없어 조문
    # 링크 없이(법령 상세 링크로만) 노출되지만, 검색 대상에서는 빠지지 않는다.
    for el in root.iter():
        if el.tag in _CONTENT_TAGS and el.text and el.text.strip() and id(el) not in covered:
            parts.append(el.text.strip())

    return "\n".join(parts), article_len


def _normalize_link(link: str | None) -> str | None:
    if not link:
        return None
    if link.startswith("http://") or link.startswith("https://"):
        return link
    return LAW_SITE_BASE + (link if link.startswith("/") else "/" + link)


def _extract(elem: ET.Element, source_type: str, deep: bool = False) -> dict:
    getter = _text_anywhere if deep else _text
    result: dict = {"source_type": source_type}
    for field, by_type in _FIELD_CANDIDATES.items():
        result[field] = getter(elem, by_type.get(source_type, []))
    result["detail_link"] = _normalize_link(result.get("detail_link"))
    return result


class LawApiClient:
    """Real client backed by the law.go.kr Open API. Requires an OC key."""

    def __init__(self, oc: str, timeout: float = 10.0):
        self.oc = oc
        self.timeout = timeout

    def search(self, source_type: str, query: str, display: int = 20, page: int = 1) -> list[dict]:
        params = {
            "OC": self.oc,
            "target": source_type,
            "type": "XML",
            "query": query,
            "display": display,
            "page": page,
        }
        try:
            resp = _client.get(LAW_SEARCH_URL, params=params, timeout=self.timeout)
            resp.raise_for_status()
        except httpx.HTTPError as exc:
            raise LawApiError(f"법령 검색 API 호출에 실패했습니다: {exc}") from exc

        try:
            root = ET.fromstring(resp.content)
        except ET.ParseError as exc:
            raise LawApiError(f"법령 검색 API 응답을 해석할 수 없습니다: {exc}") from exc

        item_tag = _LIST_ITEM_TAG[source_type]
        items = root.findall(item_tag)
        return [_extract(item, source_type) for item in items]

    def count_total(self, source_type: str, query: str = "") -> int | None:
        """목록 조회 API 응답의 totalCnt를 가져온다(전체 법령 캐시의 진행률
        표시용 - "OO건 중 OO건 캐시함"). display=1로 가볍게 한 번만
        호출한다. 이 세션은 실제 응답으로 태그명을 검증하지 못했다 -
        totalCnt를 못 찾으면 None을 돌려주고, 호출부는 총 건수 없이
        진행 건수만 표시한다(기능 자체가 막히지는 않음)."""
        params = {"OC": self.oc, "target": source_type, "type": "XML", "query": query, "display": 1}
        try:
            resp = _client.get(LAW_SEARCH_URL, params=params, timeout=self.timeout)
            resp.raise_for_status()
            root = ET.fromstring(resp.content)
        except (httpx.HTTPError, ET.ParseError):
            return None
        total_text = root.findtext("totalCnt")
        if not total_text or not total_text.strip().isdigit():
            return None
        return int(total_text.strip())

    def get_detail(self, source_type: str, external_id: str, ef_yd: str | None = None) -> dict | None:
        id_param = "MST" if source_type == "law" else "ID"
        params = {
            "OC": self.oc,
            "target": source_type,
            "type": "XML",
            id_param: external_id,
        }
        if source_type == "law":
            # law.go.kr's lawService.do 404s on target=law without these two
            # params (confirmed against a real response); mobileYn is always
            # required, efYd pins the query to a specific 시행일자 snapshot.
            params["mobileYn"] = ""
            if ef_yd:
                params["efYd"] = ef_yd
        try:
            resp = _client.get(LAW_SERVICE_URL, params=params, timeout=self.timeout)
            resp.raise_for_status()
        except httpx.HTTPError as exc:
            raise LawApiError(f"법령 상세 API 호출에 실패했습니다: {exc}") from exc

        if b"<!DOCTYPE html" in resp.content[:200]:
            raise LawApiError("법령 상세 API가 오류 페이지를 반환했습니다 (파라미터 또는 MST 값을 확인하세요).")

        try:
            root = ET.fromstring(resp.content)
        except ET.ParseError as exc:
            raise LawApiError(f"법령 상세 API 응답을 해석할 수 없습니다: {exc}") from exc

        data = _extract(root, source_type, deep=True)
        if not data.get("name"):
            return None
        data["external_id"] = external_id
        data["content"], data["article_content_len"] = _extract_full_text(root)
        return data


class DemoLawApiClient:
    """Fixture-backed client used when no OC key is configured (DEMO_MODE)."""

    def search(self, source_type: str, query: str, display: int = 20, page: int = 1) -> list[dict]:
        if page > 1:
            # 데모 데이터는 몇 건 안 되니 첫 페이지 안에서 다 끝난다 - 전체
            # 법령 캐시(페이지를 계속 넘기며 끝까지 훑는 기능)를 데모에서
            # 테스트할 때 무한 루프 없이 바로 끝나도록 두 번째 페이지부터는
            # 빈 목록을 돌려준다.
            return []
        return fixtures.search(source_type, query)[:display]

    def count_total(self, source_type: str, query: str = "") -> int | None:
        return len(fixtures.search(source_type, query))

    def get_detail(self, source_type: str, external_id: str, ef_yd: str | None = None) -> dict | None:
        return fixtures.get_detail(source_type, external_id)


def build_client(oc: str):
    if oc:
        return LawApiClient(oc)
    return DemoLawApiClient()
