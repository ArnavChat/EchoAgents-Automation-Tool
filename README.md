````markdown
# 🚀 EchoAgents Project

> **Voice-enabled scheduling & messaging system** powered by modular microservices + a lightweight React console.  
> It transcribes voice, extracts intent/entities, drafts & styles emails, creates Google Calendar events, and logs activity for observability.

---

## ✨ Features

- 🎙️ **Voice Capture** (STT with Whisper) + optional TTS responses
- 📬 **Message Normalization** across sources (voice, chat, future email)
- 🧠 **NLP Intent & Entity Extraction**
- 📅 **Google Calendar Integration** with timezone awareness
- 📜 **Timeline Logging** for audit & debugging

---

## 🏗️ High-Level Architecture

```mermaid
flowchart LR
  FE[React Frontend] -->|audio / commands| VA[voice-agent]
  FE -->|manual text| MP[msg-proxy]
  VA -->|normalized voice webhook| MP
  MP -->|NormalizedMessage JSON| ORCH[orchestrator]
  ORCH --> CAL[Google Calendar]
  ORCH --> TL[timeline]
  ORCH -->|Send message| MP
  MP -->|Timeline write (best effort)| TL
  TL --> FE
  ORCH --> FE
```
````

---

## 📂 Repository Structure

```
CalenderHandlerModule/
  scripts/                 # Launch scripts (PowerShell)
  services/
    orchestrator/          # Core intent + calendar & email drafting logic
    msg-proxy/             # Normalization + forwarding (webhook style)
    timeline/              # Timeline CRUD API (FastAPI + SQLAlchemy + Postgres)
    voice-agent/           # STT (Whisper), TTS, & upload endpoints
  google/                  # OAuth secrets (credentials.json / token.json)
frontend/
  public/                  # Static index.html
  src/                     # React app (single-page console)
  webpack.config.js        # Build + env injection
  package.json             # Frontend dependencies
venv311/                   # Python virtualenv (ignored)
.env / .env.example        # Environment configuration
```

---

## 🔧 Service Responsibilities

- **voice-agent** → Accepts audio uploads, transcribes via Whisper, performs heuristics to clean transcripts, forwards as `voice` source messages (or manual forward). Provides TTS.
- **msg-proxy** → Normalizes heterogeneous source payloads to `NormalizedMessage`; posts to timeline & orchestrator (best-effort) and exposes a generic send-message endpoint.
- **orchestrator** → Classifies intent, extracts entities, drafts/stylizes emails, creates calendar events (if configured), logs to timeline, sends user confirmations.
- **timeline** → Persists action events; simple query API for recent events.
- **frontend** → Developer console for recording, previewing transcripts, editing style, confirming email drafts, and inspecting raw JSON responses.

### 🔁 Request Flow (Voice Scheduling Example)

1. User records audio in frontend → POST `/voice/command` (voice-agent).
2. voice-agent transcribes + cleans → POST to `msg-proxy /webhook/voice` with normalized payload.
3. msg-proxy writes timeline (best-effort) + forwards message JSON to orchestrator.
4. orchestrator classifies intent (`schedule_meeting`), extracts datetime/emails, creates calendar event (if credentials available), writes timeline, and sends a confirmation message back via msg-proxy.
5. Frontend polls / displays resulting JSON (through the original response chain for voice path) and timeline entries (future UI extension).

### ✉️ Email Draft Flow

1. User instructs: “Send email to bob@example.com subject: Update make it concise”.
2. Orchestrator extracts recipients, subject, style; stores pending draft.
3. A styled preview is returned; frontend lets user apply alternate styles.
4. User confirms (sends “yes”) → orchestrator sends email via SMTP adapter → timeline updated.

---

## 🔑 Environment & Secrets

Use `.env` (copy from `.env.example`) for local dev; production should inject through deployment environment.

Key variables (see `.env.example` for the full annotated set):

