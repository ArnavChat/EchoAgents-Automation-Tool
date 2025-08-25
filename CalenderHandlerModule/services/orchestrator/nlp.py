# services/orchestrator/nlp.py
import os
import re
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional

from dateutil import parser as date_parser
try:
	from zoneinfo import ZoneInfo  # Python 3.9+
except Exception:  # pragma: no cover
	ZoneInfo = None  # Fallback; if missing, we won't localize


EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")


def extract_emails(text: str) -> List[str]:
	return EMAIL_RE.findall(text or "")


WEEKDAY_MAP = {
	'monday': 0, 'tuesday': 1, 'wednesday': 2, 'thursday': 3,
	'friday': 4, 'saturday': 5, 'sunday': 6
}

TIME_PATTERN = r"(?P<hour>\b(?:[01]?\d|2[0-3]))(?::(?P<minute>[0-5]\d))?\s*(?P<ampm>a\.?m\.?|p\.?m\.?)?"
WEEKDAY_TIME_RE = re.compile(r"\b(?P<weekday>monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b[^\n\r]{0,40}?" + TIME_PATTERN, re.IGNORECASE)

def _next_weekday(base: datetime, target_weekday: int) -> datetime:
	days_ahead = (target_weekday - base.weekday()) % 7
	if days_ahead == 0:  # same day -> advance a week to mean "next" occurrence if time already passed
		days_ahead = 7
	return base + timedelta(days=days_ahead)

def _localize(dt: datetime) -> datetime:
	if dt.tzinfo is None and ZoneInfo is not None:
		tz_name = os.getenv("TIMEZONE", "UTC")
		try:
			return dt.replace(tzinfo=ZoneInfo(tz_name))
		except Exception:
			return dt
	return dt

def parse_datetime(text: str) -> Optional[datetime]:
	if not text:
		return None
	now = datetime.utcnow()

	# 1. Custom weekday + time pattern (e.g. "Friday 5 p.m.")
	m = WEEKDAY_TIME_RE.search(text)
	if m:
		wd = m.group('weekday').lower()
		target_wd = WEEKDAY_MAP[wd]
		hour = int(m.group('hour'))
		minute = int(m.group('minute') or 0)
		ampm = m.group('ampm')
		if ampm:
			ampm_clean = ampm.replace('.', '').lower()
			if ampm_clean.startswith('p') and hour < 12:
				hour += 12
			if ampm_clean.startswith('a') and hour == 12:
				hour = 0
		# Determine the date of the next specified weekday
		base_local = now
		target_date = _next_weekday(base_local, target_wd)
		candidate = datetime(target_date.year, target_date.month, target_date.day, hour, minute)
		candidate = _localize(candidate)
		return candidate

	# 2. Fallback to dateutil fuzzy parse (may capture explicit dates)
	try:
		dt = date_parser.parse(text, fuzzy=True)
		dt = _localize(dt)
		return dt
	except Exception:
		return None


def extract_entities(text: str) -> Dict[str, Any]:
	"""Extract lightweight entities.

	Currently supported:
	- emails: list[str]
	- datetime: first parsed datetime (if any)
	- datetime_text: raw text when datetime not parsed
	- action_verbs: verbs indicating intent modifiers (cancel, reschedule, move, update)
	- summary_hints: list of capitalized words (could help match existing events)
	"""
	emails = extract_emails(text)
	dt = parse_datetime(text)
	action_verbs = []
	lower = (text or "").lower()
	for token in ["cancel", "delete", "remove", "reschedule", "move", "update", "shift"]:
		if token in lower:
			action_verbs.append(token)
	# crude summary hints: capitalized words excluding sentence starts common pronouns
	summary_hints = [w.strip(",. ") for w in re.findall(r"\b[A-Z][a-zA-Z0-9]+\b", text or "") if w.lower() not in {"i","we","the"}]
	return {
		"emails": emails,
		"datetime": dt,
		"datetime_text": text if dt is None else None,
		"action_verbs": action_verbs,
		"summary_hints": summary_hints,
	}


def classify_intent(text: str) -> str:
	t = (text or "").lower()
	if any(k in t for k in ["cancel", "delete", "remove"]):
		return "cancel_meeting"
	if any(k in t for k in ["reschedule", "move", "shift", "update", "change time"]):
		return "update_meeting"
	if any(k in t for k in ["schedule", "meeting", "calendar", "book", "invite"]):
		return "schedule_meeting"
	return "general"
