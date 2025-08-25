from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.responses import FileResponse, JSONResponse
import tempfile
import os
try:
	from dotenv import load_dotenv  # type: ignore
	load_dotenv(override=False)
except Exception:
	pass
import re
from stt import model as whisper_model
from tts import speak_text
import httpx
from datetime import datetime

app = FastAPI()

# CORS for frontend (default dev origin webpack:5173). Allow override via env ALLOWED_ORIGINS (comma-separated).
from fastapi.middleware.cors import CORSMiddleware
_origins = [o.strip() for o in os.getenv("ALLOWED_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173").split(",") if o.strip()]
app.add_middleware(
	CORSMiddleware,
	allow_origins=_origins,
	allow_credentials=True,
	allow_methods=["*"],
	allow_headers=["*"],
)


@app.get("/health")
def health():
	return {"status": "ok"}


@app.post("/voice/tts")
async def tts_endpoint(text: str = Form(...)):
	out = os.path.join(tempfile.gettempdir(), "tts_reply.wav")
	speak_text(text, out)
	return FileResponse(out, media_type="audio/wav")


@app.post("/voice/upload")
async def voice_upload(file: UploadFile = File(...)):
	# Save temp file
	fd, tmp = tempfile.mkstemp(suffix=os.path.splitext(file.filename or "input.wav")[1] or ".wav")
	os.close(fd)
	with open(tmp, "wb") as f:
		f.write(await file.read())
	# Transcribe
	result = whisper_model.transcribe(tmp)
	text = result.get("text", "").strip()
	os.remove(tmp)
	return {"text": text}


EMAIL_FALLBACK_DOMAINS = ["gmail.com", "outlook.com", "yahoo.com"]

def _normalize_transcript(text: str) -> str:
	"""Heuristic cleanup to reconstruct email addresses mis-transcribed by STT.

	Patterns handled:
	1. token 'at' domain ("john doe at gmail.com") -> "johndoe@gmail.com" (spaces removed)
	2. Spaced dots: "gmail . com" -> "gmail.com"
	3. Remove stray spaces around '@'.
	4. Collapse sequences that look like a single handle split by spaces.
	"""
	if not text:
		return text
	t = text
	# Join spaced dot segments in common domains first
	t = re.sub(r"\b(gmail|outlook|yahoo)\s*\.\s*com\b", r"\1.com", t, flags=re.I)
	# Convert ' at ' to '@' when followed by plausible domain
	t = re.sub(r"\b([A-Za-z0-9._%+-]{2,})\s+at\s+([A-Za-z0-9.-]+\.[A-Za-z]{2,})", lambda m: f"{m.group(1)}@{m.group(2)}", t, flags=re.I)
	# Remove spaces before @
	t = re.sub(r"\s*@\s*", "@", t)
	# Collapse spaces inside handle before @ if any remain (rare)
	t = re.sub(r"\b([A-Za-z0-9])\s+([A-Za-z0-9])(?=[A-Za-z0-9._%+-]*@)", r"\1\2", t)
	return t

@app.post("/voice/command")
async def voice_command(file: UploadFile = File(...), user_id: str = Form("voice_user")):
	"""
	Full single-step flow: accept audio, transcribe it, then forward as a 'voice' message to msg-proxy.
	(Return original & normalized transcripts.)
	"""
	# Save temp file
	fd, tmp = tempfile.mkstemp(suffix=os.path.splitext(file.filename or "input.wav")[1] or ".wav")
	os.close(fd)
	with open(tmp, "wb") as f:
		f.write(await file.read())

	# Transcribe (with error capture)
	try:
		result = whisper_model.transcribe(tmp)
		text_raw = result.get("text", "").strip()
	except Exception as e:
		os.remove(tmp)
		raise HTTPException(status_code=500, detail=f"Transcription failed: {e}")
	text = _normalize_transcript(text_raw)

	# Save a copy as input.wav at project root (best-effort)
	try:
		project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
		dest = os.path.join(project_root, "input.wav")
		# Copy original uploaded bytes (already written to tmp path)
		from shutil import copyfile
		copyfile(tmp, dest)
	except Exception:
		pass
	os.remove(tmp)

	# Build payload for msg-proxy
	payload = {
		"user_id": user_id,
		"text": text,
		"attachments": [],
		"timestamp": datetime.utcnow().isoformat()
	}

	msg_proxy_url = os.getenv(
		"MSG_PROXY_WEBHOOK_URL",
		(
			os.getenv("MSG_PROXY_URL", os.getenv("MSG_PROXY_BASE_URL", "http://localhost:8001").rstrip("/"))
			+ os.getenv("MSG_PROXY_VOICE_PATH", "/webhook/voice")
		),
	)

	# Forward to msg-proxy and return its details
	async with httpx.AsyncClient(timeout=15) as client:
		resp = await client.post(msg_proxy_url, json=payload)
		try:
			data = resp.json()
		except Exception:
			data = {"status": resp.status_code, "body": resp.text}

	return {"transcript": text, "original_transcript": text_raw, "proxy_result": data}


@app.post("/voice/forward")
async def voice_forward(payload: dict):
	"""Forward an already-reviewed transcript (no re-transcription).

	Payload expects:
	{
	  "text": "Schedule meeting ...",
	  "user_id": "web_client" (optional, default voice_user)
	}
	"""
	text = (payload or {}).get("text", "").strip()
	user_id = (payload or {}).get("user_id", "voice_user")
	if not text:
		raise HTTPException(status_code=400, detail="text required")
	forward_payload = {
		"user_id": user_id,
		"text": text,
		"attachments": [],
		"timestamp": datetime.utcnow().isoformat()
	}
	msg_proxy_url = os.getenv(
		"MSG_PROXY_WEBHOOK_URL",
		(
			os.getenv("MSG_PROXY_URL", os.getenv("MSG_PROXY_BASE_URL", "http://localhost:8001").rstrip("/"))
			+ os.getenv("MSG_PROXY_VOICE_PATH", "/webhook/voice")
		),
	)
	async with httpx.AsyncClient(timeout=15) as client:
		resp = await client.post(msg_proxy_url, json=forward_payload)
		try:
			data = resp.json()
		except Exception:
			data = {"status": resp.status_code, "body": resp.text}
	return {"forwarded": True, "proxy_result": data}