| Variable                                                                  | Description                                   | Default (dev)                                                 |
| ------------------------------------------------------------------------- | --------------------------------------------- | ------------------------------------------------------------- |
| `DATABASE_URL`                                                            | Postgres SQLAlchemy URL                       | `postgresql://echoagent:echoagents@localhost:5432/echoagents` |
| `TIMEZONE`                                                                | IANA timezone used by orchestrator            | `Asia/Kolkata`                                                |
| `GOOGLE_CREDENTIALS_PATH` / `GOOGLE_TOKEN_PATH`                           | Google OAuth files                            | `google/credentials.json` / `google/token.json`               |
| `DUMMY_CALENDAR`                                                          | Use in-memory calendar when creds missing     | `0`                                                           |
| `TIMELINE_URL` / `MSG_PROXY_URL` / `ORCHESTRATOR_URL` / `VOICE_AGENT_URL` | Base service URLs                             | Built from ports                                              |
| `MSG_PROXY_WEBHOOK_URL`                                                   | Direct override for voice → msg-proxy webhook | Derived if unset                                              |
| `EMAIL_SMTP_HOST/PORT/USERNAME/PASSWORD/FROM`                             | Email sending                                 | —                                                             |
| `ALLOWED_ORIGINS`                                                         | CORS for voice-agent                          | `http://localhost:5173,...`                                   |
| `FRONTEND_DEV_PORT`                                                       | Webpack dev server port                       | `5173`                                                        |

Fallback logic: services prefer explicit full URLs (`*_URL`) else construct from `*_BASE_URL` + path pieces, else default to localhost + port.

Sensitive (never commit real values): `credentials.json`, `token.json`, `.env` (use `.env.example`).

---

## ⚙️ Installation

```powershell
# Clone repo
git clone <your-repo-url>
cd echoAgentsProject

# Create virtual environment
python -m venv venv311
.\venv311\Scripts\Activate.ps1

# Install dependencies
pip install -r requirements.txt
```

Place your Google OAuth `credentials.json` under `CalenderHandlerModule/google/`.

---

## ▶️ Running Services

### 1. Prepare Environment

```powershell
Copy-Item .env.example .env
notepad .env   # edit credentials, DB URL, email settings
```

Ensure Postgres user/db exist (example):

```sql
CREATE ROLE echoagent WITH LOGIN PASSWORD 'echoagents';
CREATE DATABASE echoagents OWNER echoagent;
```

### 2. Run All Backend Services

```powershell
./venv311/Scripts/Activate.ps1
./CalenderHandlerModule/scripts/run-all.ps1 -TimelinePort 8000 -MsgProxyPort 8001 -OrchestratorPort 8002 -VoiceAgentPort 8003
```

The script:

- Loads `.env` (without overwriting existing exported vars)
- Locates venv automatically
- Launches each service in a separate minimized PowerShell window

Override ports by passing parameters or editing `.env` to match.

### 3. Run an Individual Service (Example: Timeline)

```powershell
./venv311/Scripts/Activate.ps1
./CalenderHandlerModule/scripts/run-timeline.ps1 -Port 8000
```

### 4. Frontend (React Console)

```powershell
./venv311/Scripts/Activate.ps1  # only if you need backend simultaneously
cd ./frontend
npm install
# (optional) set service URLs for build
set VOICE_AGENT_URL=http://localhost:8003
set MSG_PROXY_URL=http://localhost:8001
set ORCHESTRATOR_URL=http://localhost:8002
npm run start
```

The dev server runs on `http://localhost:5173` (or `FRONTEND_DEV_PORT`). Webpack injects the above env vars at build time; if unset, the frontend falls back to standard localhost defaults.

### 5. Health Checks

```powershell
Invoke-WebRequest http://localhost:8000/timeline/events?limit=1 | Select-Object -ExpandProperty StatusCode
Invoke-WebRequest http://localhost:8001/health | Select-Object -ExpandProperty Content
Invoke-WebRequest http://localhost:8002/health | Select-Object -ExpandProperty Content
Invoke-WebRequest http://localhost:8003/health | Select-Object -ExpandProperty Content
```

