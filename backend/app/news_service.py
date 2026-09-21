"""고용노동부/안전보건공단 안전보건 이슈, 중대재해 뉴스를 RSS/Atom 피드로
가져와 대시보드 자동 스크롤 게시판에 채워 넣는 서비스.

law_api.py가 국가법령정보센터 API를 다루는 것과 같은 사정으로, 이 세션은
고용노동부(moel.go.kr)/안전보건공단(kosha.or.kr) 공식 사이트에도 접근할 수
없어 두 기관의 공식 RSS 주소를 실제로 검증하지는 못했다. 기본 설정값은
어떤 네트워크 환경에서도 별도 승인 없이 동작하는 구글 뉴스 RSS 검색
(news.google.com/rss/search)으로 채워두었으니, 두 기관의 공식 RSS 주소를
확인하면 설정 탭에서 그 주소로 바꿔 끼우면 된다 - 표준 RSS 2.0(<item>)과
Atom(<entry>) 두 형식을 모두 지원하므로 형식만 맞으면 어떤 피드 URL이든
동작한다.
"""

from __future__ import annotations

import datetime
import email.utils
import logging
import threading
import xml.etree.ElementTree as ET

import httpx
from sqlalchemy import func

from . import fixtures, models

logger = logging.getLogger("safety_law_tracker.news")

# 일부 뉴스 사이트는 브라우저가 아닌 요청(기본 User-Agent 없음)을 차단하므로
# 일반적인 브라우저처럼 보이는 User-Agent를 붙인다.
_client = httpx.Client(
    timeout=10.0,
    headers={"User-Agent": "Mozilla/5.0 (compatible; SafetyLawMonitoringSys/1.0; NewsBoard)"},
)

_ATOM_NS = "{http://www.w3.org/2005/Atom}"

CATEGORY_LABELS: dict[str, str] = {
    "moel": "고용노동부",
    "kosha": "안전보건공단",
    "accident": "중대재해 뉴스",
}


def _parse_pubdate(value: str | None) -> datetime.datetime | None:
    if not value:
        return None
    try:
        dt = email.utils.parsedate_to_datetime(value)  # RSS 2.0 (RFC 822류)
        if dt is not None:
            return dt
    except (TypeError, ValueError):
        pass
    try:
        return datetime.datetime.fromisoformat(value.replace("Z", "+00:00"))  # Atom (ISO 8601)
    except ValueError:
        return None


def fetch_feed(url: str) -> list[dict]:
    """표준 RSS 2.0(<item>) 또는 Atom(<entry>) 피드를 읽어 [{title, link,
    guid, published_at}, ...]를 돌려준다. 실패해도 예외를 던지지 않고 빈
    목록을 돌려준다 - 뉴스 피드 하나가 막혀도 법령 동기화 같은 핵심 기능에
    영향을 주면 안 된다."""
    if not url:
        return []
    try:
        resp = _client.get(url)
        resp.raise_for_status()
        root = ET.fromstring(resp.content)
    except (httpx.HTTPError, ET.ParseError) as exc:
        logger.warning("뉴스 피드를 가져오지 못했습니다 (%s): %s", url, exc)
        return []

    items: list[dict] = []
    for item in root.iter("item"):
        title = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        if not title or not link:
            continue
        guid = (item.findtext("guid") or link).strip()
        items.append({"title": title, "link": link, "guid": guid, "published_at": _parse_pubdate(item.findtext("pubDate"))})

    if not items:
        for entry in root.iter(f"{_ATOM_NS}entry"):
            title = (entry.findtext(f"{_ATOM_NS}title") or "").strip()
            link_el = entry.find(f"{_ATOM_NS}link")
            link = (link_el.get("href") if link_el is not None else "") or ""
            if not title or not link:
                continue
            guid = (entry.findtext(f"{_ATOM_NS}id") or link).strip()
            published = _parse_pubdate(entry.findtext(f"{_ATOM_NS}updated") or entry.findtext(f"{_ATOM_NS}published"))
            items.append({"title": title, "link": link, "guid": guid, "published_at": published})

    return items


def configured_sources(db) -> list[tuple[str, str, str]]:
    """(category, source_name, feed_url) 목록을 설정값에서 구성한다."""
    from . import settings_store

    values = settings_store.get_all(db)
    return [
        ("moel", CATEGORY_LABELS["moel"], values.get("news_source_moel_url", "")),
        ("kosha", CATEGORY_LABELS["kosha"], values.get("news_source_kosha_url", "")),
        ("accident", CATEGORY_LABELS["accident"], values.get("news_source_accident_url", "")),
    ]


