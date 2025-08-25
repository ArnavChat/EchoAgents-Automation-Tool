# echoagents/services/orchestrator/agent.py
"""Orchestrator Agent: routes normalized messages, infers intent, creates calendar events, logs timeline, and sends confirmations."""

import os
import logging
from datetime import datetime, timedelta
from http_clients import TimelineClient, MsgProxyClient
from langgraph_client import LangGraphClient
from calendar_client import GoogleCalendarClient
import nlp


class Agent:
    def __init__(self, state=None):
        self.state = state or {}
        self.langgraph = LangGraphClient()
        self.timeline_client = TimelineClient()
        self.msg_proxy_client = MsgProxyClient()

        creds_path = os.getenv("GOOGLE_CREDENTIALS_PATH", os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "google", "credentials.json")))
        token_path = os.getenv("GOOGLE_TOKEN_PATH", os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "google", "token.json")))
        self.calendar = GoogleCalendarClient(credentials_path=creds_path, token_path=token_path)

    async def handle_event(self, action: dict):
        """Entry point. `action` is a NormalizedMessage from msg-proxy (source, user_id, text, attachments, timestamp)."""
        text = action.get("text") or action.get("message") or ""
        user_id = action.get("user_id", "unknown")

        intent = nlp.classify_intent(text)
        entities = nlp.extract_entities(text)

        results = {}

        if intent == "schedule_meeting":
            # Resolve start time (allow default if omitted)
            start_dt = entities.get("datetime")
            defaulted_time = False
            if not start_dt and entities.get("datetime_text"):
                start_dt = nlp.parse_datetime(entities["datetime_text"])
            if start_dt is None:
                # Default to tomorrow at 10:00 if time is missing
                now = datetime.utcnow()
                start_dt = (now + timedelta(days=1)).replace(hour=10, minute=0, second=0, microsecond=0)
                entities["datetime"] = start_dt
                defaulted_time = True

            attendees = entities.get("emails", [])
            if not attendees:
                # fallback: try to extract from text again
                attendees = nlp.extract_emails(text)

            end_dt = start_dt + timedelta(hours=1)
            summary = entities.get("summary") or f"Meeting with {', '.join(attendees) if attendees else user_id}"
            location = entities.get("location")
            description = entities.get("description") or f"Created by EchoAgents for {user_id}"

            try:
                event = self.calendar.create_event(
                    summary=summary,
                    start=start_dt,
                    end=end_dt,
                    attendees=attendees,
                    location=location,
                    description=description,
                )
                html_link = event.get("htmlLink")
                auto_time_note = " (defaulted to tomorrow 10:00)" if defaulted_time else ""
                msg = (
                    f"Meeting scheduled on {start_dt.isoformat()}{auto_time_note}. Details: {html_link}"
                    if html_link
                    else f"Meeting scheduled on {start_dt.isoformat()}{auto_time_note}"
                )
                tl = await self._send_and_timeline(user_id, intent, status="done", message=msg, payload={"event": event, "text": text, "entities": entities})
                results["calendar_event"] = event
                results.update(tl)
                return results
            except Exception as e:
                logging.exception("Failed to create calendar event")
                msg = f"Failed to schedule meeting: {e}"
                tl = await self._send_and_timeline(user_id, intent, status="failed", message=msg, payload={"text": text, "entities": entities})
                return {"error": "calendar_create_failed", "details": str(e), **tl}

        # Fallback: use LLM stubbed tools (write timeline + send message)
        prompt = f"Action Text: {text}\nState: {self.state}"
        tool_plan = self.langgraph.call_llm(prompt)
        for tool_name, tool_params in tool_plan.items():
            if tool_name == "write_timeline":
                timeline_data = {
                    "agent_name": tool_params.get("agent_name", "orchestrator"),
                    "action_type": tool_params.get("action_type", intent or "unknown_action"),
                    "payload": tool_params.get("payload", {"text": text}),
                    "status": tool_params.get("status", "done"),
                    "meta": tool_params.get("meta", None),
                }
                results[tool_name] = await self.timeline_client.write_timeline(timeline_data)
            elif tool_name == "send_message":
                results[tool_name] = await self.msg_proxy_client.send_message(tool_params)
            else:
                results[tool_name] = {"error": f"Unknown tool {tool_name}"}

        self.state["last_output"] = tool_plan
        self.langgraph.save_state(self.state)
        return results

    async def _send_and_timeline(self, user_id: str, action_type: str, status: str, message: str, payload: dict):
        """Helper to write timeline and send message."""
        timeline_data = {
            "agent_name": "orchestrator",
            "action_type": action_type,
            "payload": payload,
            "status": status,
            "meta": {"user_id": user_id},
        }
        tl = await self.timeline_client.write_timeline(timeline_data)
        sent = await self.msg_proxy_client.send_message({"recipient": user_id, "message": message})
        return {"write_timeline": tl, "send_message": sent}
