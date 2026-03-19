#!/usr/bin/env python3
"""
Merox Agent — HTTP service mode (Claude Agent SDK).

Runs on the Oracle server, listens on Tailscale IP only.
The thin client (client.py) connects from any device.

Requirements:
    pip install claude-agent-sdk fastapi uvicorn

Start:
    python3 service.py
    uvicorn service:app --host 0.0.0.0 --port 8765
"""
import json
import os
import uuid
from collections import defaultdict
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
from prompt import SYSTEM_PROMPT

# ── Session store ─────────────────────────────────────────────────────────────
# Maps our session_id → Claude CLI session_id (for resumption)
_sessions: dict[str, str] = {}

# ── FastAPI app ───────────────────────────────────────────────────────────────

app = FastAPI(title="Merox Agent", docs_url=None, redoc_url=None)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class ChatRequest(BaseModel):
    message: str
    session_id: str = ""  # empty = new session


@app.get("/health")
def health():
    return {"status": "ok", "sdk": "claude-agent-sdk", "model": MODEL}


@app.get("/sessions")
def list_sessions():
    return [{"session_id": sid} for sid in _sessions]


@app.delete("/sessions/{session_id}")
def clear_session(session_id: str):
    _sessions.pop(session_id, None)
    return {"cleared": session_id}


@app.post("/chat")
async def chat(req: ChatRequest):
    """Stream a response as Server-Sent Events (SSE)."""
    session_id = req.session_id or str(uuid.uuid4())
    claude_session_id = _sessions.get(session_id)

    async def stream() -> AsyncGenerator[str, None]:
        yield f"data: {json.dumps({'type': 'session', 'session_id': session_id})}\n\n"

        options = ClaudeAgentOptions(
            system_prompt=SYSTEM_PROMPT,
            allowed_tools=["Bash"],
            permission_mode="bypassPermissions",
            model=MODEL,
            resume=claude_session_id,  # None on first turn = new session
        )

        captured_claude_session = None
        full_text = ""

        try:
            async for message in query(prompt=req.message, options=options):

                if isinstance(message, SystemMessage) and message.subtype == "init":
                    captured_claude_session = message.data.get("session_id")

                elif isinstance(message, AssistantMessage):
                    for block in message.content:
                        if isinstance(block, TextBlock) and block.text:
                            full_text += block.text
                            yield f"data: {json.dumps({'type': 'text', 'content': block.text})}\n\n"
                        elif isinstance(block, ToolUseBlock):
                            yield f"data: {json.dumps({'type': 'tool', 'name': block.name, 'input': block.input})}\n\n"

                elif isinstance(message, ResultMessage):
                    # Fallback: some SDK versions only emit ResultMessage
                    if message.result and not full_text:
                        full_text = message.result
                        yield f"data: {json.dumps({'type': 'text', 'content': message.result})}\n\n"

        except CLINotFoundError:
            yield f"data: {json.dumps({'type': 'error', 'content': 'Claude CLI not found. Install: npm install -g @anthropic-ai/claude-code'})}\n\n"
        except CLIConnectionError as e:
            yield f"data: {json.dumps({'type': 'error', 'content': f'CLI connection error: {e}'})}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'content': str(e)})}\n\n"

        if captured_claude_session:
            _sessions[session_id] = captured_claude_session

        yield f"data: {json.dumps({'type': 'done'})}\n\n"

    return StreamingResponse(stream(), media_type="text/event-stream")


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    from config import SERVER_TS_IP

    host = SERVER_TS_IP or "0.0.0.0"
    port = int(os.getenv("AGENT_PORT", "8765"))

    print(f"Starting Merox Agent service on {host}:{port}")
    print("Uses Claude Code CLI — no ANTHROPIC_API_KEY needed.")
    uvicorn.run("service:app", host=host, port=port, reload=False)