### 6. Voice → Schedule Demo

1. Open frontend.
2. Click Start, speak: “Schedule a meeting with alice@example.com tomorrow at 10 am about roadmap”.
3. Stop → Transcript displays.
4. Click Forward → Orchestrator schedules event (if calendar configured).
5. Inspect JSON + timeline.

---

## 🔐 First-Time Google OAuth

1. Start orchestrator → Browser opens for consent
2. Approve access → `token.json` generated
3. For headless: copy-paste URL + code into console

If you see `invalid_grant`:

```powershell
del CalenderHandlerModule\google\token.json
# Restart orchestrator → re-auth
```

---

## 📅 Scheduling Flow

1. User says: _“Schedule a meeting with [alice@example.com](mailto:alice@example.com) tomorrow at 3 pm about roadmap”_
2. `voice-agent` → transcribes → sends to `msg-proxy`
3. `msg-proxy` → normalized action → orchestrator
4. `orchestrator`:

   - Intent = `schedule_meeting`
   - Entities = datetime, emails, summary
   - Creates Google Calendar event
   - Logs to timeline + confirmation back to `msg-proxy`

---

## 🌍 Timezone Handling

- Defaults to UTC if `TIMEZONE` not set
- Localizes naive datetimes before calendar creation
- Sets `start.timeZone` + `end.timeZone` explicitly

---

## 🐞 Error Handling

- Expired Google tokens → automatic re-auth
- Missing venv → fallback to global pip/uvicorn
- Service startup → auto-install lightweight dependencies

---

## 🛠️ Common Issues

| Symptom                 | Cause                     | Fix                                             |
| ----------------------- | ------------------------- | ----------------------------------------------- |
| `.env` vars not applied | Started services directly | Use `run-all.ps1` or ensure `find_dotenv` loads |
| `invalid_grant`         | Token expired             | Delete `token.json`, restart                    |
| `uvicorn not found`     | venv not activated        | Activate venv or set `$env:ECHO_VENV`           |
| Slow STT                | First Whisper download    | Cached after initial run                        |
| DB auth failed          | Wrong `DATABASE_URL`      | Create role/db & update `.env`                  |

---

## 🚀 Extending

- Add new channel → implement adapter in `msg-proxy`
- Add intents/entities → extend `nlp.py`
- Enhance timeline query filters / pagination
- Add websockets for live timeline updates
- Add dashboard → consume `/timeline` & orchestrator APIs

---

## 🔒 Security Best Practices

- ✅ Never commit `credentials.json` or `token.json`
- ✅ Limit OAuth scope to only `calendar`
- ✅ Rotate tokens periodically
- ✅ Use `.env` + secret manager in production

---

## 🧪 Testing (Planned)

- Unit → NLP intent/entity edge cases
- Integration → Mock Google API with `responses`
- Contract → Validate OpenAPI schema for clients

---

## 🗺️ Roadmap

- Authentication / user mapping
- Natural language **rescheduling & cancellation**
- Multi-language STT support
- Meeting notes summarization
- WebSocket push notifications

---

## 🖥️ Frontend Structure

```
frontend/
  public/
    index.html            # Root HTML
  src/
    index.tsx             # Main React entry (record, transcript, style, confirm)
    styles.css             # Theme + layout
  package.json            # Scripts: start / build
  webpack.config.js       # TypeScript + DefinePlugin env injection
```

Frontend Environment (build-time) variables:

- `VOICE_AGENT_URL`
- `MSG_PROXY_URL`
- `ORCHESTRATOR_URL`
- (Optional) `FRONTEND_DEV_PORT`

If not set when running `npm run start`, defaults to localhost ports.

---

Maintained by **EchoAgents Team** 🛠️ — keep this README in sync with evolutions.
