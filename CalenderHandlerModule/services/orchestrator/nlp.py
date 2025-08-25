# services/orchestrator/nlp.py
import os
import re
from datetime import datetime
from typing import Dict, Any, List, Optional

from dateutil import parser as date_parser
try:
	from zoneinfo import ZoneInfo  # Python 3.9+
except Exception:  # pragma: no cover
	ZoneInfo = None  # Fallback; if missing, we won't localize


EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")


def extract_emails(text: str) -> List[str]:
	return EMAIL_RE.findall(text or "")


def parse_datetime(text: str) -> Optional[datetime]:
	try:
		dt = date_parser.parse(text, fuzzy=True)
		# If parsed datetime is naive, localize using configured TIMEZONE
		if dt is not None and dt.tzinfo is None and ZoneInfo is not None:
			tz_name = os.getenv("TIMEZONE", "UTC")
			try:
				dt = dt.replace(tzinfo=ZoneInfo(tz_name))
			except Exception:
				# If timezone name invalid, leave as naive
				pass
		return dt
	except Exception:
		return None


def extract_entities(text: str) -> Dict[str, Any]:
	emails = extract_emails(text)
	dt = parse_datetime(text)
	return {
		"emails": emails,
		"datetime": dt,
		"datetime_text": text if dt is None else None,
	}


def classify_intent(text: str) -> str:
	t = (text or "").lower()
	if any(k in t for k in ["schedule", "meeting", "calendar", "book", "invite"]):
		return "schedule_meeting"
	return "general"
