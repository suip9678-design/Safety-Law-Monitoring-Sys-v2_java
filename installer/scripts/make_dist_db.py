"""현재 backend DB에서 "법령 마스터"(추적 법령/개정 이력/사규 매핑)를 뺀 배포용 DB를 만든다.

사용법: make_dist_db.py <원본 DB> <출력 DB>
sqlite backup API로 복사하므로 서버가 켜져 있어도 안전하다.
사규, KOSHA 가이드, 뉴스, 본문 캐시, 설정(API 키 포함)은 그대로 남는다.
받는 PC에서 첫 실행 도움말이 뜨고 유지보수가 바로 돌도록 두 표시값만 지운다.
"""
import sqlite3
import sys

src, dst = sys.argv[1], sys.argv[2]
a = sqlite3.connect(src)
b = sqlite3.connect(dst)
a.backup(b)
a.close()
for t in ("document_law_mappings", "law_revisions", "tracked_laws"):
    b.execute(f"DELETE FROM {t}")
b.execute("DELETE FROM app_settings WHERE key IN ('last_daily_maintenance_at', 'help_shown_once')")
b.commit()
b.execute("VACUUM")
for t in ("tracked_laws", "company_documents", "scraped_law_contents", "kosha_guides", "news_items"):
    print(f"  {t}: {b.execute(f'SELECT COUNT(*) FROM {t}').fetchone()[0]}건")
b.close()
