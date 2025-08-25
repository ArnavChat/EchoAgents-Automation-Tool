# services/orchestrator/nlp.py
import os
import re
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional, Tuple

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

	Adds basic email composition hints:
	- emails: list[str]
	- datetime / datetime_text (meeting scheduling)
	- action_verbs
	- summary_hints
	- subject (heuristic: 'subject: ...' line)
	- body (if 'body:' marker) else remainder after subject line
	- style (formal, casual, concise, bullet/bullet_summary)
	"""
	emails = extract_emails(text)
	dt = parse_datetime(text)
	action_verbs = []
	lower = (text or "").lower()
	for token in ["cancel", "delete", "remove", "reschedule", "move", "update", "shift"]:
		if token in lower:
			action_verbs.append(token)
	summary_hints = [w.strip(",. ") for w in re.findall(r"\b[A-Z][a-zA-Z0-9]+\b", text or "") if w.lower() not in {"i","we","the"}]

	subject, body = _extract_email_subject_body(text or "")
	styles = _extract_styles(text or "")
	style = styles[0] if styles else None
	return {
		"emails": emails,
		"datetime": dt,
		"datetime_text": text if dt is None else None,
		"action_verbs": action_verbs,
		"summary_hints": summary_hints,
		"subject": subject,
		"body": body,
		"style": style,
		"styles": styles,
	}

STYLE_KEYWORDS = {
	"formal": ["formal", "professional"],
	"casual": ["casual", "friendly", "informal"],
	"concise": ["concise", "short"],
	"bullet_summary": ["bullet", "bullets", "summary points", "bullet summary", "bullet_summary"],
}

def _extract_styles(text: str) -> List[str]:
	lower = text.lower()
	found: List[str] = []
	for style_key, kws in STYLE_KEYWORDS.items():
		for kw in kws:
			if kw in lower and style_key not in found:
				found.append(style_key)
	return found

def _extract_style(text: str) -> Optional[str]:  # backward compatibility
	styles = _extract_styles(text)
	return styles[0] if styles else None

def _extract_email_subject_body(text: str) -> Tuple[Optional[str], Optional[str]]:
	# Look for subject line OR inline 'subject:' fragment.
	lines = text.splitlines()
	subject = None
	body_lines: List[str] = []
	for i, line in enumerate(lines):
		if re.match(r"^\s*(subject|sub)\s*:\s*", line, flags=re.IGNORECASE):
			subject = re.sub(r"^\s*(subject|sub)\s*:\s*", "", line, flags=re.IGNORECASE).strip()
			body_lines = lines[i+1:]
			break
	# Inline pattern e.g. "Send email to X subject: Foo Bar Please ..."
	if subject is None:
		m = re.search(r"subject:\s*([^\.\n]+)", text, flags=re.IGNORECASE)
		if m:
			subject = m.group(1).strip()
			# If inline subject accidentally consumed a ' body:' marker, split it out.
			lower_subj = subject.lower()
			if ' body:' in lower_subj:
				parts = re.split(r"\s+body:\s*", subject, flags=re.IGNORECASE, maxsplit=1)
				if len(parts) == 2:
					subject, inline_body_fragment = parts[0].strip(), parts[1].strip()
					body_lines = [inline_body_fragment]
			# body is everything after the captured subject phrase (remaining text)
			post = text[m.end():]
			if post:
				post = post.strip()
				if post:
					body_lines.append(post)
	if subject is None:
		return None, None
	body_raw = "\n".join(body_lines).strip() if body_lines else None
	if body_raw:
		# Remove leading punctuation artifacts like starting '.' or '-' after split
		body_raw = re.sub(r"^[\s\.-]+", "", body_raw)
		# Remove any leading 'body:' label if present
		body_raw = re.sub(r"^body:\s*", "", body_raw, flags=re.IGNORECASE)
		# Remove trailing style directives "make it formal/casual/..."
		body_raw = re.sub(r"make it (formal|casual|concise|bullet( summary)?)\.?$", "", body_raw, flags=re.IGNORECASE).strip() or None
	return subject, body_raw


def classify_intent(text: str) -> str:
	t = (text or "").lower()
	if any(k in t for k in ["email", "send email", "draft email", "compose email", "mail to"]):
		return "send_email"
	if any(k in t for k in ["cancel", "delete", "remove"]):
		return "cancel_meeting"
	if any(k in t for k in ["reschedule", "move", "shift", "update", "change time"]):
		return "update_meeting"
	if any(k in t for k in ["schedule", "meeting", "calendar", "book", "invite"]):
		return "schedule_meeting"
	return "general"
