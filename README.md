# EchoAgents Project Documentation

## Overview

EchoAgents is a modular, voice-enabled scheduling and messaging system composed of multiple microservices. It transcribes voice input, normalizes messages, extracts intent and entities, schedules calendar events (Google Calendar), and logs actions to a timeline for observability.

Core capabilities:

- Voice capture (STT) and optional TTS response.
- Message normalization across sources (voice, potential future chat/email hooks).
- NLP-based intent classification and entity extraction.
- Automated Google Calendar event creation with timezone awareness.
- Timeline logging for auditing and debugging.

## High-Level Architecture & Data Flow

```
[User Voice] -> voice-agent -> (text) -> msg-proxy -> orchestrator -> Google Calendar
                                                 |                     |
                                                 +----> timeline <-----+
                                                 +----> msg-proxy (confirmation back to user)
```

1. User speaks; `voice-agent` records audio and transcribes via Whisper.
2. Transcribed text sent to `msg-proxy` webhook (source=voice).
3. `msg-proxy` normalizes payload and forwards to `orchestrator`.
4. `orchestrator` parses intent/entities (schedule meeting) and calls Google Calendar.
5. Successful event + metadata written to `timeline` and a confirmation message sent back through `msg-proxy`.
6. Timeline service provides an API surface for querying historical actions.

## Repository Structure (Relevant Portions)

```
CalenderHandlerModule/
  scripts/
    run-all.ps1              # Launch all services in separate PowerShell windows
    run-orchestrator.ps1     # Launch only orchestrator (for focused dev)
  services/
    orchestrator/
      main.py                # FastAPI entrypoint
      agent.py               # Orchestrator logic
      nlp.py                 # Intent/entity parsing
      calendar_client.py     # Google Calendar wrapper (token refresh + re-auth)
      requirements.txt
    msg-proxy/
      app.py                 # Normalization + forwarding to orchestrator & timeline
      requirements.txt
    timeline/
      main.py                # Timeline CRUD API
      requirements.txt
    voice-agent/
      server.py              # STT endpoint, forwards text to msg-proxy
      stt.py / tts.py        # Speech utilities
      requirements.txt
  google/
    credentials.json         # OAuth client secrets (DO NOT COMMIT)
    token.json               # Generated OAuth access/refresh (DO NOT COMMIT)
venv311/                     # Python virtual environment (ignored)
.docs/ or docs/              # Documentation (this file)
```

## Service Responsibilities

- voice-agent: Accepts audio, performs speech-to-text (Whisper), optional text-to-speech, then POSTs normalized voice content to msg-proxy.
- msg-proxy: Receives messages from multiple sources, normalizes schema, writes timeline entry (optional) and forwards actionable events to orchestrator.
- orchestrator: Determines intent (e.g., schedule meeting), extracts datetime/emails/summary, creates calendar events, logs timeline, and routes confirmation.
- timeline: Persists timeline events (actions, status, metadata) for audit & debugging.

## Environment & Secrets

Environment variables (examples):

- TIMEZONE: IANA timezone (e.g. `Asia/Kolkata`). Used by orchestrator for default datetime interpretation.
- GOOGLE_CREDENTIALS_PATH: Override path to `credentials.json` (optional).
- GOOGLE_TOKEN_PATH: Override path to `token.json` (optional).
- ORCHESTRATOR_URL / TIMELINE_URL / MSG_PROXY_BASE_URL / TIMELINE_BASE_URL: Inter-service URLs (injected by launch scripts).
- MSG_PROXY_WEBHOOK_URL: Where voice-agent posts transcribed text.

Sensitive files (should be .gitignored):

- `google/credentials.json`
- `google/token.json`
- Any `.env` style secret files.

## Installation & Setup

1. Clone repository.
2. Create virtual environment (if not present):
   ```powershell
   python -m venv venv311
   .\venv311\Scripts\Activate.ps1
   ```
3. (Optional) Pre-install shared libs for speed:
   ```powershell
   pip install fastapi uvicorn httpx google-api-python-client google-auth-oauthlib sqlalchemy pydantic torch
   ```
4. Place your Google OAuth `credentials.json` under `CalenderHandlerModule/google/`.

## Running All Services

From project root:

```powershell
# Activate venv
.\venv311\Scripts\Activate.ps1
# Launch (with optional custom ports)
.\CalenderHandlerModule\scripts\run-all.ps1 -TimelinePort 9000
```

