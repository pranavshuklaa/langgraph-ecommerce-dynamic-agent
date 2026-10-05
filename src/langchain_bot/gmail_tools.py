import pickle
from pathlib import Path

from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

from langchain_community.tools.gmail.send_message import GmailSendMessage


ROOT = Path(__file__).resolve().parents[2]

CREDENTIALS_PATH = ROOT / "credentials.json"
TOKEN_PATH = ROOT / "token.pickle"

SCOPES = [
    "https://www.googleapis.com/auth/gmail.send"
]

_gmail_service = None
_gmail_initialized = False


def get_gmail_service():
    global _gmail_service

    if _gmail_service is not None:
        return _gmail_service

    if not CREDENTIALS_PATH.exists():
        raise FileNotFoundError(
            f"Missing Gmail credentials: {CREDENTIALS_PATH}"
        )

    credentials = None

    if TOKEN_PATH.exists():
        with TOKEN_PATH.open("rb") as token_file:
            credentials = pickle.load(token_file)

    if credentials is not None and credentials.expired:
        if credentials.refresh_token:
            credentials.refresh(Request())
        else:
            credentials = None

    if credentials is None or not credentials.valid:
        flow = InstalledAppFlow.from_client_secrets_file(
            str(CREDENTIALS_PATH),
            SCOPES,
        )

        credentials = flow.run_local_server(
            port=0
        )

        with TOKEN_PATH.open("wb") as token_file:
            pickle.dump(credentials, token_file)

    _gmail_service = build(
        "gmail",
        "v1",
        credentials=credentials,
    )

    return _gmail_service


def initialize_gmail() -> bool:
    global _gmail_initialized

    if _gmail_initialized:
        return _gmail_service is not None

    try:
        get_gmail_service()
        _gmail_initialized = True
        return True

    except Exception as exc:
        print(f"Gmail initialization skipped: {exc}")
        _gmail_initialized = True
        return False


def get_gmail_tools():
    if not initialize_gmail():
        return []

    return [
        GmailSendMessage(
            api_resource=get_gmail_service()
        )
    ]


def is_gmail_available() -> bool:
    return _gmail_service is not None


__all__ = [
    "get_gmail_service",
    "initialize_gmail",
    "get_gmail_tools",
    "is_gmail_available",
]