#!/usr/bin/env python3
"""
Merox Agent — HTTP service mode.

Runs on the Oracle server, listens on Tailscale IP only.
The thin client (client.py) connects from any device.

Start: python3 service.py
       uvicorn service:app --host 0.0.0.0 --port 8765
"""
import asyncio
import json
import os
import uuid
from collections import defaultdict
from typing import AsyncGenerator

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

import anthropic

from config import MODEL, MAX_TOKENS
from prompt import SYSTEM_PROMPT
from tools import kubernetes, server, git_tools

# ── Tool registry (shared with agent.py) ──────────────────────────────────────

ALL_TOOLS = (
    kubernetes.DEFINITIONS
    + server.DEFINITIONS
    + git_tools.DEFINITIONS
)

_HANDLERS = {
    **{t["name"]: lambda i, _n=t["name"]: kubernetes.handle(_n, i) for t in kubernetes.DEFINITIONS},
    **{t["name"]: lambda i, _n=t["name"]: server.handle(_n, i)     for t in server.DEFINITIONS},
    **{t["name"]: lambda i, _n=t["name"]: git_tools.handle(_n, i)  for t in git_tools.DEFINITIONS},
}


def dispatch(name: str, inp: dict) -> str:
    h = _HANDLERS.get(name)
    return h(inp) if h else f"Unknown tool: {name}"


# ── Session store (in-memory, resets on restart) ──────────────────────────────

_sessions: dict[str, list] = defaultdict(list)


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


class SessionResponse(BaseModel):
    session_id: str
    message_count: int


@app.get("/health")
def health():
    return {"status": "ok", "model": MODEL}


@app.get("/sessions")
def list_sessions():
    return [
        {"session_id": sid, "messages": len(msgs)}
        for sid, msgs in _sessions.items()
    ]


@app.delete("/sessions/{session_id}")
def clear_session(session_id: str):
    _sessions.pop(session_id, None)
    return {"cleared": session_id}


@app.post("/chat")
async def chat(req: ChatRequest):
    """Stream a response as Server-Sent Events (SSE)."""
    if not os.environ.get("ANTHROPIC_API_KEY"):
        raise HTTPException(503, "ANTHROPIC_API_KEY not set on server")

    session_id = req.session_id or str(uuid.uuid4())

    async def stream() -> AsyncGenerator[str, None]:
        # Send session_id first so client can reuse it
        yield f"data: {json.dumps({'type': 'session', 'session_id': session_id})}\n\n"

        conversation = list(_sessions[session_id])
        conversation.append({"role": "user", "content": req.message})

        client = anthropic.Anthropic()

        while True:
            response = await asyncio.to_thread(
                client.messages.create,
                model=MODEL,
                max_tokens=MAX_TOKENS,
                system=SYSTEM_PROMPT,
                tools=ALL_TOOLS,
                messages=conversation,
            )
            conversation.append({"role": "assistant", "content": response.content})

            if response.stop_reason == "tool_use":
                results = []
                for block in response.content:
                    if block.type == "tool_use":
                        # Notify client which tool is running
                        yield f"data: {json.dumps({'type': 'tool', 'name': block.name, 'input': block.input})}\n\n"
                        result = await asyncio.to_thread(dispatch, block.name, block.input)
                        results.append({
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "content": result,
                        })
                conversation.append({"role": "user", "content": results})

            else:
                text = next((b.text for b in response.content if b.type == "text"), "")
                yield f"data: {json.dumps({'type': 'text', 'content': text})}\n\n"
                break

        # Persist conversation
        _sessions[session_id] = conversation
        yield f"data: {json.dumps({'type': 'done'})}\n\n"

    return StreamingResponse(stream(), media_type="text/event-stream")


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    from config import SERVER_TS_IP

    host = SERVER_TS_IP or "0.0.0.0"
    port = int(os.getenv("AGENT_PORT", "8765"))

    print(f"Starting Merox Agent service on {host}:{port}")
    print("Connect from any Tailscale device with: merox-agent (client.py)")
    uvicorn.run("service:app", host=host, port=port, reload=False)
