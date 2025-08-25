# echoagents/services/orchestrator/test_agent.py

import asyncio
from echoagents.services.orchestrator.agent import Agent

async def test_agent():
    agent = Agent()
    action = {
        "type": "schedule_meeting",
        "params": {"time": "2025-08-15 10:00", "attendees": ["alice@example.com"]}
    }
    results = await agent.handle_event(action)
    print("Agent results:", results)

if __name__ == "__main__":
    asyncio.run(test_agent())
