"""Rule-based style transformations for drafted email/text content.

Lightweight, deterministic transforms keep latency low and provide
auditable output (we can later layer an LLM fallback behind an env flag).

Supported styles: formal, casual, concise, bullet_summary (alias bullet)

Each transform should be:
 - Idempotent when run twice.
 - Avoid hallucination: do not add facts.
 - Preserve email addresses / URLs verbatim.
"""

from __future__ import annotations
import re
from typing import Callable

_FILLER_PHRASES = [
    "just", "really", "very", "kind of", "sort of", "basically", "actually",
    "I think", "I believe", "it seems", "in order to", "at this point in time",
]

def _strip_extra_whitespace(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()

def _ensure_sentence_punctuation(text: str) -> str:
    return re.sub(r"([^.!?\s])\s*(\n|$)", r"\1. ", text).strip()

def formalize(text: str) -> str:
    t = text.strip()
    # Expand some common contractions (simple heuristic)
    contractions = {
        "can't": "cannot", "won't": "will not", "don't": "do not",
        "I'm": "I am", "it's": "it is", "that's": "that is", "we're": "we are",
        "let's": "let us", "you're": "you are", "didn't": "did not",
    }
    def repl(m):
        c = m.group(0)
        return contractions.get(c, c)
    t = re.sub(r"\b(?:" + "|".join(map(re.escape, contractions.keys())) + r")\b", repl, t)
    # Remove slang-ish fillers
    t = re.sub(r"\b(okay|ok|yeah)\b", "Yes", t, flags=re.IGNORECASE)
    # Courtesy framing
    if not re.search(r"^dear |^hello |^hi ", t, flags=re.IGNORECASE):
        t = "Hello,\n\n" + t
    if not re.search(r"(kind regards|regards|sincerely)", t, flags=re.IGNORECASE):
        t = t.rstrip() + "\n\nKind regards,\nEcho Agent"
    return _strip_extra_whitespace(t)

def casualize(text: str) -> str:
    t = text.strip()
    # Lighten tone
    if not re.search(r"^hey|^hi|^hello", t, flags=re.IGNORECASE):
        t = "Hey, " + t
    # Remove overly formal closings
    t = re.sub(r"\n(?:kind regards|regards|sincerely)[^\n]*", "", t, flags=re.IGNORECASE)
    if not re.search(r"cheers|thanks", t, flags=re.IGNORECASE):
        t = t.rstrip() + "\n\nThanks!"
    return _strip_extra_whitespace(t)

def make_concise(text: str) -> str:
    t = text
    for phrase in _FILLER_PHRASES:
        t = re.sub(r"\b" + re.escape(phrase) + r"\b", "", t, flags=re.IGNORECASE)
    # Collapse spaces and remove double spaces after removal
    t = _strip_extra_whitespace(t)
    return t

def bulletize(text: str) -> str:
    # Split into sentences and keep actionable (simple heuristic: contains a verb)
    sentences = re.split(r"(?<=[.!?])\s+", text.strip())
    bullets = []
    for s in sentences:
        s_clean = s.strip()
        if not s_clean:
            continue
        # Very naive verb check
        if re.search(r"\b(is|are|will|need|please|can|should|review|send|schedule|update|confirm)\b", s_clean, flags=re.IGNORECASE):
            bullets.append("- " + s_clean.rstrip(". "))
    if not bullets:
        bullets = ["- " + text.strip()]
    return "\n".join(bullets)

STYLE_FUNCS: dict[str, Callable[[str], str]] = {
    "formal": formalize,
    "casual": casualize,
    "concise": make_concise,
    "bullet": bulletize,
    "bullet_summary": bulletize,
}

def rewrite_style(text: str, style: str) -> str:
    if not style:
        return text
    style_key = style.lower().strip()
    fn = STYLE_FUNCS.get(style_key)
    if not fn:
        return text
    return fn(text)
