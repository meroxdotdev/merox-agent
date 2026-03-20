#!/usr/bin/env python3
"""
Merox Agent — HTTP service + Telegram bot.

Runs on the Oracle server. The HTTP endpoint serves client.py (SSE streaming).
The Telegram bot allows chatting with the agent directly from your phone.

Requirements:
    pip install claude-agent-sdk fastapi uvicorn python-telegram-bot

Start:
    python3 service.py
"""
import asyncio
import json
import os
import time
import uuid
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from claude_agent_sdk import (
    query,
    ClaudeAgentOptions,
    ResultMessage,
    AssistantMessage,
    TextBlock,
    ToolUseBlock,
    SystemMessage,
    CLINotFoundError,
    CLIConnectionError,
)

from config import MODEL
from prompt import build_system_prompt

# ── Config ────────────────────────────────────────────────────────────────────

TELEGRAM_TOKEN   = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_USER_ID = int(os.getenv("TELEGRAM_USER_ID", "0"))

# ── Session store ─────────────────────────────────────────────────────────────
# Maps our session_id → (claude_cli_session_id, last_used_timestamp)
_SESSION_TTL = 24 * 3600  # 24 hours
_sessions: dict[str, tuple[str, float]] = {}


def _get_session(key: str) -> str | None:
    entry = _sessions.get(key)
    if entry is None:
        return None
    session_id, _ = entry
    _sessions[key] = (session_id, time.time())  # refresh on access
    return session_id


def _set_session(key: str, claude_session_id: str):
    _sessions[key] = (claude_session_id, time.time())


async def _cleanup_sessions():
    """Remove sessions unused for longer than SESSION_TTL. Runs hourly."""
    while True:
        await asyncio.sleep(3600)
        cutoff = time.time() - _SESSION_TTL
        stale = [k for k, (_, ts) in _sessions.items() if ts < cutoff]
        for k in stale:
            del _sessions[k]
        if stale:
            print(f"Session cleanup: removed {len(stale)} stale sessions.", flush=True)

# ── Shared agent runner ───────────────────────────────────────────────────────

async def run_agent(message: str, session_key: str) -> AsyncGenerator[dict, None]:
    """Run the agent and yield event dicts (type, content/name/input)."""
    claude_session_id = _get_session(session_key)

    options = ClaudeAgentOptions(
        system_prompt=build_system_prompt(),
        allowed_tools=["Bash"],
        permission_mode="default",
        model=MODEL,
        resume=claude_session_id,
    )

    captured_session = None
    full_text = ""

    try:
        async for msg in query(prompt=message, options=options):
            if isinstance(msg, SystemMessage) and msg.subtype == "init":
                captured_session = msg.data.get("session_id")

            elif isinstance(msg, AssistantMessage):
                for block in msg.content:
                    if isinstance(block, TextBlock) and block.text:
                        full_text += block.text
                        yield {"type": "text", "content": block.text}
                    elif isinstance(block, ToolUseBlock):
                        yield {"type": "tool", "name": block.name, "input": block.input}

            elif isinstance(msg, ResultMessage):
                if getattr(msg, "is_error", False):
                    yield {"type": "error", "content": msg.result or "Agent returned an error"}
                elif msg.result and not full_text:
                    full_text = msg.result
                    yield {"type": "text", "content": msg.result}

    except CLINotFoundError:
        yield {"type": "error", "content": "Claude CLI not found. Run: npm install -g @anthropic-ai/claude-code"}
    except CLIConnectionError as e:
        yield {"type": "error", "content": f"CLI connection error: {e}"}
    except Exception as e:
        yield {"type": "error", "content": f"{type(e).__name__}: {e}"}

    if captured_session:
        _set_session(session_key, captured_session)


# ── Telegram bot ──────────────────────────────────────────────────────────────

async def _tg_agent_reply(user_message: str, session_key: str) -> str:
    """Collect full agent response for Telegram (non-streaming)."""
    parts = []
    async for event in run_agent(user_message, session_key):
        if event["type"] == "text":
            parts.append(event["content"])
        elif event["type"] == "error":
            parts.append(f"❌ {event['content']}")
    return "".join(parts) or "No response."


async def _tg_send(bot, chat_id: int, text: str):
    """Send message, try Markdown first, fall back to plain text."""
    try:
        await bot.send_message(chat_id=chat_id, text=text, parse_mode="Markdown")
    except Exception:
        await bot.send_message(chat_id=chat_id, text=text)


