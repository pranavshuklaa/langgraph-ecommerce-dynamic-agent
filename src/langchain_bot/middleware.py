from datetime import datetime

from langchain.agents.middleware import (
    HumanInTheLoopMiddleware,
    wrap_model_call,
    wrap_tool_call,
)


def _ts():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


@wrap_model_call
def model_logging_middleware(request, handler):
    messages = request.state.get("messages", [])

    print(
        f"[{_ts()}] MODEL REQUEST | "
        f"messages={len(messages)}"
    )

    if messages:
        last_message = messages[-1]

        preview = str(
            getattr(last_message, "content", "")
        )[:200]

        print(
            f"[{_ts()}] MODEL INPUT | "
            f"{preview}"
        )

    try:
        response = handler(request)

        result = getattr(response, "result", [])

        if result:
            last_result = result[-1]

            preview = str(
                getattr(last_result, "content", "")
            )[:200]

            print(
                f"[{_ts()}] MODEL RESPONSE | "
                f"{preview}"
            )

            tool_calls = getattr(
                last_result,
                "tool_calls",
                []
            )

            if tool_calls:
                print(
                    f"[{_ts()}] MODEL TOOL CALLS | "
                    f"{tool_calls}"
                )

        return response

    except Exception as exc:
        print(
            f"[{_ts()}] MODEL ERROR | "
            f"{type(exc).__name__}: {exc}"
        )
        raise


@wrap_tool_call
def tool_logging_middleware(request, handler):
    tool_call = request.tool_call

    print(
        f"[{_ts()}] TOOL REQUEST | "
        f"name={tool_call.get('name')} | "
        f"args={tool_call.get('args')}"
    )

    try:
        result = handler(request)

        preview = str(
            getattr(result, "content", result)
        )[:300]

        print(
            f"[{_ts()}] TOOL RESPONSE | "
            f"{preview}"
        )

        return result

    except Exception as exc:
        print(
            f"[{_ts()}] TOOL ERROR | "
            f"{type(exc).__name__}: {exc}"
        )
        raise


def get_logging_middleware():
    return [
        model_logging_middleware,
        tool_logging_middleware,
    ]

hitl_middleware = HumanInTheLoopMiddleware(
    interrupt_on={
        "cancel_order_action": {
            "allowed_decisions": ["approve", "reject"],
        },
        "create_return_action": {
            "allowed_decisions": ["approve", "reject"],
        },
    },
    description_prefix="Admin approval required",
)