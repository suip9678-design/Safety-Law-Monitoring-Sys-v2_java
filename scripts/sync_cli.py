#!/usr/bin/env python3
"""매일 실행용 동기화 스크립트.

서버를 상시 띄워두지 않고 로컬에서만 쓸 경우, 이 스크립트를 cron/작업
스케줄러에 등록해 매일 자동으로 법령·고시 개정 여부를 확인합니다.

예) crontab -e 에 아래와 같이 등록 (매일 오전 8시 실행):
  0 8 * * * cd /path/to/test-trans/backend && /usr/bin/python3 ../scripts/sync_cli.py >> sync.log 2>&1
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from app import models  # noqa: E402
from app.database import SessionLocal, engine, ensure_columns  # noqa: E402
from app.law_api import build_client  # noqa: E402
from app.sync_service import sync_all  # noqa: E402
from app import settings_store  # noqa: E402


def main() -> int:
    models.Base.metadata.create_all(bind=engine)
    ensure_columns()
    db = SessionLocal()
    try:
        oc = settings_store.get(db, "law_api_oc")
        client = build_client(oc)
        new_revisions, errors = sync_all(db, client)

        print(f"확인 완료: 신규 개정 {len(new_revisions)}건")
        for rev in new_revisions:
            print(f"  - {rev.tracked_law.name}: 공포 {rev.promulgation_date}, 시행 {rev.enforcement_date}")

        if errors:
            print("오류:")
            for err in errors:
                print(f"  - {err}")
            return 1
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
