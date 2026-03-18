"""
Draft Agent
- Generates a customer-facing draft reply for automatable tickets
- Reuses RAG context retrieved by the Analysis Agent (no second embedding call)
- Returns: draft response string (pending human review)
"""

import os
from openai import OpenAI, APIError, RateLimitError
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))


@retry(
    retry=retry_if_exception_type((RateLimitError, APIError)),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    stop=stop_after_attempt(3)
)
def generate_draft_response(ticket: dict, analysis: dict) -> str:
    """Generate a draft customer-facing reply for automatable tickets."""

    rag_documents = analysis.get("_rag_documents", [])
    rag_text = "\n\n".join([f"[Context {i+1}]: {doc}" for i, doc in enumerate(rag_documents)])

    prompt = f"""You are a customer support agent drafting a reply to a support ticket.

TICKET:
Subject: {ticket['subject']}
Message: {ticket['message']}

ANALYSIS SUMMARY:
Intent: {analysis['intent']}
Summary: {analysis['summary']}
Suggested Action: {analysis['suggested_action']}

RELEVANT KNOWLEDGE BASE:
{rag_text}

Write a professional, friendly, and concise draft reply to send to the customer.
- Address their specific issue directly
- Use the knowledge base context where relevant
- Do not mention internal systems, routing, or AI
- End with an offer to help further
- Keep it under 150 words

Return only the reply text, no subject line, no labels."""

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.4
    )

    return response.choices[0].message.content.strip()
