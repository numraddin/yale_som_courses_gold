"""The Yale SOM course agent.

main.py imports `run_agent` at module load, so nothing here raises on import:
the agent is built lazily on the first call and a missing PORTKEY_API_KEY comes
back as a readable reply rather than a 500.

Wiring:
  * model   — gpt-6-astra, reached through the Portkey gateway
  * tools   — search_courses (local, tools.py)
  * native  — web_search (OpenAI's server-side tool, via NativeTool)
  * audit   — every run appended to output/audit_trail.json
"""

from __future__ import annotations

import asyncio
import json
import os
import threading
from concurrent.futures import TimeoutError as FuturesTimeout
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from openai import AsyncOpenAI
from pydantic_ai import Agent, WebSearchTool
from pydantic_ai.capabilities import NativeTool
from pydantic_ai.messages import (
    NativeToolCallPart,
    NativeToolReturnPart,
    TextPart,
    ThinkingPart,
    ToolCallPart,
    ToolReturnPart,
)
from pydantic_ai.models.openai import OpenAIResponsesModel
from pydantic_ai.providers.openai import OpenAIProvider

from models import AgentResult, AuditEntry, ToolInvocation
from tools import search_courses

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
PROMPT_PATH = HERE / "prompts" / "prompt.md"
AUDIT_PATH = ROOT / "output" / "audit_trail.json"

MODEL_NAME = "gpt-6-astra"
PORTKEY_BASE_URL = "https://api.portkey.ai/v1"

# How long a single agent loop may take before we give up on it.
RUN_TIMEOUT_SECONDS = float(os.environ.get("AGENT_TIMEOUT_SECONDS", "180"))

# The key may sit next to this lecture folder or in a parent (e.g. MGT409/.env).
# Walk a few levels up and load whatever is found; python-dotenv does not
# overwrite already-set vars, so the closest .env wins. The walk is bounded so
# an unrelated .env near the filesystem root is never picked up.
_ENV_SEARCH_DEPTH = 4
_ENV_CANDIDATES = [ROOT / ".env", *(p / ".env" for p in ROOT.parents[:_ENV_SEARCH_DEPTH])]


def load_env() -> None:
    for candidate in _ENV_CANDIDATES:
        if candidate.is_file():
            load_dotenv(candidate)


def _instructions() -> str:
    return PROMPT_PATH.read_text(encoding="utf-8")


_agent: Agent[None, str] | None = None
_build_lock = threading.Lock()

# main.py's /api/chat is a sync def, so FastAPI runs it in a threadpool and each
# worker thread would otherwise get its own event loop. The AsyncOpenAI client
# binds asyncio primitives to whichever loop touches it first, so a second
# thread raises "bound to a different event loop". One long-lived loop, owned by
# a dedicated thread, keeps every agent run on the same loop (and preserves HTTP
# connection pooling).
_loop: asyncio.AbstractEventLoop | None = None
_loop_lock = threading.Lock()
_audit_lock = threading.Lock()


def _get_loop() -> asyncio.AbstractEventLoop:
    """The shared agent event loop, started on first use."""
    global _loop
    with _loop_lock:
        if _loop is None or _loop.is_closed():
            _loop = asyncio.new_event_loop()
            threading.Thread(
                target=_loop.run_forever, name="agent-event-loop", daemon=True
            ).start()
        return _loop


def _build_agent() -> Agent[None, str]:
    """Construct the agent once. Raises RuntimeError if the key is missing."""
    global _agent
    with _build_lock:
        if _agent is not None:
            return _agent
        _agent = _construct_agent()
        return _agent


def _construct_agent() -> Agent[None, str]:
    load_env()
    portkey_key = os.environ.get("PORTKEY_API_KEY")
    if not portkey_key:
        looked = ", ".join(str(p) for p in _ENV_CANDIDATES[:3])
        raise RuntimeError(
            "PORTKEY_API_KEY is not set. Put it in a .env next to this lecture "
            f"folder or in a parent folder (looked in: {looked}, …)."
        )

    # Portkey authenticates via its own headers; the SDK still wants an api_key,
    # so a placeholder is passed and never used upstream.
    client = AsyncOpenAI(
        base_url=PORTKEY_BASE_URL,
        api_key="sk-portkey-placeholder",
        default_headers={
            "x-portkey-api-key": portkey_key,
            "x-portkey-provider": "openai",
        },
    )
    model = OpenAIResponsesModel(MODEL_NAME, provider=OpenAIProvider(openai_client=client))

    return Agent(
        model,
        instructions=_instructions(),
        tools=[search_courses],
        capabilities=[NativeTool(WebSearchTool())],
        name="yale-som-course-assistant",
    )


