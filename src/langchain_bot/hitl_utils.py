from datetime import datetime
from pathlib import Path
import sqlite3

from langgraph.types import Command

from langchain_bot.agent import get_agent, get_thread_config
from langchain_bot.context import SessionContext


ROOT = Path(__file__).resolve().parents[2]
DB_PATH = ROOT / "ecommerce.db"


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%dT%H:%M:%S")


def _get_interrupts(agent_result):
    """Return interrupt objects from a LangGraph agent result."""
    if not isinstance(agent_result, dict):
        return []

    interrupts = agent_result.get("__interrupt__", [])

    if interrupts is None:
        return []

    if not isinstance(interrupts, (list, tuple)):
        interrupts = [interrupts]

    return list(interrupts)


def _get_interrupt_value(interrupt):
    """Extract the value carried by a LangGraph interrupt."""
    value = getattr(interrupt, "value", None)

    if value is not None:
        return value

    if isinstance(interrupt, dict):
        return interrupt.get("value", interrupt)

    return interrupt


def _get_action_requests(interrupt_value):
    """Extract action requests from the HITL interrupt payload."""
    if isinstance(interrupt_value, dict):
        action_requests = interrupt_value.get("action_requests", [])

        if isinstance(action_requests, dict):
            return [action_requests]

        if isinstance(action_requests, list):
            return action_requests

    return []


def _request_value(request, key):
    """Read an action-request argument from common LangChain payload shapes."""
    if not isinstance(request, dict):
        return None

    args = request.get("args")

    if args is None:
        args = request.get("arguments", {})

    if isinstance(args, dict) and key in args:
        return args[key]

    return request.get(key)


def handle_interrupt(
    agent_result,
    thread_id: str,
    user_email: str,
) -> str | None:
    """
    Persist HITL action requests and return a customer-facing markdown message.

    Returns None when the agent result contains no interrupt.
    """

    interrupts = _get_interrupts(agent_result)

    if not interrupts:
        return None

    pending_messages = []

    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("PRAGMA foreign_keys = ON")

        for interrupt in interrupts:
            value = _get_interrupt_value(interrupt)

            for request in _get_action_requests(value):
                tool_name = request.get("name")

                if tool_name == "cancel_order_action":
                    action_type = "CANCEL_ORDER"
                elif tool_name == "create_return_action":
                    action_type = "CREATE_RETURN"
                else:
                    continue

                order_id = _request_value(request, "order_id")
                product_name = _request_value(request, "product_name")
                reason = _request_value(request, "reason")

                if order_id is None:
                    continue

                now = _now()

                existing = conn.execute(
                    """
                    SELECT id
                    FROM pending_actions
                    WHERE thread_id = ?
                      AND action_type = ?
                      AND order_id = ?
                      AND status = 'PENDING'
                    """,
                    (
                        thread_id,
                        action_type,
                        order_id,
                    ),
                ).fetchone()

                if existing is None:
                    conn.execute(
                        """
                        INSERT INTO pending_actions (
                            thread_id,
                            user_email,
                            action_type,
                            order_id,
                            product_name,
                            reason,
                            status,
                            created_at,
                            updated_at
                        )
                        VALUES (?, ?, ?, ?, ?, ?, 'PENDING', ?, ?)
                        """,
                        (
                            thread_id,
                            user_email,
                            action_type,
                            order_id,
                            product_name,
                            reason,
                            now,
                            now,
                        ),
                    )

                if action_type == "CANCEL_ORDER":
                    pending_messages.append(
                        f"**Cancellation request pending human approval**\n\n"
                        f"Order #{order_id} requires admin approval."
                    )
                else:
                    pending_messages.append(
                        f"**Return request pending human approval**\n\n"
                        f"Order #{order_id}"
                        + (
                            f" — {product_name}"
                            if product_name
                            else ""
                        )
                        + " requires admin approval."
                    )

        conn.commit()

    if not pending_messages:
        return None

    return "\n\n".join(pending_messages)


def list_pending_actions(
    status: str = "PENDING",
    user_email: str | None = None,
) -> list[dict]:
    """Return pending action rows for the admin dashboard."""

    query = """
        SELECT
            id,
            thread_id,
            user_email,
            action_type,
            order_id,
            product_name,
            reason,
            status,
            created_at,
            updated_at
        FROM pending_actions
        WHERE status = ?
    """

    params = [status]

    if user_email is not None:
        query += " AND user_email = ?"
        params.append(user_email)

    query += " ORDER BY created_at ASC"

    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(query, params).fetchall()

    return [dict(row) for row in rows]

def get_thread_action_status(thread_id: str) -> list[dict]:
    """Return action statuses associated with a conversation thread."""

    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row

        rows = conn.execute(
            """
            SELECT
                id,
                action_type,
                order_id,
                product_name,
                reason,
                status,
                created_at,
                updated_at
            FROM pending_actions
            WHERE thread_id = ?
            ORDER BY id ASC
            """,
            (thread_id,),
        ).fetchall()

    return [dict(row) for row in rows]

def resume_with_decision(
    thread_id: str,
    decision: str,
):
    """
    Resume the customer's paused agent thread after an admin decision.

    decision must be 'approve' or 'reject'.
    """

    decision = decision.lower().strip()

    if decision not in {"approve", "reject"}:
        raise ValueError(
            "decision must be either 'approve' or 'reject'"
        )

    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row

        row = conn.execute(
            """
            SELECT
                id,
                user_email,
                thread_id,
                status
            FROM pending_actions
            WHERE thread_id = ?
              AND status = 'PENDING'
            ORDER BY id DESC
            LIMIT 1
            """,
            (thread_id,),
        ).fetchone()

    if row is None:
        raise ValueError(
            f"No PENDING action found for thread: {thread_id}"
        )

    user_email = row["user_email"]

    prefix = f"{user_email}:"

    if not thread_id.startswith(prefix):
        raise ValueError(
            "Thread ID does not match the stored customer email."
        )

    conversation_id = thread_id[len(prefix):]

    context = SessionContext(
        user_email=user_email,
        conversation_id=conversation_id,
        role="customer",
    )

    config = get_thread_config(
        user_email,
        conversation_id,
    )

    agent = get_agent()

    result = agent.invoke(
        Command(
            resume={
                "decisions": [
                    {
                        "type": decision,
                    }
                ]
            }
        ),
        config=config,
        context=context,
    )
    # Verify that the resumed graph actually completed.
    state = agent.get_state(config)

    if state.next:
        raise RuntimeError(
            f"HITL resume did not complete for thread {thread_id}. "
            f"Graph is still paused at: {state.next}"
        )

    new_status = (
        "APPROVED"
        if decision == "approve"
        else "REJECTED"
    )

    now = _now()

    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            """
            UPDATE pending_actions
            SET status = ?,
                updated_at = ?
            WHERE id = ?
              AND status = 'PENDING'
            """,
            (
                new_status,
                now,
                row["id"],
            ),
        )
        conn.commit()

    return result


__all__ = [
    "handle_interrupt",
    "list_pending_actions",
    "get_thread_action_status",
    "resume_with_decision",
]