from pathlib import Path

from sqlalchemy import create_engine, text
from sqlalchemy.orm import declarative_base, sessionmaker

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)

DATABASE_URL = f"sqlite:///{DATA_DIR / 'app.db'}"

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False},
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def migrate_schema():
    """Lightweight SQLite migrations for existing app.db files."""
    with engine.begin() as conn:
        columns = {row[1] for row in conn.execute(text("PRAGMA table_info(tasks)"))}
        if not columns:
            return
        if "status" not in columns:
            conn.execute(
                text("ALTER TABLE tasks ADD COLUMN status VARCHAR(32) NOT NULL DEFAULT 'in_progress'")
            )
        if "report" not in columns:
            conn.execute(text("ALTER TABLE tasks ADD COLUMN report TEXT"))
