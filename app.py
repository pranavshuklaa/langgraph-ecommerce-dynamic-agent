import streamlit as st
from dotenv import load_dotenv
from uuid import uuid4
from langchain_bot.context import SessionContext
from langchain_bot.hitl_utils import (
    handle_interrupt,
    get_thread_action_status,
)

from langchain_bot.agent import (
    get_agent,
    get_thread_config,
)
from langchain_bot.rag_tool import initialize_vector_store
from langchain_bot.auth import authenticate_user
from langchain_bot.threads import (
    load_threads,
    add_thread,
)
from langchain_bot.gmail_tools import (
    initialize_gmail,
    is_gmail_available,
)


def init_session():
    if "user_email" not in st.session_state:
        st.session_state.user_email = None

    if "user_role" not in st.session_state:
        st.session_state.user_role = None

    if "conversation_id" not in st.session_state:
        st.session_state.conversation_id = None

    if "threads" not in st.session_state:
        st.session_state.threads = []

    if "vector_store_ready" not in st.session_state:
        st.session_state.vector_store_ready = False


def start_new_conversation():
    conversation_id = str(uuid4())

    st.session_state.conversation_id = conversation_id

    add_thread(
        st.session_state.user_email,
        conversation_id
    )

    st.session_state.threads = load_threads(
        st.session_state.user_email
    )


def load_conversation(conversation_id):
    st.session_state.conversation_id = conversation_id


def render_history():
    if (
        st.session_state.user_email is None
        or st.session_state.conversation_id is None
    ):
        return

    config = get_thread_config(
        st.session_state.user_email,
        st.session_state.conversation_id
    )

    snapshot = get_agent().get_state(config)

    messages = snapshot.values.get("messages", [])

    for msg in messages:
        if msg.type == "human":
            with st.chat_message("user"):
                st.markdown(msg.content)

        elif msg.type == "ai" and msg.content:
            with st.chat_message("assistant"):
                st.markdown(msg.content)

    thread_id = f"{st.session_state.user_email}:{st.session_state.conversation_id}"

    action_statuses = get_thread_action_status(thread_id)

    for action in action_statuses:
        if action["status"] == "APPROVED":
            if action["action_type"] == "CREATE_RETURN":
                st.success(
                    f"Return approved for **{action['product_name']}** "
                    f"from order #{action['order_id']}."
                )
            elif action["action_type"] == "CANCEL_ORDER":
                st.success(
                    f"Cancellation approved for order #{action['order_id']}."
                )

        elif action["status"] == "REJECTED":
            if action["action_type"] == "CREATE_RETURN":
                st.error(
                    f"Return request rejected for **{action['product_name']}** "
                    f"from order #{action['order_id']}."
                )
            elif action["action_type"] == "CANCEL_ORDER":
                st.error(
                    f"Cancellation request rejected for order #{action['order_id']}."
                )

def chat_round(user_input):
    user_email = st.session_state.user_email
    conversation_id = st.session_state.conversation_id

    config = get_thread_config(
        user_email,
        conversation_id
    )

    context = SessionContext(
        user_email=user_email,
        conversation_id=conversation_id,
        role=st.session_state.user_role or "customer",
    )

    result = get_agent().invoke(
        {
            "messages": [
                {
                    "role": "user",
                    "content": user_input
                }
            ]
        },
        config=config,
        context=context,
    )

    thread_id = f"{user_email}:{conversation_id}"

    pending_message = handle_interrupt(
        result,
        thread_id=thread_id,
        user_email=user_email,
    )

    if pending_message:
        st.markdown(pending_message)
    elif result and result.get("messages"):
        last_message = result["messages"][-1]

        if getattr(last_message, "content", None):
            st.markdown(last_message.content)


def login_form():
    st.sidebar.subheader("Login")

    email = st.sidebar.text_input("Email")
    password = st.sidebar.text_input(
        "Password",
        type="password"
    )

    role = st.sidebar.selectbox(
        "Role",
        ["customer", "admin"]
    )

    if st.sidebar.button("Login"):
        user = authenticate_user(
            email=email,
            password=password,
            role=role
        )

        if user is None:
            st.sidebar.error(
                "Invalid email, password, or role."
            )
            return

        st.session_state.user_email = user["email"]
        st.session_state.user_role = user["role"]

        threads = load_threads(
            st.session_state.user_email
        )

        st.session_state.threads = threads

        if threads:
            st.session_state.conversation_id = threads[0]["id"]
        else:
            start_new_conversation()

        st.rerun()


def main():
    st.set_page_config(
        page_title="E-commerce Support Bot",
        page_icon="🛒"
    )

    load_dotenv()
    init_session()

    st.title("E-commerce Support Bot")

    # ---------------------------------------
    # Login
    # ---------------------------------------

    if st.session_state.user_email is None:
        st.info("Please log in to continue.")

        login_form()

        st.caption(
            "Demo customer: bob@example.com / bob123"
        )

        return

    # ---------------------------------------
    # Initialize vector store
    # ---------------------------------------

    if not st.session_state.vector_store_ready:
        with st.spinner(
            "Loading policy knowledge base..."
        ):
            initialize_vector_store()

        st.session_state.vector_store_ready = True

    if "gmail_ready" not in st.session_state:
        st.session_state.gmail_ready = False

    if not st.session_state.gmail_ready:
        with st.spinner("Initializing Gmail..."):
            initialize_gmail()

    st.session_state.gmail_ready = True

    # ---------------------------------------
    # Sidebar
    # ---------------------------------------

    st.sidebar.success(
        f"Logged in as {st.session_state.user_email}"
    )
    st.sidebar.write(
        "Conversation ID:",
        st.session_state.conversation_id
    )

    if st.sidebar.button("New Conversation"):
        start_new_conversation()
        st.rerun()

    if st.sidebar.button("Refresh Chat"):
        st.rerun()

    threads = st.session_state.threads

    if threads:
        thread_ids = [
            thread["id"]
            for thread in threads
        ]

        thread_labels = {
            thread["id"]: thread["label"]
            for thread in threads
        }

        current_id = st.session_state.conversation_id

        if current_id not in thread_ids:
            current_id = thread_ids[0]
            st.session_state.conversation_id = current_id

        selected_id = st.sidebar.selectbox(
            "Conversations",
            thread_ids,
            index=thread_ids.index(current_id),
            format_func=lambda thread_id:
                thread_labels.get(
                    thread_id,
                    thread_id[:8]
                )
        )

        if selected_id != st.session_state.conversation_id:
            load_conversation(selected_id)
            st.rerun()

    if is_gmail_available():
        st.sidebar.success("Gmail: Enabled")
    else:
        st.sidebar.info("Gmail: Not configured")

    # ---------------------------------------
    # Chat history from checkpointer
    # ---------------------------------------

    render_history()

    # ---------------------------------------
    # Chat input
    # ---------------------------------------

    prompt = st.chat_input(
        "Ask about returns, refunds, shipping, cancellations..."
    )

    if prompt:
        with st.chat_message("user"):
            st.markdown(prompt)

        with st.chat_message("assistant"):
            with st.spinner("Thinking..."):
                chat_round(prompt)

        st.rerun()


if __name__ == "__main__":
    main()