# 보관(is_archived) 처리를 해두지 않아도, RSS 주소를 잘못 설정해 한 카테고리에
# 비정상적으로 많은 항목이 몰리는 경우까지 대비한 안전장치. 사용자가 직접
# 조절하는 값이 아니라(보관 기간 설정과는 별개), 디스크가 무한정 커지는 걸
# 막기 위한 최후의 상한선이라 넉넉하게 잡아둔다.
_HARD_CAP_PER_CATEGORY = 5000

# sync_news()는 "이미 있는지 확인 후 없으면 삽입"하는 방식이라, 서버 시작
# 20초 뒤에 자동으로 도는 예약 작업(main.py의 _scheduled_news_sync)과
# 사용자가 대시보드에 들어올 때 트리거되는 백그라운드 재동기화, "지금
# 새로고침" 버튼이 거의 동시에 겹치면 둘 다 "아직 없다"고 확인한 뒤 같은
# guid로 동시에 삽입을 시도해 두 번째 커밋이 UNIQUE 제약 위반(500 에러)으로
# 실패할 수 있었다. 이 앱은 단일 프로세스로 도는 걸 전제하므로(README/여러
# 스크립트 주석 참고), 프로세스 안에서 겹쳐 부르는 것만 막아주면 충분해
# 락으로 직렬화한다 - 그러면 뒤에 들어온 호출은 앞선 호출이 이미 커밋한
# 결과를 보고 "이미 있음"으로 정상적으로 건너뛴다.
_sync_lock = threading.Lock()


def sync_news(db, sources: list[tuple[str, str, str]], retention_days: int) -> int:
    """각 소스를 가져와 새 항목만 저장한다. 돌려주는 값은 신규 저장 건수.

    실제 피드가 비어 있으면(네트워크 차단, 주소 미설정 등) 화면이 텅 비어
    보이지 않도록 fixtures.demo_news()로 채운다. 반대로 실제 데이터가 들어
    오기 시작하면 그 카테고리의 예시 항목은 정리한다."""
    with _sync_lock:
        return _sync_news_locked(db, sources, retention_days)


def _sync_news_locked(db, sources: list[tuple[str, str, str]], retention_days: int) -> int:
    added = 0
    for category, source_name, url in sources:
        fetched = fetch_feed(url)
        is_demo = not fetched
        if is_demo:
            fetched = fixtures.demo_news(category)
        else:
            db.query(models.NewsItem).filter(
                models.NewsItem.category == category, models.NewsItem.is_demo.is_(True)
            ).delete(synchronize_session=False)

        for entry in fetched:
            existing = (
                db.query(models.NewsItem)
                .filter(models.NewsItem.category == category, models.NewsItem.guid == entry["guid"][:512])
                .first()
            )
            if existing:
                continue
            db.add(
                models.NewsItem(
                    category=category,
                    source_name=source_name,
                    title=entry["title"][:512],
                    link=entry["link"][:1024],
                    guid=entry["guid"][:512],
                    published_at=entry.get("published_at"),
                    is_demo=is_demo,
                )
            )
            added += 1
    db.commit()

    # 발행일(published_at, 없으면 fetched_at) 기준으로 보관 기간이 지난
    # 항목은 삭제한다 - 단, "보관" 처리(is_archived)해둔 항목은 기간이
    # 지나도 남겨둔다.
    order_col = func.coalesce(models.NewsItem.published_at, models.NewsItem.fetched_at)
    cutoff = datetime.datetime.utcnow() - datetime.timedelta(days=max(retention_days, 1))
    for category, _source_name, _url in sources:
        stale_ids = [
            row.id
            for row in db.query(models.NewsItem.id)
            .filter(
                models.NewsItem.category == category,
                models.NewsItem.is_archived.is_(False),
                order_col < cutoff,
            )
            .all()
        ]
        if stale_ids:
            db.query(models.NewsItem).filter(models.NewsItem.id.in_(stale_ids)).delete(synchronize_session=False)

        # 안전장치: 보관 기간 안에 있어도 비정상적으로 많이 쌓였다면 오래된 것부터 정리.
        overflow_ids = [
            row.id
            for row in db.query(models.NewsItem.id)
            .filter(models.NewsItem.category == category, models.NewsItem.is_archived.is_(False))
            .order_by(order_col.desc())
            .offset(_HARD_CAP_PER_CATEGORY)
            .all()
        ]
        if overflow_ids:
            db.query(models.NewsItem).filter(models.NewsItem.id.in_(overflow_ids)).delete(synchronize_session=False)
    db.commit()
    return added