This opens four minimized PowerShell windows (msg-proxy, orchestrator, timeline, voice-agent). Logs indicate dependency install then Uvicorn startup.

### Running a Single Service (Example: Orchestrator)

```powershell
.\venv311\Scripts\Activate.ps1
.\CalenderHandlerModule\scripts\run-orchestrator.ps1 -Port 8002
```

### Verifying Services

After startup, test health (assuming default ports):

```powershell
Invoke-WebRequest http://localhost:8002/docs | Select-Object -ExpandProperty StatusCode
Invoke-WebRequest http://localhost:8001/docs | Select-Object -ExpandProperty StatusCode
```

Expect `200` responses.

## First-Time Google OAuth Flow

On first orchestrator start (or after token revocation):

1. Browser window opens for consent.
2. Approve Calendar access.
3. New `token.json` written automatically.
   If running headless: console flow prints a URL and code; follow instructions.

If you see error `invalid_grant: Token has been expired or revoked`:

- Delete `token.json`.
- Restart orchestrator to re-auth.

## Scheduling Flow (Detailed)

1. User voice command: "Schedule a meeting with alice@example.com tomorrow at 3 pm about roadmap".
2. voice-agent transcribes -> `{ text: "Schedule...", source: "voice" }` POST to msg-proxy.
3. msg-proxy wraps into normalized action: `{ user_id, text, source, timestamp }` -> orchestrator.
4. orchestrator:
   - `nlp.classify_intent` => `schedule_meeting`
   - `nlp.extract_entities` => emails, datetime string, summary tokens
   - fallback default time if missing (tomorrow 10:00 local)
   - uses `calendar_client.create_event`
5. calendar_client:
   - Ensures credentials (refresh or re-auth)
   - Posts event to Google Calendar with timezone fields
6. orchestrator builds confirmation message, writes timeline entry, posts message back via msg-proxy.
7. msg-proxy could then deliver to a UI or chat integration (future).

## Timezone Handling

- Orchestrator reads `TIMEZONE` (default UTC if unset).
- Parsed naive datetimes are localized to that timezone before calendar creation.
- calendar_client sets `start.timeZone` and `end.timeZone` if a zone name is known.

## Error Handling Highlights

- Expired Google tokens trigger re-auth (automatic fallbacks added in `calendar_client.py`).
- Missing venv: scripts fall back to global `pip`/`uvicorn` but warn.
- Service startup dependency install performed idempotently each launch (kept light by already-cached wheels).

## Common Issues & Resolutions

| Symptom                            | Cause                  | Resolution                                         |
| ---------------------------------- | ---------------------- | -------------------------------------------------- |
| `Split-Path` error in older script | Fragile path logic     | Updated `run-all.ps1` uses `$PSScriptRoot`         |
| `invalid_grant` on startup         | Revoked/expired token  | Delete `token.json`, restart, re-consent           |
| `uvicorn not found`                | Venv not detected      | Activate venv or set `$env:ECHO_VENV` to venv root |
| STT slow on first run              | Whisper model download | Allow initial download, cached afterward           |

## Extending the System

- Add new input channel: Implement adapter in msg-proxy to accept Slack/email and normalize to internal schema.
- Additional intents: Expand `nlp.py` classification and entity extraction logic.
- Persistence: Add database models to timeline (currently minimal) via SQLAlchemy migrations.
- Frontend: Consume `/timeline` and orchestrator endpoints for a dashboard.

## Security & Hygiene

- Never commit `credentials.json` / `token.json`.
- Restrict OAuth client to necessary scope only (`calendar`).
- Consider rotating refresh tokens periodically.
- Use `.env` + secrets manager in production (instead of inline scripts).

## Testing (Suggested Next Steps)

Add basic tests (future enhancement):

- Unit: nlp intent classification edge cases.
- Integration: schedule meeting flow using mocked Google API (e.g., `httpretty` or `responses`).
- Contract: Generate OpenAPI schema and validate against frontend client types.

## TypeScript Client Generation (Optional)

If you add a frontend and want typed clients:

```powershell
npx openapi-typescript http://localhost:8002/openapi.json -o .\frontend\types\orchestrator.d.ts
```

(Install Node & openapi-typescript globally or use npx.)

## Roadmap Ideas

- Authentication / user mapping.
- Natural language rescheduling & cancellation.
- Multi-language STT support.
- Meeting notes summarization post-event.
- WebSocket push notifications.

---

Maintained by the EchoAgents team. Update this document as services or flows evolve.
