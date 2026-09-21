"""Sample data used when LAW_API_OC is not configured (DEMO_MODE).

Lets you explore the dashboard - searching, tracking laws, mapping to
company documents - before you have a real law.go.kr Open API key.
Field values are illustrative, not guaranteed to match the real current
text of these laws; once you set LAW_API_OC, real data replaces this.
"""

DEMO_LAWS = [
    {
        "source_type": "law",
        "external_id": "demo-law-001",
        "name": "산업안전보건법",
        "category": "법률",
        "department": "고용노동부",
        "promulgation_no": "제19591호",
        "promulgation_date": "20230816",
        "enforcement_date": "20240517",
        "detail_link": "https://www.law.go.kr/법령/산업안전보건법",
    },
    {
        "source_type": "law",
        "external_id": "demo-law-002",
        "name": "산업안전보건법 시행령",
        "category": "대통령령",
        "department": "고용노동부",
        "promulgation_no": "제34603호",
        "promulgation_date": "20240618",
        "enforcement_date": "20240618",
        "detail_link": "https://www.law.go.kr/법령/산업안전보건법시행령",
    },
    {
        "source_type": "law",
        "external_id": "demo-law-003",
        "name": "산업안전보건법 시행규칙",
        "category": "고용노동부령",
        "department": "고용노동부",
        "promulgation_no": "제417호",
        "promulgation_date": "20240101",
        "enforcement_date": "20240101",
        "detail_link": "https://www.law.go.kr/법령/산업안전보건법시행규칙",
    },
    {
        "source_type": "law",
        "external_id": "demo-law-004",
        "name": "산업안전보건기준에 관한 규칙",
        "category": "고용노동부령",
        "department": "고용노동부",
        "promulgation_no": "제402호",
        "promulgation_date": "20231128",
        "enforcement_date": "20231128",
        "detail_link": "https://www.law.go.kr/법령/산업안전보건기준에관한규칙",
        # 키워드 검색(본문 캐시) 데모용 - 실제 법령 본문 전체가 아니라, 해당
        # 키워드가 조문에 포함되어 있다는 것만 보여주기 위한 예시 발췌문.
        "content": "제241조(화재위험 작업 시의 준수사항) 사업주는 통풍이나 환기가 충분하지 않은 장소에서 화재위험작업(용접·용단 등 불꽃이나 화기를 사용하는 작업)을 하는 경우 화재감시자를 배치하여야 한다.",
    },
    {
        "source_type": "law",
        "external_id": "demo-law-005",
        "name": "중대재해 처벌 등에 관한 법률",
        "category": "법률",
        "department": "법무부",
        "promulgation_no": "제18627호",
        "promulgation_date": "20220126",
        "enforcement_date": "20220127",
        "detail_link": "https://www.law.go.kr/법령/중대재해처벌등에관한법률",
    },
    {
        "source_type": "admrul",
        "external_id": "demo-admrul-001",
        "name": "유해위험방지계획서 제출·심사 및 확인에 관한 규칙",
        "category": "고시",
        "department": "고용노동부",
        "promulgation_no": "고용노동부고시 제2023-31호",
        "promulgation_date": "20230630",
        "enforcement_date": "20230701",
        "detail_link": "https://www.law.go.kr/행정규칙/유해위험방지계획서",
        "content": "제6조(유해위험방지계획서의 내용) 탱크·배관 등의 설비를 해체하거나 정비·보수 작업을 하는 경우로서 화기작업을 수반하는 경우에는 유해위험방지계획서에 화재·폭발 예방대책을 포함하여야 한다.",
    },
    {
        "source_type": "admrul",
        "external_id": "demo-admrul-002",
        "name": "관리감독자 안전보건교육 운영지침",
        "category": "예규",
        "department": "고용노동부",
        "promulgation_no": "고용노동부예규 제220호",
        "promulgation_date": "20220310",
        "enforcement_date": "20220310",
        "detail_link": "https://www.law.go.kr/행정규칙/관리감독자안전보건교육운영지침",
    },
    {
        "source_type": "admrul",
        "external_id": "demo-admrul-003",
        "name": "위험성평가 실시규정",
        "category": "고시",
        "department": "고용노동부",
        "promulgation_no": "고용노동부고시 제2023-19호",
        "promulgation_date": "20230501",
        "enforcement_date": "20230501",
        "detail_link": "https://www.law.go.kr/행정규칙/위험성평가실시규정",
    },
    # 아래 두 건은 "신규 제정 고시 자동 탐지" 데모용 - 아직 등록되지 않은
    # 채로 남겨둬서, 새로고침을 누르면 후보로 잡히는 걸 보여준다.
    {
        "source_type": "admrul",
        "external_id": "demo-admrul-004",
        "name": "밀폐공간 작업 유해위험 방지에 관한 고시",
        "category": "고시",
        "department": "고용노동부",
        "promulgation_no": "고용노동부고시 제2026-4호",
        "promulgation_date": "20260115",
        "enforcement_date": "20260115",
        "detail_link": "https://www.law.go.kr/행정규칙/밀폐공간작업유해위험방지에관한고시",
        "content": "제9조(밀폐공간 화기작업) 밀폐공간에서 화기작업을 실시하는 경우 사전에 가스농도를 측정하고, 화기작업 중에는 지속적으로 환기를 실시하여야 한다.",
    },
    {
        "source_type": "admrul",
        "external_id": "demo-admrul-005",
        "name": "중대재해 예방을 위한 안전보건관리체계 구축 지침",
        "category": "예규",
        "department": "고용노동부",
        "promulgation_no": "고용노동부예규 제245호",
        "promulgation_date": "20260302",
        "enforcement_date": "20260302",
        "detail_link": "https://www.law.go.kr/행정규칙/중대재해예방을위한안전보건관리체계구축지침",
    },
    # 소관부처가 달라서 "고용노동부" 필터에 걸러져야 하는 디코이 - 이중 필터
    # (부처+키워드)가 실제로 부처 조건도 검사하는지 데모에서 확인하기 위함.
    {
        "source_type": "admrul",
        "external_id": "demo-admrul-006",
        "name": "화학물질 취급시설 안전관리에 관한 고시",
        "category": "고시",
        "department": "환경부",
        "promulgation_no": "환경부고시 제2026-11호",
        "promulgation_date": "20260210",
        "enforcement_date": "20260210",
        "detail_link": "https://www.law.go.kr/행정규칙/화학물질취급시설안전관리에관한고시",
    },
]


