from pathlib import Path
import sqlite3
from typing import TypedDict


class UserRecord(TypedDict):
    email: str
    full_name: str
    role: str


ROOT = Path(__file__).resolve().parents[2]
DB_PATH = ROOT / "ecommerce.db"


def authenticate_user(
    email: str,
    password: str,
    role: str | None = None
) -> UserRecord | None:
    query = """
        SELECT email, full_name, role
        FROM users
        WHERE email = ? AND password = ?
    """

    params = [email, password]

    if role is not None:
        query += " AND role = ?"
        params.append(role)

    with sqlite3.connect(DB_PATH) as conn:
        row = conn.execute(query, params).fetchone()

    if row is None:
        return None

    return {
        "email": row[0],
        "full_name": row[1],
        "role": row[2],
    }