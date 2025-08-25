"""Google Calendar API client wrapper."""

from __future__ import annotations

import os
from datetime import datetime
from typing import List, Optional

from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from google.auth import exceptions as google_exceptions
try:
	from zoneinfo import ZoneInfo  # Python 3.9+
except Exception:  # pragma: no cover
	ZoneInfo = None


SCOPES = ["https://www.googleapis.com/auth/calendar"]


class GoogleCalendarClient:
	def __init__(self, credentials_path: str, token_path: str):
		self.credentials_path = credentials_path
		self.token_path = token_path
		self.creds: Optional[Credentials] = None
		self._ensure_credentials()

	def _ensure_credentials(self):
		"""Load or obtain user credentials, handling expired/revoked tokens gracefully.

		Logic:
		1. If token file exists, load it.
		2. If invalid and refreshable, attempt refresh.
		3. On refresh failure (invalid_grant / revoked), delete token and perform new OAuth flow.
		4. Persist new token.
		"""
		creds = None
		if os.path.exists(self.token_path):
			try:
				creds = Credentials.from_authorized_user_file(self.token_path, SCOPES)
			except Exception:
				creds = None
		if not creds or not creds.valid:
			# Try refresh first if possible
			refreshed = False
			if creds and creds.expired and creds.refresh_token:
				try:
					creds.refresh(Request())
					refreshed = True
				except google_exceptions.RefreshError:
					# Token revoked / expired permanently -> discard and re-auth
					try:
						os.remove(self.token_path)
					except OSError:
						pass
					creds = None
			if not refreshed and (not creds or not creds.valid):
				# Interactive flow (attempt local server; fallback to console)
				flow = InstalledAppFlow.from_client_secrets_file(self.credentials_path, SCOPES)
				try:
					creds = flow.run_local_server(port=0)
				except Exception:
					# Probably headless environment; fallback to console prompt
					creds = flow.run_console()
			with open(self.token_path, "w", encoding="utf-8") as token_f:
				token_f.write(creds.to_json())
		self.creds = creds

	def _service(self):
		if not self.creds:
			self._ensure_credentials()
		return build("calendar", "v3", credentials=self.creds, cache_discovery=False)

	def create_event(
		self,
		summary: str,
		start: datetime,
		end: datetime,
		attendees: Optional[List[str]] = None,
		location: Optional[str] = None,
		description: Optional[str] = None,
		timezone: Optional[str] = None,
	) -> dict:
		service = self._service()
		# Determine timezone name to use
		configured_tz = timezone or os.getenv("TIMEZONE", "UTC")
		def _tz_name(dt: datetime) -> Optional[str]:
			# If datetime is naive, use configured timezone name
			if dt.tzinfo is None:
				return configured_tz
			# If timezone is a ZoneInfo, return its key; otherwise, omit timeZone
			if ZoneInfo is not None and isinstance(dt.tzinfo, ZoneInfo):
				return dt.tzinfo.key  # e.g., "Asia/Kolkata"
			return None

		start_tz = _tz_name(start)
		end_tz = _tz_name(end)

		body = {
			"summary": summary,
			"location": location,
			"description": description,
			"start": {"dateTime": start.isoformat()},
			"end": {"dateTime": end.isoformat()},
		}
		# Attach timeZone fields if we have names; otherwise rely on offset in dateTime
		if start_tz:
			body["start"]["timeZone"] = start_tz
		if end_tz:
			body["end"]["timeZone"] = end_tz
		if attendees:
			body["attendees"] = [{"email": e} for e in attendees]
		event = service.events().insert(calendarId="primary", body=body, sendUpdates="all").execute()
		return event