def search(source_type: str, query: str) -> list[dict]:
    q = (query or "").strip()
    pool = [law for law in DEMO_LAWS if law["source_type"] == source_type]
    if not q:
        return pool
    return [law for law in pool if q in law["name"]]


def get_detail(source_type: str, external_id: str) -> dict | None:
    for law in DEMO_LAWS:
        if law["source_type"] == source_type and law["external_id"] == external_id:
            return law
    return None


# 뉴스 게시판용 예시 데이터. 실제 RSS 피드를 가져오지 못했을 때(네트워크
# 차단, 아직 설정 안 함 등) 화면이 텅 비어 보이지 않도록 채워 넣는 용도라,
# DEMO_LAWS와 달리 LAW_API_OC 설정과는 무관하게 카테고리별 피드 호출이
# 빈 목록을 돌려줄 때마다 쓰인다(news_service.sync_news 참고). guid를
# 고정해두어 반복 동기화해도 중복 저장되지 않는다.
DEMO_NEWS: dict[str, list[dict]] = {
    "moel": [
        {
            "title": "[예시] 고용노동부, 중대재해 예방을 위한 산업안전보건 감독 강화 계획 발표",
            "link": "https://www.moel.go.kr",
            "guid": "demo-news-moel-1",
        },
        {
            "title": "[예시] 고용노동부, 밀폐공간 질식재해 예방 집중 점검 실시",
            "link": "https://www.moel.go.kr",
            "guid": "demo-news-moel-2",
        },
        {
            "title": "[예시] 산업안전보건법 시행규칙 개정안 행정예고",
            "link": "https://www.moel.go.kr",
            "guid": "demo-news-moel-3",
        },
    ],
    "kosha": [
        {
            "title": "[예시] 안전보건공단, 여름철 온열질환 예방 안전보건 가이드 배포",
            "link": "https://www.kosha.or.kr",
            "guid": "demo-news-kosha-1",
        },
        {
            "title": "[예시] 안전보건공단, 건설현장 추락재해 예방 특별 캠페인 실시",
            "link": "https://www.kosha.or.kr",
            "guid": "demo-news-kosha-2",
        },
        {
            "title": "[예시] 안전보건공단, 위험성평가 우수사례 공모전 접수",
            "link": "https://www.kosha.or.kr",
            "guid": "demo-news-kosha-3",
        },
    ],
    "accident": [
        {
            "title": "[예시] 제조업 사업장 끼임 사고로 중대재해 발생, 관계기관 조사 착수",
            "link": "https://www.moel.go.kr",
            "guid": "demo-news-accident-1",
        },
        {
            "title": "[예시] 건설현장 추락사고로 근로자 1명 사망, 원청 안전보건관리체계 점검",
            "link": "https://www.moel.go.kr",
            "guid": "demo-news-accident-2",
        },
        {
            "title": "[예시] 화학물질 누출사고로 인한 중대산업재해 조사 진행",
            "link": "https://www.moel.go.kr",
            "guid": "demo-news-accident-3",
        },
    ],
}


def demo_news(category: str) -> list[dict]:
    return [dict(item, published_at=None) for item in DEMO_NEWS.get(category, [])]
