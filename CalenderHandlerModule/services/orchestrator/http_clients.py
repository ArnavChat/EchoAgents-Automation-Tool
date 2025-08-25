"""
HTTP clients for orchestrator with environment-configurable base URLs.

Environment variables:
- TIMELINE_BASE_URL (default: http://localhost:8000)
- MSG_PROXY_BASE_URL (default: http://localhost:8001)
"""

import os
import httpx
import asyncio
import logging

BASE_URL_TIMELINE = os.getenv("TIMELINE_BASE_URL", "http://localhost:8000")
BASE_URL_MSG_PROXY = os.getenv("MSG_PROXY_BASE_URL", "http://localhost:8001")


class TimelineClient:
    def __init__(self, base_url: str | None = None):
        self.base_url = base_url or BASE_URL_TIMELINE

    async def write_timeline(self, event_data: dict) -> dict:
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(f"{self.base_url}/timeline/events", json=event_data)
                response.raise_for_status()
                return response.json()
        except Exception as e:
            logging.warning(f"Timeline service unavailable: {e}")
            return {"warning": "timeline_unavailable", "echo": event_data}

    async def read_timeline(self, query_params: dict) -> dict:
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{self.base_url}/timeline/events", params=query_params)
            response.raise_for_status()
            return response.json()


class MsgProxyClient:
    def __init__(self, base_url: str | None = None):
        self.base_url = base_url or BASE_URL_MSG_PROXY

    async def send_message(self, message_data: dict) -> dict:
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(f"{self.base_url}/messages/send", json=message_data)
                response.raise_for_status()
                return response.json()
        except Exception as e:
            logging.warning(f"Msg-proxy service unavailable: {e}")
            return {"warning": "msg_proxy_unavailable", "echo": message_data}
