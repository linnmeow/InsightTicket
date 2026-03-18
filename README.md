# InsightTicket

InsightTicket is an AI-powered customer support ticket routing and response system. It uses a multi-layer pipeline to classify incoming tickets, route them to automation or human escalation, and generate draft replies for automatable cases — all with PII-safe logging for auditability.

**Stack:** Python · FastAPI · GPT-4o-mini · ChromaDB · n8n

---

## Architecture

```
  [n8n Webhook] POST /ticket-received
                     │
                     ▼
  ┌─────────────────────────────────────────┐
  │             Ticket Input                │
  │  id, customer_name, email,              │
  │  subject, message, status               │
  └──────────────────┬──────────────────────┘
                     │
                     ▼
  ┌─────────────────────────────────────────┐
  │         Pre-Processing Layer            │
  │           preprocessor.py              │
  │  ─────────────────────────────────────  │
  │  • Urgency keyword detection            │
  │    → "urgent" | "complex" | "simple"   │
  └──────────────────┬──────────────────────┘
                     │
          ┌──────────┴──────────┐
          │                     │
       [urgent]           [complex / simple]
          │                     │
          ▼                     ▼
   Fast-path            ┌───────────────────────────────────┐
   Escalate             │         Analysis Agent            │
   (skip LLM)           │        analysis_agent.py          │
                        │  ─────────────────────────────    │
                        │  • ChromaDB RAG retrieval         │ ◄── vector_store/
                        │    (shared with draft step)       │ ◄── text-embedding-3-small
                        │  • GPT-4o-mini LLM call 1         │
                        │    - Intent classification        │
                        │    - Sentiment detection          │
                        │    - Entity extraction            │
                        │    - Summarization                │
                        │    - Confidence score (0–1.0)     │
                        └──────────────┬────────────────────┘
                                       │
                                       ▼
                        ┌───────────────────────────────────┐
                        │         Decision Engine           │
                        │        decision_engine.py         │
                        │  ─────────────────────────────    │
                        │  • Sentiment override → escalate  │
                        │  • Confidence ≥ 0.70 + automatable│
                        │    → automate                     │
                        │  • Otherwise → escalate           │
                        └──────────────┬────────────────────┘
                                       │
                    ┌──────────────────┴──────────────────┐
                    │                                     │
               [automate]                           [escalate]
                    │                                     │
                    ▼                                     ▼
  ┌─────────────────────────────┐       ┌─────────────────────────────┐
  │    Draft Response Generator │       │    Human Escalation Queue   │
  │       draft_agent.py        │       │      FastAPI response        │
  │  ─────────────────────────  │       │  full analysis context      │
  │  • Reuses RAG context       │       │  for human agent review     │
  │    (no 2nd embedding call)  │       └──────────────┬──────────────┘
  │  • GPT-4o-mini LLM call 2   │                      │
  │    Draft customer reply     │                      │
  │  • Pending human review     │                      │
  └──────────────┬──────────────┘                      │
                 └─────────────────────┬───────────────┘
                                       │
                                       ▼
                        ┌───────────────────────────────────┐
                        │        Feedback & Logging         │
                        │           logger.py               │
                        │  ─────────────────────────────    │
                        │  • PII masking (email, phone)     │
                        │  • logs/decisions.csv — all       │
                        │    tickets: intent, sentiment,    │
                        │    confidence, route, summary     │
                        │  • logs/drafts.csv — automate     │
                        │    tickets only: draft_response   │
                        └───────────────────────────────────┘
```

---

## Prerequisites

- Python 3.11+
- OpenAI API key (GPT-4o-mini + text-embedding-3-small)
- Docker (optional, for n8n)

---

## Setup

```bash
git clone https://github.com/yourname/InsightTicket.git
cd InsightTicket
cp .env.example .env          # add your OpenAI API key
pip install -r requirements.txt
uvicorn api:app --reload      # starts on http://localhost:8000
```

On first startup, the knowledge base is automatically seeded into ChromaDB.

**Optional — n8n integration:**

```bash
docker run -it --rm --name n8n -p 5678:5678 -v ~/.n8n:/home/node/.n8n n8nio/n8n
```

Open `http://localhost:5678`, import `n8n/workflow.json`, and publish the workflow. Tickets can then be sent to `http://localhost:5678/webhook/ticket-received`.

---

## API Endpoints

### `POST /process-ticket`

```bash
curl -X POST http://localhost:8000/process-ticket \
  -H "Content-Type: application/json" \
  -d '{
    "id": "TKT-001",
    "created_at": "2026-03-14T08:00:00Z",
    "customer_name": "Jane Doe",
    "customer_email": "jane.doe@example.com",
    "subject": "I forgot my password",
    "message": "Hi, I cant log in because I forgot my password. How do I reset it?",
    "status": "open"
  }'
```

**Example response:**

```json
{
  "ticket_id": "TKT-001",
  "route": "automate",
  "priority": "low",
  "reason": "High confidence (92%) and automatable intent",
  "analysis": {
    "intent": "account_access",
    "sentiment": "neutral",
    "summary": "Customer forgot their password and cannot log in.",
    "suggested_action": "Send password reset instructions via email",
    "confidence_score": 0.92,
    "can_be_automated": true
  },
  "draft_response": "Hi Jane, no worries! To reset your password, click 'Forgot Password' on the login page...",
  "logged": true
}
```

### `GET /logs?limit=20`

```bash
curl "http://localhost:8000/logs?limit=10"
```

### `GET /health`

```bash
curl http://localhost:8000/health
```

---

## Project Structure

```
InsightTicket/
├── api.py                  # FastAPI server — main entry point
├── preprocessor.py         # Rule-based urgency detection
├── analysis_agent.py       # GPT-4o-mini analysis + ChromaDB RAG
├── decision_engine.py      # Confidence threshold routing
├── draft_agent.py          # Draft reply generation for automatable tickets
├── logger.py               # CSV logging with PII masking
├── knowledge_base/
│   └── faqs.json           # FAQ entries seeded into ChromaDB
├── tickets/
│   └── sample_tickets.json # 15 sample tickets for testing
├── logs/
│   ├── decisions.csv       # All ticket decisions (auto-created)
│   └── drafts.csv          # Draft responses for automate tickets (auto-created)
└── n8n/
    └── workflow.json       # Importable n8n workflow
```

---

## Logging

All decisions are logged with PII masking (emails, phones, card numbers).

**`logs/decisions.csv`** — every ticket: `ticket_id`, `urgency_level`, `intent`, `sentiment`, `confidence_score`, `route`, `priority`, `reason`, `summary`, `suggested_action`

**`logs/drafts.csv`** — automate tickets only: `ticket_id`, `intent`, `confidence_score`, `draft_response`
