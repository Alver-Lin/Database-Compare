import sqlite3
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)

SOURCE = DATA_DIR / "demo_source.db"
TARGET = DATA_DIR / "demo_target.db"


def write_db(path: Path, statements: list[str], rows: dict[str, list[tuple]]):
    if path.exists():
        path.unlink()
    conn = sqlite3.connect(path)
    try:
        cur = conn.cursor()
        for sql in statements:
            cur.execute(sql)
        for table, items in rows.items():
            for item in items:
                placeholders = ",".join("?" * len(item))
                cur.execute(f"INSERT INTO {table} VALUES ({placeholders})", item)
        conn.commit()
    finally:
        conn.close()


write_db(
    SOURCE,
    [
        """
        CREATE TABLE users (
            id INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            email TEXT,
            created_at TEXT
        )
        """,
        """
        CREATE TABLE orders (
            id INTEGER PRIMARY KEY,
            user_id INTEGER,
            amount REAL,
            status TEXT
        )
        """,
        """
        CREATE TABLE products (
            id INTEGER PRIMARY KEY,
            name TEXT,
            price REAL
        )
        """,
    ],
    {
        "users": [
            (1, "Alice", "alice@example.com", "2026-01-01"),
            (2, "Bob", "bob@example.com", "2026-02-01"),
            (3, "Carol", "carol@example.com", "2026-03-01"),
        ],
        "orders": [
            (1, 1, 99.0, "paid"),
            (2, 2, 12.5, "pending"),
            (3, 1, 40.0, "paid"),
        ],
        "products": [
            (1, "Keyboard", 199.0),
            (2, "Mouse", 79.0),
        ],
    },
)

write_db(
    TARGET,
    [
        """
        CREATE TABLE users (
            id INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            email TEXT,
            phone TEXT,
            created_at TEXT
        )
        """,
        """
        CREATE TABLE orders (
            id INTEGER PRIMARY KEY,
            user_id INTEGER,
            amount REAL,
            status TEXT
        )
        """,
        """
        CREATE TABLE goods (
            id INTEGER PRIMARY KEY,
            name TEXT,
            price REAL
        )
        """,
    ],
    {
        "users": [
            (1, "Alice", "alice@example.com", "13800000001", "2026-01-01"),
            (2, "Bob", "bob@example.com", "13800000002", "2026-02-01"),
            (4, "Dave", "dave@example.com", "13800000004", "2026-04-01"),
        ],
        "orders": [
            (1, 1, 99.0, "paid"),
            (2, 2, 12.5, "pending"),
            (3, 1, 40.0, "paid"),
            (4, 4, 18.0, "cancelled"),
        ],
        "goods": [
            (1, "Keyboard", 199.0),
            (2, "Mouse", 79.0),
            (3, "Monitor", 899.0),
        ],
    },
)

print(f"source: {SOURCE}")
print(f"target: {TARGET}")
