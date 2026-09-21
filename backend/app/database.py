from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from .config import settings

connect_args = {"check_same_thread": False} if settings.DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(settings.DATABASE_URL, connect_args=connect_args)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _add_column_if_missing(inspector, table: str, column: str, ddl: str) -> bool:
    """table에 column이 없으면 ddl(ALTER TABLE ...)을 실행한다. 실행했으면 True."""
    if table not in inspector.get_table_names():
        return False
    existing = {c["name"] for c in inspector.get_columns(table)}
    if column in existing:
        return False
    with engine.begin() as conn:
        conn.execute(text(ddl))
    return True


def ensure_columns():
    """Lightweight, no-Alembic migration: add any model columns that are
    missing from an existing DB file (Base.metadata.create_all only creates
    missing tables, it never alters existing ones). Call after create_all()."""
    inspector = inspect(engine)
    _add_column_if_missing(inspector, "tracked_laws", "master_id", "ALTER TABLE tracked_laws ADD COLUMN master_id VARCHAR(64)")
    _add_column_if_missing(inspector, "company_documents", "tags", "ALTER TABLE company_documents ADD COLUMN tags VARCHAR(512)")
    _add_column_if_missing(
        inspector, "scraped_law_contents", "article_content_len",
        "ALTER TABLE scraped_law_contents ADD COLUMN article_content_len INTEGER DEFAULT 0",
    )
    _add_column_if_missing(inspector, "news_items", "is_archived", "ALTER TABLE news_items ADD COLUMN is_archived BOOLEAN DEFAULT 0")

    added_content_stale = _add_column_if_missing(
        inspector, "kosha_guides", "content_stale", "ALTER TABLE kosha_guides ADD COLUMN content_stale BOOLEAN DEFAULT 1"
    )
    if added_content_stale:
        # 이미 본문이 채워져 있던 기존 항목은 새로 캐시할 필요가 없다고
        # 간주해 stale=0으로 시작한다 - 그래야 이 업데이트 직후 "본문 캐시
        # 채우기"가 이미 캐시해둔 걸 전부 다시 훑지 않는다.
        with engine.begin() as conn:
            conn.execute(text("UPDATE kosha_guides SET content_stale = 0 WHERE content IS NOT NULL AND content != ''"))
