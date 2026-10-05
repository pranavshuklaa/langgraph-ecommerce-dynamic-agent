from pathlib import Path
import sqlite3


ROOT = Path(__file__).resolve().parents[2]

DB_PATH = ROOT / "ecommerce.db"
SQL_SEED_PATH = ROOT / "ecommerce_setup.sql"


def init_database():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)

    sql_script = SQL_SEED_PATH.read_text(encoding="utf-8")

    with sqlite3.connect(DB_PATH) as conn:
        conn.executescript(sql_script)
        conn.commit()

    return DB_PATH


def main():
    db_path = init_database()
    print(f"Database initialized at: {db_path}")


if __name__ == "__main__":
    main()