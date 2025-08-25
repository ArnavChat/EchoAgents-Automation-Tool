# services/orchestrator/main.py
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import asyncio
from agent import Agent
from pydantic import BaseModel

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
agent = Agent()

class StyleRequest(BaseModel):
    style: str
    user_id: str | None = None

@app.get("/health")
def health():
    return {"status": "ok"}

@app.post("/handle-event")
async def handle_event(action: dict):
    result = await agent.handle_event(action)
    return {"result": result}

@app.post("/orchestrator")
async def orchestrator_entry(action: dict):
    return await handle_event(action)

@app.post("/email/style")
async def update_email_style(req: StyleRequest):
    updated = agent.apply_email_style(req.style)
    return updated
