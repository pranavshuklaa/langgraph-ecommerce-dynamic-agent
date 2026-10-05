import streamlit as st
import sqlite3
from pathlib import Path

from langchain_bot.auth import authenticate_user
from langchain_bot.hitl_utils import resume_with_decision


def init_session():
    if "admin_email" not in st.session_state:
        st.session_state.admin_email = None


def login_form():
    st.subheader("Admin Login")

    with st.form("admin_login"):
        email = st.text_input("Email")
        password = st.text_input(
            "Password",
            type="password"
        )

        submitted = st.form_submit_button("Login")

    if submitted:
        user = authenticate_user(
            email=email,
            password=password,
            role="admin"
        )

        if user is None:
            st.error("Invalid admin email or password.")
            return

        st.session_state.admin_email = user["email"]
        st.rerun()

def get_pending_actions(status="PENDING", email=None):
    db_path = Path(__file__).resolve().parents[2] / "ecommerce.db"

    conn = sqlite3.connect(db_path)

    query = """
        SELECT
            id,
            user_email,
            order_id,
            action_type,
            thread_id,
            status
        FROM pending_actions
        WHERE status = ?
    """

    params = [status]

    if email:
        query += " AND user_email = ?"
        params.append(email)

    query += " ORDER BY id DESC"

    rows = conn.execute(query, params).fetchall()

    conn.close()

    return rows

def main():
    st.set_page_config(
        page_title="E-commerce Admin Dashboard",
        page_icon="🛠️"
    )

    init_session()

    st.title("E-commerce Admin Dashboard")

    if st.session_state.admin_email is None:
        st.info("Please log in as an administrator.")
        login_form()
        return

    st.success(
        f"Logged in as {st.session_state.admin_email}"
    )

    status = st.selectbox(
        "Status",
        ["PENDING", "APPROVED", "REJECTED"]
    )

    email = st.text_input(
        "Filter by email (optional)"
    )

    st.subheader("Pending Actions")

    pending_actions = get_pending_actions(
        status=status,
        email=email.strip() or None
    )
    st.subheader("Pending Actions")


    if not pending_actions:
        st.info("No pending actions.")
        return

    for action in pending_actions:
        (
            action_id,
            user_email,
            order_id,
            action_type,
            thread_id,
            action_status,
        ) = action

        st.write(f"**Action #{action_id}**")
        st.write(f"User: {user_email}")
        st.write(f"Order: #{order_id}")
        st.write(f"Action: {action_type}")
        st.write(f"Thread: `{thread_id}`")
        st.write(f"Status: {action_status}")

        if action_status == "PENDING":
            col1, col2 = st.columns(2)

            with col1:
                if st.button(
                    "Approve",
                    key=f"approve_{action_id}",
                ):
                    result = resume_with_decision(
                        thread_id,
                        "approve",
                    )

                    st.success(
                        f"Action #{action_id} approved."
                    )
                    st.write(result)

                    st.rerun()

            with col2:
                if st.button(
                    "Reject",
                    key=f"reject_{action_id}",
                ):
                    result = resume_with_decision(
                        thread_id,
                        "reject",
                    )

                    st.warning(
                        f"Action #{action_id} rejected."
                    )
                    st.write(result)

                    st.rerun()

        st.divider()


if __name__ == "__main__":
    main()