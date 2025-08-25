# echoagents/services/orchestrator/agent.py
"""Orchestrator Agent: routes normalized messages, infers intent, creates calendar events, logs timeline, and sends confirmations."""

import os
import logging
from types import SimpleNamespace
from datetime import datetime, timedelta
from dotenv import load_dotenv
from http_clients import TimelineClient, MsgProxyClient
from langgraph_client import LangGraphClient
from calendar_client import GoogleCalendarClient
import nlp
from email_adapter import EmailAdapter
from style import rewrite_style


class Agent:
    def __init__(self, state=None):
        # Load .env once (safe no-op if already loaded)
        load_dotenv(override=False)
        self.state = state or {}
        self.langgraph = LangGraphClient()
        self.timeline_client = TimelineClient()
        self.msg_proxy_client = MsgProxyClient()
        # Resolve credential paths robustly: allow relative .env entries like 'google/credentials.json'
        def _resolve_path(env_value: str | None, default_rel: str) -> str:
            base_default = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))  # CalenderHandlerModule
            if not env_value:
                return os.path.join(base_default, default_rel)
            # If absolute and exists, use directly.
            if os.path.isabs(env_value):
                return env_value
            # Try relative to project root (two levels up from this file)
            candidate1 = os.path.join(base_default, env_value)
            if os.path.exists(candidate1):
                return candidate1
            # Try relative to current working directory (as provided)
            if os.path.exists(env_value):
                return os.path.abspath(env_value)
            # Finally fall back to default relative
            return os.path.join(base_default, default_rel)

        creds_path = _resolve_path(os.getenv("GOOGLE_CREDENTIALS_PATH"), os.path.join("google", "credentials.json"))
        token_path = _resolve_path(os.getenv("GOOGLE_TOKEN_PATH"), os.path.join("google", "token.json"))
        # Calendar is optional for email flows; fail gracefully if creds missing
        self.calendar_creds_path = creds_path
        logging.info(f"Calendar credential path resolved to: {creds_path} (exists={os.path.exists(creds_path)})")
        try:
            if os.path.exists(creds_path):
                self.calendar = GoogleCalendarClient(credentials_path=creds_path, token_path=token_path)
            else:
                logging.warning(f"Calendar credentials not found at {creds_path}; calendar features disabled.")
                self.calendar = None
        except FileNotFoundError:
            logging.warning("Calendar credentials file missing; calendar disabled.")
            self.calendar = None
        except Exception as e:
            logging.exception("Failed to initialize calendar client; disabling calendar features.")
            self.calendar = None
        # Optional dummy calendar for local dev/testing (set DUMMY_CALENDAR=1)
        if not self.calendar and os.getenv("DUMMY_CALENDAR") == "1":
            logging.info("Using dummy in-memory calendar client (DUMMY_CALENDAR=1)")
            def _dummy_create_event(**kwargs):
                from datetime import datetime
                ev = {"id": f"dummy-{int(datetime.utcnow().timestamp())}", **kwargs, "htmlLink": None}
                return ev
            self.calendar = SimpleNamespace(create_event=_dummy_create_event)
        self.email_adapter = EmailAdapter()

    async def handle_event(self, action: dict):
        """Entry point. `action` is a NormalizedMessage from msg-proxy (source, user_id, text, attachments, timestamp)."""
        text = action.get("text") or action.get("message") or ""
        user_id = action.get("user_id", "unknown")

        intent = nlp.classify_intent(text)
        entities = nlp.extract_entities(text)

        # If there's a pending email draft, treat simple yes/no confirmations regardless of detected intent
        lowered = text.strip().lower()
        if self.state.get("pending_email") and lowered in {"yes", "y", "send", "confirm", "no", "n", "cancel"}:
            return await self._handle_email_confirmation(lowered, user_id)

        results = {}
        if intent == "schedule_meeting":
            if not self.calendar:
                msg = "Calendar features are not configured (credentials missing)."
                ack = await self._send_and_timeline(user_id, intent, status="failed", message=msg, payload={"text": text, "missing_credentials_path": self.calendar_creds_path})
                return {"error": "calendar_disabled", "missing_credentials_path": self.calendar_creds_path, **ack}
            # Resolve start time (allow default if omitted)
            start_dt = entities.get("datetime")
            defaulted_time = False
            if not start_dt and entities.get("datetime_text"):
                start_dt = nlp.parse_datetime(entities["datetime_text"])
            if start_dt is None:
                now = datetime.utcnow()
                start_dt = (now + timedelta(days=1)).replace(hour=10, minute=0, second=0, microsecond=0)
                entities["datetime"] = start_dt
                defaulted_time = True

            attendees = entities.get("emails", [])
            if not attendees:
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
                    f"Meeting scheduled on {start_dt.isoformat()}{auto_time_note}. Details: {html_link}" if html_link else f"Meeting scheduled on {start_dt.isoformat()}{auto_time_note}"
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

        elif intent in {"cancel_meeting", "update_meeting"}:
            msg = f"Intent '{intent}' recognized but this capability is not yet fully implemented."
            ack = await self._send_and_timeline(user_id, intent, status="done", message=msg, payload={"text": text, "entities": entities})
            return {"info": msg, **ack}
        elif intent == "send_email":
            return await self._handle_email_draft(user_id, text, entities)

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

    async def _handle_email_confirmation(self, confirm_text: str, user_id: str):
        pending = self.state.get("pending_email")
        if not pending:
            return {"email": {"status": "no_pending"}}
        if confirm_text in {"yes", "y", "send", "confirm"}:
            try:
                message_id = self.email_adapter.send(
                    to=pending["to"],
                    subject=pending["subject"],
                    body=pending["styled_body"],
                    cc=pending.get("cc"),
                )
                tl = await self._send_and_timeline(
                    user_id,
                    "email_sent",
                    status="done",
                    message=f"Email sent to {', '.join(pending['to'])} (id {message_id}).",
                    payload={"subject": pending["subject"], "style": pending["style"], "message_id": message_id},
                )
                self.state.pop("pending_email", None)
                return {"email": {"status": "sent", "message_id": message_id}, **tl}
            except Exception as e:
                tl = await self._send_and_timeline(user_id, "email_sent", status="failed", message=f"Failed to send email: {e}", payload={"error": str(e)})
                self.state.pop("pending_email", None)
                return {"error": "email_send_failed", **tl}
        elif confirm_text in {"no", "n", "cancel"}:
            self.state.pop("pending_email", None)
            tl = await self._send_and_timeline(user_id, "email_cancelled", status="done", message="Email draft discarded.", payload={})
            return {"email": {"status": "cancelled"}, **tl}
        # Should not reach here due to gating, but safe fallback
        return {"email": {"status": "unknown_confirmation"}}

    async def _handle_email_draft(self, user_id: str, text: str, entities: dict):
        to = entities.get("emails") or []
        subject = entities.get("subject") or "(No Subject)"
        # Initial raw body guess from NLP or fallback heuristic then sanitized
        raw_body_original = entities.get("body") or _strip_after_subject(text)
        raw_body = _sanitize_email_body(raw_body_original, subject, text)
        styles_list = entities.get("styles") or ([entities.get("style")] if entities.get("style") else [])
        styled_body = raw_body
        applied = "(none)"
        if styles_list:
            # Sequentially apply style rewrites (idempotent functions)
            for s in styles_list:
                styled_body = rewrite_style(styled_body, s)
            applied = ",".join(styles_list)
        preview = (
            f"Subject: {subject}\nStyles: {applied}\n--- Draft Preview ---\n{styled_body}\n---------------------\nSend this email? (yes/no)"
        )
        self.state["pending_email"] = {
            "to": to,
            "subject": subject,
            "raw_body": raw_body,
            "styled_body": styled_body,
            "style": styles_list[-1] if styles_list else None,
            "styles": styles_list,
        }
        tl = await self._send_and_timeline(
            user_id,
            "email_draft",
            status="pending",
            message="Draft email prepared. Awaiting confirmation.",
            payload={
                "to": to,
                "subject": subject,
                "styles": styles_list,
                "raw_body": raw_body,
                "styled_body": styled_body,
                "changed": styled_body.strip() != raw_body.strip(),
            },
        )
        await self.msg_proxy_client.send_message({"recipient": user_id, "message": preview})
        return {"email": {"status": "pending_confirmation", "to": to, "subject": subject, "styles": styles_list, "raw_body": raw_body, "styled_body": styled_body, "preview_message": preview}, **tl}

    def apply_email_style(self, style: str):
        """Apply a single style to the pending email draft (recomputed from raw_body).

        Returns updated pending email dict or error dict.
        """
        pending = self.state.get("pending_email")
        if not pending:
            return {"error": "no_pending_email"}
        raw = pending.get("raw_body") or pending.get("styled_body")
        if not raw:
            return {"error": "empty_body"}
        styled = rewrite_style(raw, style)
        pending["styled_body"] = styled
        pending["style"] = style
        pending["styles"] = [style]
        self.state["pending_email"] = pending
        return {"email": {**pending, "status": "pending_confirmation"}}

