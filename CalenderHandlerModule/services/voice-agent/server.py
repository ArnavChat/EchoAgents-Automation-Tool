from fastapi import FastAPI, UploadFile, File, Form
from fastapi.responses import FileResponse, JSONResponse
import tempfile
import os
from stt import model as whisper_model
from tts import speak_text
import httpx
from datetime import datetime

app = FastAPI()


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


@app.post("/voice/command")
async def voice_command(file: UploadFile = File(...), user_id: str = Form("voice_user")):
	"""
	Accept audio, transcribe it, then forward as a 'voice' message to msg-proxy.
	Returns orchestrator processing result.
	"""
	# Save temp file
	fd, tmp = tempfile.mkstemp(suffix=os.path.splitext(file.filename or "input.wav")[1] or ".wav")
	os.close(fd)
	with open(tmp, "wb") as f:
		f.write(await file.read())

	# Transcribe
	result = whisper_model.transcribe(tmp)
	text = result.get("text", "").strip()
	os.remove(tmp)

	# Build payload for msg-proxy
	payload = {
		"user_id": user_id,
		"text": text,
		"attachments": [],
		"timestamp": datetime.utcnow().isoformat()
	}

	msg_proxy_url = os.getenv("MSG_PROXY_WEBHOOK_URL", "http://localhost:8001/webhook/voice")

	# Forward to msg-proxy and return its details
	async with httpx.AsyncClient(timeout=15) as client:
		resp = await client.post(msg_proxy_url, json=payload)
		try:
			data = resp.json()
		except Exception:
			data = {"status": resp.status_code, "body": resp.text}

	return {"transcript": text, "proxy_result": data}

