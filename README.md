````markdown
# 🚀 EchoAgents Project

> **Voice-enabled scheduling & messaging system** powered by modular microservices.  
> It transcribes voice, extracts intent/entities, creates Google Calendar events, and logs activity for observability.

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
    A[User Voice] --> B[voice-agent]
    B -->|text| C[msg-proxy]
    C --> D[orchestrator]
    D --> E[Google Calendar]
    D --> F[timeline]
    D --> C
````

---

## 📂 Repository Structure

```
CalenderHandlerModule/
  scripts/                 # Launch scripts (PowerShell)
  services/
    orchestrator/          # Core intent + calendar logic
    msg-proxy/             # Normalization + forwarding
    timeline/              # Timeline CRUD API
    voice-agent/           # Speech-to-text / text-to-speech
  google/                  # ⚠️ OAuth secrets (ignored in git)
  venv311/                 # Python virtualenv (ignored)
docs/ or .docs/            # Documentation
```

---

## 🔧 Service Responsibilities

* **voice-agent** → Audio → STT (Whisper) → `msg-proxy`
* **msg-proxy** → Normalizes & forwards to orchestrator → (optional timeline)
* **orchestrator** → Intent parsing, entity extraction, Google Calendar calls, confirmation routing
* **timeline** → Stores all actions & metadata for observability

---

## 🔑 Environment & Secrets

Environment variables:

| Variable                                                   | Purpose                             |
| ---------------------------------------------------------- | ----------------------------------- |
| `TIMEZONE`                                                 | IANA timezone (e.g. `Asia/Kolkata`) |
| `GOOGLE_CREDENTIALS_PATH`                                  | Override for `credentials.json`     |
| `GOOGLE_TOKEN_PATH`                                        | Override for `token.json`           |
| `ORCHESTRATOR_URL` / `TIMELINE_URL` / `MSG_PROXY_BASE_URL` | Inter-service URLs                  |
| `MSG_PROXY_WEBHOOK_URL`                                    | Where `voice-agent` posts text      |

> ⚠️ **Sensitive files (never commit):**
>
> * `google/credentials.json`
> * `google/token.json`
> * `.env` or secret files

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

### Run All Services

```powershell
.\venv311\Scripts\Activate.ps1
.\CalenderHandlerModule\scripts\run-all.ps1 -TimelinePort 9000
```

Launches 4 services (msg-proxy, orchestrator, timeline, voice-agent).

### Run a Single Service (Example: Orchestrator)

```powershell
.\venv311\Scripts\Activate.ps1
.\CalenderHandlerModule\scripts\run-orchestrator.ps1 -Port 8002
```

### Verify Health

```powershell
Invoke-WebRequest http://localhost:8002/docs
Invoke-WebRequest http://localhost:8001/docs
```

Expect `200`.

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

1. User says: *“Schedule a meeting with [alice@example.com](mailto:alice@example.com) tomorrow at 3 pm about roadmap”*
2. `voice-agent` → transcribes → sends to `msg-proxy`
3. `msg-proxy` → normalized action → orchestrator
4. `orchestrator`:

   * Intent = `schedule_meeting`
   * Entities = datetime, emails, summary
   * Creates Google Calendar event
   * Logs to timeline + confirmation back to `msg-proxy`

---

## 🌍 Timezone Handling

* Defaults to UTC if `TIMEZONE` not set
* Localizes naive datetimes before calendar creation
* Sets `start.timeZone` + `end.timeZone` explicitly

---

## 🐞 Error Handling

* Expired Google tokens → automatic re-auth
* Missing venv → fallback to global pip/uvicorn
* Service startup → auto-install lightweight dependencies

---

## 🛠️ Common Issues

| Symptom             | Cause                  | Fix                                     |
| ------------------- | ---------------------- | --------------------------------------- |
| `Split-Path` error  | Old script logic       | Updated PowerShell with `$PSScriptRoot` |
| `invalid_grant`     | Token expired          | Delete `token.json`, restart            |
| `uvicorn not found` | venv not activated     | Activate venv or set `$env:ECHO_VENV`   |
| Slow STT            | First Whisper download | Cached after initial run                |

---

## 🚀 Extending

* Add new channel → implement adapter in `msg-proxy`
* Add intents/entities → extend `nlp.py`
* Persist timeline → migrate to SQLAlchemy DB
* Add dashboard → consume `/timeline` & orchestrator APIs

---

## 🔒 Security Best Practices

* ✅ Never commit `credentials.json` or `token.json`
* ✅ Limit OAuth scope to only `calendar`
* ✅ Rotate tokens periodically
* ✅ Use `.env` + secret manager in production

---

## 🧪 Testing (Planned)

* Unit → NLP intent/entity edge cases
* Integration → Mock Google API with `responses`
* Contract → Validate OpenAPI schema for clients

---

## 🗺️ Roadmap

* Authentication / user mapping
* Natural language **rescheduling & cancellation**
* Multi-language STT support
* Meeting notes summarization
* WebSocket push notifications

---

Maintained by **EchoAgents Team** 🛠️
Update this README as services & flows evolve.

