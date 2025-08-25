# services/msg-proxy/app.py
import os
try:
    from dotenv import load_dotenv  # type: ignore
    load_dotenv(override=False)
except Exception:
    pass
from fastapi import FastAPI, Request, HTTPException, Body
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import datetime
import httpx

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # tighten later
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

"""Configuration

Environment variables consumed (with fallbacks):
  TIMELINE_URL_BASE  (default http://localhost:8000)
  ORCHESTRATOR_URL_BASE (default http://localhost:8002)
  TIMELINE_EVENTS_PATH (default /timeline/events)
  ORCHESTRATOR_HANDLE_PATH (default /handle-event)
Backward compatibility: If TIMELINE_URL / ORCHESTRATOR_URL are provided fully qualified, they are used directly.
"""

_timeline_full = os.getenv("TIMELINE_URL")
_orchestrator_full = os.getenv("ORCHESTRATOR_URL")
if _timeline_full:
    TIMELINE_URL = _timeline_full
else:
    TIMELINE_URL = (
        os.getenv("TIMELINE_URL_BASE", os.getenv("TIMELINE_BASE_URL", "http://localhost:8000").rstrip("/"))
        + os.getenv("TIMELINE_EVENTS_PATH", "/timeline/events")
    )
if _orchestrator_full:
    ORCHESTRATOR_URL = _orchestrator_full
else:
    ORCHESTRATOR_URL = (
        os.getenv("ORCHESTRATOR_URL_BASE", "http://localhost:8002").rstrip("/")
        + os.getenv("ORCHESTRATOR_HANDLE_PATH", "/handle-event")
    )

class NormalizedMessage(BaseModel):
    source: str
    user_id: str
    text: str
    attachments: Optional[List[str]] = Field(default_factory=list)
    timestamp: datetime

class TimelineEntry(BaseModel):
    agent_name: str = "msg-proxy"
    action_type: str = "message_received"
    payload: dict
    status: str = Field("done", pattern="^(started|done|failed)$")
    meta: Optional[dict] = None
    

@app.post("/webhook/{source}")
async def inbound_webhook(source: str, request: Request):
    payload = await request.json()
    try:
        msg = normalize_message(source, payload)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

    timeline_entry = TimelineEntry(payload=msg.dict())

    results = {"timeline": None, "orchestrator": None}
    async with httpx.AsyncClient(timeout=10.0) as client:
        # Write to Timeline (best-effort)
        try:
            resp_timeline = await client.post(
                TIMELINE_URL,
                content=timeline_entry.json(),  # serialize with Pydantic's encoders
                headers={"Content-Type": "application/json"}
            )
            try:
                results["timeline"] = {"status": resp_timeline.status_code, "body": resp_timeline.json()}
            except Exception:
                results["timeline"] = {"status": resp_timeline.status_code, "body": resp_timeline.text}
        except Exception as e:
            results["timeline"] = {"error": str(e)}

        # Send to Orchestrator (best-effort)
        try:
            resp_orch = await client.post(
                ORCHESTRATOR_URL,
                content=msg.json(),  # same here
                headers={"Content-Type": "application/json"}
            )
            try:
                results["orchestrator"] = {"status": resp_orch.status_code, "body": resp_orch.json()}
            except Exception:
                results["orchestrator"] = {"status": resp_orch.status_code, "body": resp_orch.text}
        except Exception as e:
            results["orchestrator"] = {"error": str(e)}

    # Always return 200 to avoid webhook retries; include details for observability
    return {"status": "accepted", "details": results}

@app.post("/messages/send")
async def send_message_endpoint(message: dict = Body(...)):
    """
    Receive a message from orchestrator to send out.
    For now, just log and acknowledge.
    """
    # Here you can add logic to send message via Slack/Telegram/etc
    print("Sending message:", message)

    # Simulate success response
    return {"status": "message sent", "details": message}

def normalize_message(source: str, payload: dict) -> NormalizedMessage:
    """
    Convert incoming payloads from various sources to NormalizedMessage
    """
    if source == "slack":
        # Example Slack payload normalization
        user_id = payload.get("user") or payload.get("event", {}).get("user", "")
        text = payload.get("text") or payload.get("event", {}).get("text", "")
        attachments = [att.get("url") for att in payload.get("attachments", []) if "url" in att]
        ts_raw = payload.get("ts") or payload.get("event", {}).get("ts")
        try:
            timestamp = datetime.fromtimestamp(float(ts_raw)) if ts_raw is not None else datetime.utcnow()
        except Exception:
            timestamp = datetime.utcnow()
    elif source == "telegram":
        user_id = payload.get("message", {}).get("from", {}).get("id", "")
        text = payload.get("message", {}).get("text", "")
        attachments = []  # Add handling if needed
        try:
            timestamp = datetime.fromtimestamp(float(payload.get("message", {}).get("date")))
        except Exception:
            timestamp = datetime.utcnow()
    elif source == "whatsapp":
        # Example WhatsApp payload structure (depends on provider)
        user_id = payload.get("from", "")
        text = payload.get("body", "")
        attachments = []  # Add if available
        try:
            timestamp = datetime.fromisoformat(payload.get("timestamp"))
        except Exception:
            timestamp = datetime.utcnow()
    elif source == "email":
        user_id = payload.get("from", "")
        text = payload.get("subject", "") + "\n" + payload.get("body", "")
        attachments = payload.get("attachments", [])
        date_raw = payload.get("date")
        try:
            timestamp = datetime.fromisoformat(date_raw) if date_raw else datetime.utcnow()
        except Exception:
            timestamp = datetime.utcnow()
    elif source == "voice":
        # Simple passthrough for voice transcriptions
        user_id = payload.get("user_id", "voice_user")
        text = payload.get("text", "")
        attachments = payload.get("attachments", [])
        date_raw = payload.get("timestamp")
        try:
            # Accept ISO string or epoch seconds
            if isinstance(date_raw, (int, float)):
                timestamp = datetime.fromtimestamp(float(date_raw))
            elif isinstance(date_raw, str):
                timestamp = datetime.fromisoformat(date_raw)
            else:
                timestamp = datetime.utcnow()
        except Exception:
            timestamp = datetime.utcnow()
    else:
        raise ValueError(f"Unsupported source: {source}")

    return NormalizedMessage(
        source=source,
        user_id=str(user_id),
        text=text,
        attachments=attachments,
        timestamp=timestamp,
    )

@app.get("/health")
async def health():
    return {"status": "ok", "service": "msg-proxy"}