def run_agent(message: str) -> dict[str, Any]:
    """Answer one user message.

    Returns the dict shape main.py's /api/chat route expects:
        {"reply": str, "tools_used": list[str]}
    """
    started = datetime.now(timezone.utc)

    try:
        agent = _build_agent()
    except RuntimeError as exc:
        result = AgentResult(reply=f"Configuration problem: {exc}", tools_used=[])
        _append_audit(
            AuditEntry(
                time=started.isoformat(),
                user_message=message,
                reply=result.reply,
                stop_reason="config_error",
            )
        )
        return result.model_dump()

    # Submitted to the shared loop rather than agent.run_sync(), which would
    # spin a fresh loop per call and break the reused AsyncOpenAI client.
    future = asyncio.run_coroutine_threadsafe(agent.run(message), _get_loop())
    try:
        run = future.result(timeout=RUN_TIMEOUT_SECONDS)
    except FuturesTimeout:
        future.cancel()  # otherwise the run keeps burning tokens on the loop
        result = AgentResult(
            reply=(
                f"That took longer than {RUN_TIMEOUT_SECONDS:.0f}s and was stopped. "
                "Try a narrower question."
            ),
            tools_used=[],
        )
        _append_audit(
            AuditEntry(
                time=started.isoformat(),
                user_message=message,
                reply=result.reply,
                stop_reason="timeout",
            )
        )
        return result.model_dump()
    except Exception as exc:  # noqa: BLE001 - surface any provider failure readably
        detail = f"{type(exc).__name__}: {exc}"
        result = AgentResult(
            reply="The agent could not complete that request. " + detail,
            tools_used=[],
        )
        _append_audit(
            AuditEntry(
                time=started.isoformat(),
                user_message=message,
                reply=result.reply,
                stop_reason="error",
            )
        )
        return result.model_dump()

    thoughts, tool_calls, tools_used = _inspect_messages(run.all_messages())
    reply = run.output if isinstance(run.output, str) else str(run.output)

    _append_audit(
        AuditEntry(
            time=started.isoformat(),
            user_message=message,
            thoughts=thoughts,
            tool_calls=tool_calls,
            reply=reply,
            stop_reason=_stop_reason(run),
        )
    )

    return AgentResult(reply=reply, tools_used=tools_used).model_dump()


def _inspect_messages(
    messages: list[Any],
) -> tuple[list[str], list[ToolInvocation], list[str]]:
    """Pull thoughts, tool calls, and tool names out of the message history.

    Local tool calls arrive as ToolCallPart/ToolReturnPart; native ones (web
    search) as NativeToolCallPart/NativeToolReturnPart. Returns are matched to
    calls by tool_call_id so each invocation carries a result summary.
    """
    thoughts: list[str] = []
    calls: list[ToolInvocation] = []
    tools_used: list[str] = []
    returns: dict[str, str] = {}

    # First pass: collect tool results keyed by call id.
    for msg in messages:
        for part in getattr(msg, "parts", []):
            if isinstance(part, (ToolReturnPart, NativeToolReturnPart)):
                returns[part.tool_call_id] = _summarize(part.content)

    # Second pass: thoughts and calls, in order.
    for msg in messages:
        for part in getattr(msg, "parts", []):
            if isinstance(part, ThinkingPart):
                if text := (part.content or "").strip():
                    thoughts.append(text)
            elif isinstance(part, (ToolCallPart, NativeToolCallPart)):
                name = part.tool_name
                calls.append(
                    ToolInvocation(
                        tool=name,
                        args=_normalize_args(part.args),
                        result_summary=returns.get(part.tool_call_id, ""),
                    )
                )
                if name not in tools_used:
                    tools_used.append(name)

    return thoughts, calls, tools_used


def _stop_reason(run: Any) -> str:
    """Why the loop ended, from the final model response."""
    try:
        reason = getattr(run.response, "finish_reason", None)
    except Exception:  # noqa: BLE001
        reason = None
    return str(reason) if reason else "completed"


def _normalize_args(args: Any) -> dict[str, Any]:
    """Tool args arrive as a dict or a JSON string depending on the provider."""
    if isinstance(args, dict):
        return args
    if isinstance(args, str):
        try:
            parsed = json.loads(args)
        except (ValueError, TypeError):
            return {"raw": args}
        return parsed if isinstance(parsed, dict) else {"value": parsed}
    if args is None:
        return {}
    return {"value": str(args)}


def _summarize(content: Any, limit: int = 300) -> str:
    """Short, readable stand-in for a tool result in the audit trail."""
    if content is None:
        return ""
    if hasattr(content, "model_dump"):
        content = content.model_dump()
    if isinstance(content, (dict, list)):
        try:
            text = json.dumps(content, ensure_ascii=False, default=str)
        except (TypeError, ValueError):
            text = str(content)
    else:
        text = str(content)
    text = " ".join(text.split())
    return text if len(text) <= limit else text[:limit].rstrip() + "…"


def _append_audit(entry: AuditEntry) -> None:
    """Append one entry to output/audit_trail.json, preserving earlier rows.

    Read-modify-write, so it is serialized behind a lock: concurrent /api/chat
    requests land in different threadpool workers and would otherwise read the
    same list and lose an entry. The write itself goes to a temp file and is
    then renamed, so a crash mid-write cannot truncate the trail.

    Never raises: a broken audit file must not take down a chat reply. If the
    existing file is unreadable it is set aside rather than overwritten.
    """
    try:
        with _audit_lock:
            AUDIT_PATH.parent.mkdir(parents=True, exist_ok=True)

            rows: list[Any] = []
            if AUDIT_PATH.is_file():
                try:
                    loaded = json.loads(AUDIT_PATH.read_text(encoding="utf-8") or "[]")
                    rows = loaded if isinstance(loaded, list) else [loaded]
                except (ValueError, OSError):
                    try:
                        AUDIT_PATH.replace(AUDIT_PATH.with_suffix(".corrupt.json"))
                    except OSError:
                        pass
                    rows = []

            rows.append(entry.model_dump())

            tmp = AUDIT_PATH.with_suffix(".tmp")
            tmp.write_text(
                json.dumps(rows, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
            )
            tmp.replace(AUDIT_PATH)
    except Exception:  # noqa: BLE001 - auditing is best-effort
        pass
