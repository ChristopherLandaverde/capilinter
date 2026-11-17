"""Estimated match-quality score.

Meta does not publish its Event Match Quality formula. This is a heuristic
estimate that weights the identifiers Meta documents as most useful for
matching. Use it to compare payloads, not to predict the number in Events
Manager.
"""

from dataclasses import dataclass
from typing import Any, Dict, List

from .core import is_fb_cookie, is_sha256

# key, label, weight, recommendation, format check (True = SHA-256, "fb" = fb cookie)
WEIGHTS = [
    ("em", "Hashed email (em)", 3.0, "Add a SHA-256 hashed, normalized email (+3.0).", True),
    ("ph", "Hashed phone (ph)", 2.5, "Add a SHA-256 hashed phone, digits with country code (+2.5).", True),
    ("fbc", "Click ID (fbc)", 1.5, "Pass the _fbc cookie, or build it from fbclid on the landing URL (+1.5).", "fb"),
    ("fbp", "Browser ID (fbp)", 1.0, "Forward the _fbp first-party cookie (+1.0).", "fb"),
    ("external_id", "External ID", 1.0, "Pass a stable CRM or user ID as external_id (+1.0).", False),
    ("client_ip_address", "Client IP address", 0.5, "Forward the visitor IP from the server container (+0.5).", False),
    ("client_user_agent", "Client user agent", 0.5, "Forward the browser user agent from the server container (+0.5).", False),
]

EXCELLENT = 8.5
GOOD = 7.0
FAIR = 5.0


@dataclass
class EMQReport:
    score: float
    grade: str
    matched_parameters: List[str]
    missing_parameters: List[str]
    recommendations: List[str]


def _present(value: Any, check: Any) -> bool:
    if not value:
        return False
    if check == "fb":
        return is_fb_cookie(value)
    if not check:
        return isinstance(value, (str, int, float)) or (isinstance(value, list) and any(value))
    values = value if isinstance(value, list) else [value]
    return any(is_sha256(v) for v in values)


def calculate_emq_score(event: Dict[str, Any]) -> EMQReport:
    user_data = event.get("user_data", {}) if isinstance(event, dict) else {}
    if not isinstance(user_data, dict):
        user_data = {}

    score = 0.0
    matched: List[str] = []
    missing: List[str] = []
    recs: List[str] = []

    for key, label, weight, rec, check in WEIGHTS:
        if _present(user_data.get(key), check):
            score += weight
            matched.append(label)
        else:
            missing.append(label)
            recs.append(rec)

    score = round(min(10.0, score), 1)
    if score >= EXCELLENT:
        grade = "EXCELLENT"
    elif score >= GOOD:
        grade = "GOOD"
    elif score >= FAIR:
        grade = "FAIR"
    else:
        grade = "POOR"

    return EMQReport(score=score, grade=grade, matched_parameters=matched,
                     missing_parameters=missing, recommendations=recs)