# Helper used by email draft fallback to derive body when inline subject used
def _strip_after_subject(text: str) -> str:
    if not text:
        return text
    # Remove everything up to and including 'subject: <something>' and treat remainder as body
    import re
    m = re.search(r"subject:\s*([^\.\n]+)([\.|\n\r]+)(.*)$", text, flags=re.IGNORECASE)
    if m:
        remainder = m.group(3).strip()
        # Remove trailing style directives like 'make it formal.'
        remainder = re.sub(r"make it (formal|casual|concise|bullet( summary)?)\.?$", "", remainder, flags=re.IGNORECASE).strip()
        return remainder or text
    return text


# Body sanitization: remove command phrasing and style directives from body text once subject is extracted.
import re
COMMAND_PREFIX_RE = re.compile(r"^(?:please\s+)?(?:send|draft|compose)\s+(?:an\s+)?email\s+to.*?subject:\s*[^\.!?\n\r]+[\.!?\s]*", re.IGNORECASE)
STYLE_DIRECTIVE_RE = re.compile(r"\b(make it|be|make this)\s+(formal|casual|concise|bullet(?: summary)?)\b[\.!?]*", re.IGNORECASE)

def _sanitize_email_body(candidate: str, subject: str, full_text: str) -> str:
    if not candidate:
        return subject  # fall back to using subject as minimal body
    body = candidate.strip()
    # If body still includes the whole command line, strip command prefix up to and including subject phrase.
    body = COMMAND_PREFIX_RE.sub("", body).strip()
    # Remove any residual 'subject: <subject>' fragments accidentally carried over
    subj_pattern = re.compile(rf"subject:\s*{re.escape(subject)}\s*", re.IGNORECASE)
    body = subj_pattern.sub("", body).strip()
    # Remove style directive trailing phrases (e.g., 'Make it casual')
    body = STYLE_DIRECTIVE_RE.sub("", body).strip()
    # Remove repeated email addresses lines that were instruction artifacts
    body = re.sub(r"^to:\s*.+$", "", body, flags=re.IGNORECASE).strip()
    # If body ended up empty after cleanup, fall back to a sentence from subject
    if not body:
        body = subject.strip()
    return body
