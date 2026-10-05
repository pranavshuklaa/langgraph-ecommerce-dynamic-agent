from datetime import datetime
from pathlib import Path
import sqlite3

from langchain_core.tools import tool
from langchain.tools import ToolRuntime

from .context import SessionContext


ROOT = Path(__file__).resolve().parents[2]
DB_PATH = ROOT / "ecommerce.db"


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%dT%H:%M:%S")


@tool
def cancel_order_action(
    order_id: int,
    runtime: ToolRuntime[SessionContext],
) -> str:
    """
    Cancel a customer's PLACED order after human approval.

    The logged-in user's identity comes from SessionContext.
    Do not accept user_email from the model.
    """

    user_email = runtime.context.user_email
    thread_id = f"{user_email}:{runtime.context.conversation_id}"

    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("PRAGMA foreign_keys = ON")

        row = conn.execute(
            """
            SELECT o.id, o.status, o.total_amount, u.id
            FROM orders o
            JOIN users u ON u.id = o.user_id
            WHERE o.id = ?
              AND u.email = ?
            """,
            (order_id, user_email),
        ).fetchone()

        if row is None:
            return f"Order #{order_id} was not found for the logged-in customer."

        _, order_status, total_amount, user_id = row

        if order_status != "PLACED":
            return (
                f"Order #{order_id} cannot be cancelled because its current "
                f"status is {order_status}."
            )

        now = _now()

        conn.execute(
            """
            UPDATE orders
            SET status = 'CANCELLED'
            WHERE id = ?
            """,
            (order_id,),
        )

        conn.execute(
            """
            UPDATE payments
            SET status = 'REFUNDED'
            WHERE order_id = ?
            """,
            (order_id,),
        )

        conn.execute(
            """
            INSERT INTO tickets (
                user_id,
                return_id,
                subject,
                status,
                thread_id,
                user_email,
                created_at,
                updated_at
            )
            VALUES (?, NULL, ?, 'OPEN', ?, ?, ?, ?)
            """,
            (
                user_id,
                f"Cancellation request for order #{order_id}",
                thread_id,
                user_email,
                now,
                now,
            ),
        )

        conn.commit()

    return (
        f"Order #{order_id} has been cancelled successfully. "
        f"A refund of {total_amount:.2f} has been initiated."
    )


@tool
def create_return_action(
    order_id: int,
    product_name: str,
    reason: str,
    runtime: ToolRuntime[SessionContext],
) -> str:
    """
    Create a return request for a customer's SHIPPED or DELIVERED order
    after human approval.

    The logged-in user's identity comes from SessionContext.
    Do not accept user_email from the model.
    """

    user_email = runtime.context.user_email
    thread_id = f"{user_email}:{runtime.context.conversation_id}"

    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("PRAGMA foreign_keys = ON")

        order_row = conn.execute(
            """
            SELECT o.id, o.status, o.total_amount, u.id
            FROM orders o
            JOIN users u ON u.id = o.user_id
            WHERE o.id = ?
              AND u.email = ?
            """,
            (order_id, user_email),
        ).fetchone()

        if order_row is None:
            return f"Order #{order_id} was not found for the logged-in customer."

        _, order_status, total_amount, user_id = order_row

        if order_status == "PLACED":
            return (
                f"Order #{order_id} is still PLACED. "
                "Please cancel the order instead of creating a return."
            )

        if order_status not in ("SHIPPED", "DELIVERED"):
            return (
                f"Order #{order_id} cannot be returned because its current "
                f"status is {order_status}."
            )

        item_row = conn.execute(
            """
            SELECT oi.id, oi.quantity, oi.unit_price, p.name
            FROM order_items oi
            JOIN products p ON p.id = oi.product_id
            WHERE oi.order_id = ?
              AND LOWER(p.name) = LOWER(?)
            """,
            (order_id, product_name),
        ).fetchone()

        if item_row is None:
            return (
                f"Product '{product_name}' was not found in order #{order_id}. "
                "Please provide the exact product name from the order."
            )

        order_item_id, quantity, unit_price, actual_product_name = item_row

        existing_return = conn.execute(
            """
            SELECT id, status
            FROM returns
            WHERE order_id = ?
              AND order_item_id = ?
              AND status IN ('PENDING', 'APPROVED')
            """,
            (order_id, order_item_id),
        ).fetchone()

        if existing_return is not None:
            return (
                f"A return already exists for '{actual_product_name}' "
                f"in order #{order_id} with status {existing_return[1]}."
            )

        now = _now()

        cursor = conn.execute(
            """
            INSERT INTO returns (
                order_id,
                order_item_id,
                user_id,
                reason,
                status,
                requested_at,
                resolved_at,
                admin_id
            )
            VALUES (?, ?, ?, ?, 'APPROVED', ?, ?, NULL)
            """,
            (
                order_id,
                order_item_id,
                user_id,
                reason,
                now,
                now,
            ),
        )

        return_id = cursor.lastrowid

        conn.execute(
            """
            INSERT INTO tickets (
                user_id,
                return_id,
                subject,
                status,
                thread_id,
                user_email,
                created_at,
                updated_at
            )
            VALUES (?, ?, ?, 'OPEN', ?, ?, ?, ?)
            """,
            (
                user_id,
                return_id,
                f"Return request for {actual_product_name}",
                thread_id,
                user_email,
                now,
                now,
            ),
        )

        conn.execute(
            """
            UPDATE payments
            SET status = 'REFUNDED'
            WHERE order_id = ?
            """,
            (order_id,),
        )

        conn.commit()

    refund_amount = quantity * unit_price

    return (
        f"Return for '{actual_product_name}' from order #{order_id} "
        f"has been created successfully. "
        f"A refund of {refund_amount:.2f} has been initiated."
    )


def get_action_tools():
    return [
        cancel_order_action,
        create_return_action,
    ]


__all__ = [
    "cancel_order_action",
    "create_return_action",
    "get_action_tools",
]