async def start_telegram_bot():
    import traceback
    from telegram import Update
    from telegram.constants import ChatAction
    from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

    async def _only_me(update: Update) -> bool:
        return update.effective_user and update.effective_user.id == TELEGRAM_USER_ID

    async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not await _only_me(update):
            return
        await update.message.reply_text(
            "👋 Merox Agent ready.\n\nAsk me anything about your infra — cluster, pods, services, logs.\n\n/clear — reset conversation"
        )

    async def cmd_clear(update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not await _only_me(update):
            return
        key = f"tg_{update.effective_user.id}"
        _sessions.pop(key, None)
        await update.message.reply_text("Session cleared.")

    async def on_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not await _only_me(update):
            return

        key = f"tg_{update.effective_user.id}"
        chat_id = update.effective_chat.id

        # Keep typing indicator alive while agent runs
        stop_typing = asyncio.Event()

        async def typing_loop():
            while not stop_typing.is_set():
                await context.bot.send_chat_action(chat_id=chat_id, action=ChatAction.TYPING)
                await asyncio.sleep(4)

        typing_task = asyncio.create_task(typing_loop())
        try:
            reply = await _tg_agent_reply(update.message.text, key)
        finally:
            stop_typing.set()
            typing_task.cancel()

        # Split if over Telegram's 4096 char limit
        for i in range(0, max(len(reply), 1), 4096):
            await _tg_send(context.bot, chat_id, reply[i:i + 4096])

    retry_delay = 5
    while True:
        tg_app = Application.builder().token(TELEGRAM_TOKEN).build()
        tg_app.add_handler(CommandHandler("start", cmd_start))
        tg_app.add_handler(CommandHandler("clear", cmd_clear))
        tg_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_message))

        try:
            await tg_app.initialize()
            await tg_app.start()
            await tg_app.updater.start_polling(drop_pending_updates=True)
            print("Telegram bot polling started.", flush=True)
            retry_delay = 5  # reset on success
            await asyncio.Event().wait()  # run forever
        except asyncio.CancelledError:
            raise
        except Exception:
            print(f"Telegram bot error (retrying in {retry_delay}s):\n{traceback.format_exc()}", flush=True)
            try:
                await tg_app.updater.stop()
            except Exception:
                pass
            try:
                await tg_app.stop()
            except Exception:
                pass
            try:
                await tg_app.shutdown()
            except Exception:
                pass
            await asyncio.sleep(retry_delay)
            retry_delay = min(retry_delay * 2, 120)  # exponential backoff, max 2 min


# ── FastAPI app ───────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    cleanup_task = asyncio.create_task(_cleanup_sessions())
    if TELEGRAM_TOKEN and TELEGRAM_USER_ID:
        tg_task = asyncio.create_task(start_telegram_bot())
        print(f"Telegram bot enabled for user {TELEGRAM_USER_ID}.", flush=True)
    else:
        tg_task = None
        print("Telegram bot disabled (TELEGRAM_BOT_TOKEN / TELEGRAM_USER_ID not set).", flush=True)
    yield
    cleanup_task.cancel()
    if tg_task:
        tg_task.cancel()


app = FastAPI(title="Merox Agent", lifespan=lifespan, docs_url=None, redoc_url=None)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class ChatRequest(BaseModel):
    message: str
    session_id: str = ""


@app.get("/health")
def health():
    return {"status": "ok", "telegram": bool(TELEGRAM_TOKEN), "model": MODEL}


@app.get("/sessions")
def list_sessions():
    return [{"session_id": sid, "idle_seconds": int(time.time() - ts)}
            for sid, (_, ts) in _sessions.items()]


@app.delete("/sessions/{session_id}")
def delete_session(session_id: str):
    _sessions.pop(session_id, None)
    return {"cleared": session_id}


@app.post("/chat")
async def chat(req: ChatRequest):
    """Stream agent response as Server-Sent Events."""
    session_id = req.session_id or str(uuid.uuid4())

    async def stream() -> AsyncGenerator[str, None]:
        yield f"data: {json.dumps({'type': 'session', 'session_id': session_id})}\n\n"
        async for event in run_agent(req.message, session_id):
            yield f"data: {json.dumps(event)}\n\n"
        yield f"data: {json.dumps({'type': 'done'})}\n\n"

    return StreamingResponse(stream(), media_type="text/event-stream")


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    from config import SERVER_TS_IP

    host = SERVER_TS_IP or "0.0.0.0"
    port = int(os.getenv("AGENT_PORT", "8765"))
    print(f"Starting Merox Agent on {host}:{port}")
    uvicorn.run("service:app", host=host, port=port, reload=False)
