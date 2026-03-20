#!/usr/bin/env python3
"""
Merox Agent — HTTP service + Telegram bot.

Uses the Anthropic Python SDK directly.
- Sessions = full conversation history, persisted to disk across restarts
- Telegram streams responses live (message edited as chunks arrive)
- Per-user lock prevents overlapping requests

Requirements:
    pip install anthropic fastapi uvicorn python-telegram-bot

Start:
    python3 service.py
"""
import asyncio
import json
import os
import time
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncGenerator

import anthropic
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from config import MODEL, MAX_TOKENS
from prompt import build_system_prompt
from tools import DEFINITIONS as TOOLS, run_bash

# ── Config ────────────────────────────────────────────────────────────────────

TELEGRAM_TOKEN   = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_USER_ID = int(os.getenv("TELEGRAM_USER_ID", "0"))

_TG_EDIT_INTERVAL = 1.2   # seconds between live edits (Telegram: max 1 edit/sec)
_MAX_HISTORY      = 40    # max messages kept per session (20 turns)

# ── Session store ─────────────────────────────────────────────────────────────
# Maps session_key → list of Anthropic message dicts (full conversation history)

_SESSION_FILE = Path(__file__).parent / "memory" / "sessions.json"
_sessions: dict[str, list] = {}


def _load_sessions_from_disk() -> None:
    try:
        _sessions.update(json.loads(_SESSION_FILE.read_text()))
    except (FileNotFoundError, json.JSONDecodeError):
        pass


def _save_sessions_to_disk() -> None:
    try:
        _SESSION_FILE.write_text(json.dumps(_sessions))
    except Exception as e:
        print(f"Session save error: {e}", flush=True)


def _get_conversation(key: str) -> list:
    return list(_sessions.get(key, []))


def _set_conversation(key: str, conversation: list) -> None:
    _sessions[key] = conversation[-_MAX_HISTORY:]
    _save_sessions_to_disk()


def _clear_session(key: str) -> None:
    _sessions.pop(key, None)
    _save_sessions_to_disk()


# ── Agent runner ──────────────────────────────────────────────────────────────

_client = anthropic.AsyncAnthropic()


async def run_agent(message: str, session_key: str) -> AsyncGenerator[dict, None]:
    """
    Run the agent loop for one user message.
    Yields event dicts: {"type": "text"|"tool"|"error", ...}
    Handles multi-turn tool use transparently.
    """
    conversation = _get_conversation(session_key)
    conversation.append({"role": "user", "content": message})

    while True:
        try:
            async with _client.messages.stream(
                model=MODEL,
                max_tokens=MAX_TOKENS,
                system=build_system_prompt(),
                tools=TOOLS,
                messages=conversation,
            ) as stream:
                # Stream text chunks in real time
                async for text in stream.text_stream:
                    yield {"type": "text", "content": text}

                final = await stream.get_final_message()

        except anthropic.APIError as e:
            yield {"type": "error", "content": f"API error: {e}"}
            return

        # Build assistant message for conversation history
        assistant_content = []
        for block in final.content:
            if block.type == "text":
                assistant_content.append({"type": "text", "text": block.text})
            elif block.type == "tool_use":
                assistant_content.append({
                    "type": "tool_use",
                    "id": block.id,
                    "name": block.name,
                    "input": block.input,
                })

        conversation.append({"role": "assistant", "content": assistant_content})

        if final.stop_reason == "end_turn":
            break

        if final.stop_reason == "tool_use":
            tool_results = []
            for block in final.content:
                if block.type == "tool_use":
                    yield {"type": "tool", "name": block.name, "input": block.input}
                    result = run_bash(block.input.get("command", ""))
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": result,
                    })
            conversation.append({"role": "user", "content": tool_results})
        else:
            break

    _set_conversation(session_key, conversation)


# ── Telegram bot ──────────────────────────────────────────────────────────────

async def _tg_edit(message, text: str) -> None:
    """Edit a Telegram message, Markdown first then plain fallback."""
    try:
        await message.edit_text(text, parse_mode="Markdown")
    except Exception:
        try:
            await message.edit_text(text)
        except Exception:
            pass


async def _tg_send(bot, chat_id: int, text: str) -> None:
    """Send a new Telegram message, Markdown first then plain fallback."""
    try:
        await bot.send_message(chat_id=chat_id, text=text, parse_mode="Markdown")
    except Exception:
        await bot.send_message(chat_id=chat_id, text=text)


async def start_telegram_bot() -> None:
    import traceback
    from telegram import Update
    from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

    _user_locks: dict[str, asyncio.Lock] = {}

    async def _only_me(update: Update) -> bool:
        return update.effective_user and update.effective_user.id == TELEGRAM_USER_ID

    async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not await _only_me(update):
            return
        await update.message.reply_text(
            "👋 Merox Agent ready.\n\n"
            "Ask me anything about your infra — cluster, pods, services, logs.\n\n"
            "/clear — reset conversation"
        )

    async def cmd_clear(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not await _only_me(update):
            return
        _clear_session(f"tg_{update.effective_user.id}")
        await update.message.reply_text("Session cleared.")

    async def on_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not await _only_me(update):
            return

        key = f"tg_{update.effective_user.id}"
        chat_id = update.effective_chat.id

        # One request at a time per user
        if key not in _user_locks:
            _user_locks[key] = asyncio.Lock()
        if _user_locks[key].locked():
            await update.message.reply_text("⏳ Still processing your previous message...")
            return

        async with _user_locks[key]:
            # Placeholder message — edited live as chunks arrive
            sent = await context.bot.send_message(chat_id=chat_id, text="⏳")
            accumulated = ""
            last_edit = 0.0

            async for event in run_agent(update.message.text, key):
                if event["type"] == "text":
                    accumulated += event["content"]
                    now = time.time()
                    if now - last_edit >= _TG_EDIT_INTERVAL and len(accumulated) <= 4096:
                        try:
                            await sent.edit_text(accumulated + " ▌")
                            last_edit = now
                        except Exception:
                            pass
                elif event["type"] == "error":
                    accumulated = f"❌ {event['content']}"

            if not accumulated:
                accumulated = "No response."

            # Final edit: replace placeholder with complete response
            await _tg_edit(sent, accumulated[:4096])
            for i in range(4096, len(accumulated), 4096):
                await _tg_send(context.bot, chat_id, accumulated[i:i + 4096])

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
            retry_delay = 5
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            raise
        except Exception:
            print(f"Telegram bot error (retrying in {retry_delay}s):\n{traceback.format_exc()}", flush=True)
            for method in (tg_app.updater.stop, tg_app.stop, tg_app.shutdown):
                try:
                    await method()
                except Exception:
                    pass
            await asyncio.sleep(retry_delay)
            retry_delay = min(retry_delay * 2, 120)


# ── FastAPI app ───────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    _load_sessions_from_disk()
    if TELEGRAM_TOKEN and TELEGRAM_USER_ID:
        tg_task = asyncio.create_task(start_telegram_bot())
        print(f"Telegram bot enabled for user {TELEGRAM_USER_ID}.", flush=True)
    else:
        tg_task = None
        print("Telegram bot disabled (set TELEGRAM_BOT_TOKEN and TELEGRAM_USER_ID).", flush=True)
    yield
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
    return [{"session_id": k, "turns": len(v) // 2} for k, v in _sessions.items()]


@app.delete("/sessions/{session_id}")
def delete_session(session_id: str):
    _clear_session(session_id)
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
