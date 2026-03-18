"""
Pre-Processing Layer
- Urgency detection via keyword rules
- Returns: urgency_level ("urgent", "complex", "simple")
"""

URGENCY_KEYWORDS = [
    "hacked", "compromised", "fraud", "unauthorized", "stolen",
    "outage", "critical emergency", "data leak", "data breach",
    "legal action", "lawsuit", "security breach", "account locked",
    "losing revenue", "production down", "systems down"
]

COMPLEX_KEYWORDS = [
    "integrate", "api", "webhook", "migration", "custom", "enterprise",
    "multiple", "several", "also", "additionally", "furthermore",
    "doesn't work", "not working", "broken", "confused", "unclear"
]

def detect_urgency(text: str) -> str:
    text_lower = text.lower()
    if any(kw in text_lower for kw in URGENCY_KEYWORDS):
        return "urgent"
    if any(kw in text_lower for kw in COMPLEX_KEYWORDS):
        return "complex"
    return "simple"

def preprocess(ticket: dict) -> dict:
    combined_text = f"{ticket['subject']} {ticket['message']}"
    urgency = detect_urgency(combined_text)

    return {
        "ticket_id": ticket["id"],
        "urgency_level": urgency,
        "combined_text": combined_text
    }
