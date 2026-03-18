"""
Feedback & Logging Layer
- Logs all decisions to CSV
- Applies basic PII masking before logging
"""

import csv
import re
from datetime import datetime
from pathlib import Path

LOG_PATH = Path(__file__).parent / "logs" / "decisions.csv"
DRAFTS_LOG_PATH = Path(__file__).parent / "logs" / "drafts.csv"

FIELDNAMES = [
    "timestamp", "ticket_id", "urgency_level",
    "intent", "sentiment", "confidence_score",
    "route", "priority", "reason",
    "summary", "suggested_action"
]


def mask_pii(text: str) -> str:
    """Mask emails and simple phone patterns."""
    if not text:
        return text
    text = re.sub(r'\b[\w.+-]+@[\w-]+\.\w+\b', '[EMAIL]', text)
    text = re.sub(r'\b\d{3}[-.\s]?\d{3}[-.\s]?\d{4}\b', '[PHONE]', text)
    text = re.sub(r'\b\d{16}\b', '[CARD]', text)
    return text


def log_decision(ticket: dict, preprocessed: dict, analysis: dict, decision: dict):
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)

    write_header = not LOG_PATH.exists()

    row = {
        "timestamp": datetime.utcnow().isoformat(),
        "ticket_id": ticket["id"],
        "urgency_level": preprocessed["urgency_level"],
        "intent": analysis.get("intent", ""),
        "sentiment": analysis.get("sentiment", ""),
        "confidence_score": analysis.get("confidence_score", 0),
        "route": decision["route"],
        "priority": decision["priority"],
        "reason": mask_pii(decision["reason"]),
        "summary": mask_pii(analysis.get("summary", "")),
        "suggested_action": mask_pii(analysis.get("suggested_action", ""))
    }

    with open(LOG_PATH, "a", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        if write_header:
            writer.writeheader()
        writer.writerow(row)

    return row


def log_draft(ticket: dict, analysis: dict, draft: str):
    DRAFTS_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)

    write_header = not DRAFTS_LOG_PATH.exists()

    row = {
        "timestamp": datetime.utcnow().isoformat(),
        "ticket_id": ticket["id"],
        "intent": analysis.get("intent", ""),
        "confidence_score": analysis.get("confidence_score", 0),
        "draft_response": mask_pii(draft)
    }

    with open(DRAFTS_LOG_PATH, "a", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["timestamp", "ticket_id", "intent", "confidence_score", "draft_response"])
        if write_header:
            writer.writeheader()
        writer.writerow(row)

    return row
