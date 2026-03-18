"""
Decision Agent
- Takes analysis results
- Applies threshold-based routing logic
- Returns: route ("automate" or "escalate"), reason
"""

CONFIDENCE_THRESHOLD = 0.70


def decide(analysis: dict) -> dict:
    confidence = analysis.get("confidence_score", 0)
    can_automate = analysis.get("can_be_automated", False)
    sentiment = analysis.get("sentiment", "neutral")

    # Hard escalation rules
    if sentiment in ["frustrated", "urgent"]:
        return {
            "route": "escalate",
            "reason": f"Sentiment override: customer is '{sentiment}'",
            "priority": "medium"
        }

    # Confidence + automation check
    if confidence >= CONFIDENCE_THRESHOLD and can_automate:
        return {
            "route": "automate",
            "reason": f"High confidence ({confidence:.0%}) and automatable intent",
            "priority": "low"
        }

    if confidence >= CONFIDENCE_THRESHOLD and not can_automate:
        return {
            "route": "escalate",
            "reason": f"High confidence ({confidence:.0%}) but requires human action — not automatable",
            "priority": "medium"
        }

    return {
        "route": "escalate",
        "reason": f"Low confidence ({confidence:.0%}) — needs human review",
        "priority": "medium"
    }
