import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
THREADS_PATH = ROOT / "chat_threads.json"


def load_threads(user_email: str) -> list[dict]:
    if not THREADS_PATH.exists():
        return []

    try:
        data = json.loads(
            THREADS_PATH.read_text(encoding="utf-8")
        )
    except (json.JSONDecodeError, OSError):
        return []

    return data.get(user_email, [])


def save_threads(user_email: str, threads: list[dict]) -> None:
    data = {}

    if THREADS_PATH.exists():
        try:
            data = json.loads(
                THREADS_PATH.read_text(encoding="utf-8")
            )
        except (json.JSONDecodeError, OSError):
            data = {}

    data[user_email] = threads

    THREADS_PATH.write_text(
        json.dumps(data, indent=2),
        encoding="utf-8"
    )


def add_thread(user_email: str, conversation_id: str) -> None:
    threads = load_threads(user_email)

    threads.append({
        "id": conversation_id,
        "label": f"Chat {conversation_id[:8]}"
    })

    save_threads(user_email, threads)