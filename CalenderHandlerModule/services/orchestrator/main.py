# services/orchestrator/main.py
from fastapi import FastAPI
import asyncio
from agent import Agent

app = FastAPI()
agent = Agent()

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
