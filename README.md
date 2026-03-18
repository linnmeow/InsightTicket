# InsightTicket

InsightTicket is an AI-powered customer support ticket optimization system that automatically classifies, routes, and drafts responses for incoming support tickets using a multi-layer pipeline: rule-based pre-processing filters for urgency, a GPT-4o-mini analysis agent with ChromaDB RAG retrieves relevant knowledge base context to classify intent and sentiment, a decision engine applies confidence thresholds to route tickets, and automatable tickets receive a second LLM call that generates a draft customer reply for human review before sending. All decisions are logged with PII masking for auditability and feedback loop improvement.

---

## Architecture

```
                        ┌─────────────────────────────────────────────────────┐
                        │                  InsightTicket Pipeline              │
                        └─────────────────────────────────────────────────────┘

  [n8n Webhook]
  POST /ticket-received
         │
         ▼
  ┌─────────────────┐
  │  Ticket Input   │  JSON: id, customer_name, email, subject, message, status
  └────────┬────────┘
           │
           ▼
  ┌──────────────────────────────┐
  │   Pre-Processing Layer       │
  │  preprocessor.py             │
  │  ─────────────────────────   │
  │  • Urgency keyword detection │  ──► urgency_level: "urgent" | "complex" | "simple"
  └────────────┬─────────────────┘
               │
    ┌──────────┴──────────┐
    │                     │
 [urgent?]           [complex/simple]
    │                     │
    ▼                     ▼
 Fast-path         ┌──────────────────────────────┐
 Escalate          │    Analysis Agent             │
 (skip LLM)        │  analysis_agent.py            │
                   │  ─────────────────────────    │
                   │  • ChromaDB RAG retrieval     │  ◄── vector_store/ (ChromaDB)
                   │    (shared with draft step)   │  ◄── OpenAI text-embedding-3-small
                   │  ─────────────────────────    │
                   │  • GPT-4o-mini LLM call 1:    │
                   │    Intent classification      │
                   │    Sentiment detection        │
                   │    Entity extraction          │
                   │    Summarization              │
                   │    Confidence score (0–1.0)   │
                   └──────────────┬───────────────┘
                                  │
                                  ▼
                   ┌──────────────────────────────┐
                   │    Decision Engine            │
                   │  decision_engine.py           │
                   │  ─────────────────────────    │
                   │  • Sentiment override → escal.│
                   │  • Confidence ≥ 0.70 + auto   │
                   │    → automate                 │
                   │  • Otherwise → escalate       │
                   └──────────────┬───────────────┘
                                  │
               ┌──────────────────┴──────────────────┐
               │                                     │
          [automate]                           [escalate]
               │                                     │
               ▼                                     ▼
   ┌──────────────────────────────┐    ┌─────────────────────────┐
   │  Draft Response Generator    │    │  Human Escalation Queue  │
   │  draft_agent.py              │    │  FastAPI response        │
   │  ────────────────────────    │    │  n8n Set node formats    │
   │  • Reuses RAG context from   │    │  escalation summary      │
   │    analysis step (no 2nd     │    └─────────────────────────┘
   │    embedding call)           │
   │  • GPT-4o-mini LLM call 2:  │
   │    Draft customer reply      │
   │  • Pending human review      │
   └──────────────────────────────┘
               │                                     │
               └──────────────┬──────────────────────┘
                              │
                              ▼
               ┌──────────────────────────────┐
               │   Feedback & Logging          │
               │  logger.py                    │
               │  ─────────────────────────    │
               │  • PII masking (email, phone) │
               │  • logs/decisions.csv         │
               │    ticket_id, intent,         │
               │    sentiment, confidence,     │
               │    route, priority, summary   │
               │  • logs/drafts.csv            │
               │    automate tickets only:     │
               │    ticket_id, intent,         │
               │    confidence, draft_response │
               └──────────────────────────────┘
```

---

## Prerequisites

- **Python 3.11+**
- **OpenAI API key** (GPT-4o-mini + text-embedding-3-small access required)
- **Docker** (for running n8n locally)
- **n8n** (self-hosted via Docker, or n8n Cloud account)

---

## Setup Instructions

### 1. Clone the repository

```bash
git clone https://github.com/yourname/InsightTicket.git
cd InsightTicket
```

### 2. Create your `.env` file

```bash
cp .env.example .env
```

Open `.env` and replace `your_openai_api_key_here` with your actual OpenAI API key:

```
OPENAI_API_KEY=sk-...
```

### 3. Install Python dependencies

It is recommended to use a virtual environment:

```bash
python3 -m venv venv
source venv/bin/activate       # macOS/Linux
# venv\Scripts\activate        # Windows

pip install -r requirements.txt
```

### 4. Start the FastAPI server

```bash
uvicorn api:app --reload
```

The API will be available at `http://localhost:8000`. On first startup, the knowledge base is automatically seeded into ChromaDB (requires an active OpenAI API key for embeddings).

You can verify the server is running:

```bash
curl http://localhost:8000/health
# {"status":"ok"}
```

### 5. Start n8n via Docker

```bash
docker run -it --rm \
  --name n8n \
  -p 5678:5678 \
  -v ~/.n8n:/home/node/.n8n \
  n8nio/n8n
```

n8n will be available at `http://localhost:5678`.

### 6. Import the n8n workflow

1. Open n8n at `http://localhost:5678`
2. Go to **Workflows** > **Import from file**
3. Select `n8n/workflow.json`
4. Activate the workflow using the toggle in the top-right corner
5. The webhook will be available at `http://localhost:5678/webhook/ticket-received`

---

## API Endpoints

### `POST /process-ticket`

Runs the full InsightTicket pipeline on a single ticket. This is the endpoint n8n calls.

**Request body:**

```json
{
  "id": "TKT-001",
  "created_at": "2026-03-14T08:00:00Z",
  "customer_name": "Jane Doe",
  "customer_email": "jane.doe@example.com",
  "subject": "I forgot my password",
  "message": "Hi, I can't log in because I forgot my password. How do I reset it?",
  "status": "open"
}
```

**Example curl:**

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
    "entities": {
      "product_mentioned": null,
      "issue_type": "password reset",
      "account_reference": null
    },
    "summary": "Customer forgot their password and cannot log in. They are requesting a password reset.",
    "suggested_action": "Send password reset instructions via email",
    "confidence_score": 0.92,
    "can_be_automated": true,
    "reasoning": "Clear password reset intent with high confidence; standard FAQ answer available",
    "rag_contexts_used": [
      {"category": "account", "question": "How do I reset my password?"}
    ]
  },
  "preprocessed": {
    "ticket_id": "TKT-001",
    "urgency_level": "simple",
    "combined_text": "I forgot my password ..."
  },
  "draft_response": "Hi Jane,\n\nNo worries! To reset your password, click 'Forgot Password' on the login page and follow the instructions sent to your email. The link expires after 24 hours.\n\nLet us know if you need any further help!\n\nBest,\nSupport Team",
  "logged": true
}
```

---

### `GET /logs?limit=20`

Returns the last N decisions logged to CSV.

```bash
curl "http://localhost:8000/logs?limit=10"
```

---

### `GET /health`

Returns server health status.

```bash
curl http://localhost:8000/health
# {"status":"ok"}
```

---

## Testing with Sample Tickets

Run all 15 sample tickets through the pipeline using a single Python one-liner:

```bash
python3 -c "
import httpx, json
tickets = json.load(open('tickets/sample_tickets.json'))
for t in tickets:
    r = httpx.post('http://localhost:8000/process-ticket', json=t, timeout=30)
    d = r.json()
    print(f\"{d['ticket_id']} | {d['route'].upper():8} | {d['priority']:6} | {d.get('analysis', {}).get('intent', 'N/A')}\")
"
```

This will print a summary table like:

```
TKT-001 | ESCALATE | high   | unknown
TKT-002 | ESCALATE | high   | unknown
TKT-008 | AUTOMATE | low    | account_access
TKT-009 | AUTOMATE | low    | refund_request
...
```

---

## Project Structure

```
InsightTicket/
├── api.py                        # FastAPI server — main entry point
├── preprocessor.py               # Rule-based urgency detection
├── analysis_agent.py             # OpenAI GPT analysis + ChromaDB RAG retrieval
├── decision_engine.py            # Confidence threshold routing logic
├── draft_agent.py                # GPT draft reply generation for automatable tickets
├── logger.py                     # CSV logging with PII masking
├── requirements.txt              # Python dependencies
├── .env.example                  # Environment variable template
├── .env                          # Your local env (not committed)
│
├── tickets/
│   └── sample_tickets.json       # 15 sample tickets for testing
│
├── knowledge_base/
│   └── faqs.json                 # 15 FAQ entries seeded into ChromaDB
│
├── vector_store/                 # ChromaDB persistent storage (auto-created)
│
├── logs/
│   ├── decisions.csv             # Append-only decision log (auto-created)
│   └── drafts.csv                # Draft responses for automate tickets (auto-created)
│
└── n8n/
    └── workflow.json             # Importable n8n workflow
```

---

## How the Feedback Loop Works

Every ticket processed by InsightTicket is logged with PII masking across two CSV files.

**`logs/decisions.csv`** — all tickets:

| Field | Description |
|---|---|
| `timestamp` | UTC time of decision |
| `ticket_id` | Ticket identifier |
| `urgency_level` | Pre-processor output: urgent / complex / simple |
| `intent` | GPT-classified intent category |
| `sentiment` | GPT-detected sentiment |
| `confidence_score` | LLM confidence (0.0–1.0) |
| `route` | Final decision: automate or escalate |
| `priority` | low / medium / high |
| `reason` | Human-readable explanation of the routing decision |
| `summary` | 1-2 sentence ticket summary (PII masked) |
| `suggested_action` | Recommended action (PII masked) |

**`logs/drafts.csv`** — automate tickets only:

| Field | Description |
|---|---|
| `timestamp` | UTC time of draft generation |
| `ticket_id` | Ticket identifier |
| `intent` | GPT-classified intent category |
| `confidence_score` | LLM confidence (0.0–1.0) |
| `draft_response` | LLM-generated customer reply (PII masked, pending human review) |

**PII is masked before logging:** email addresses become `[EMAIL]`, phone numbers become `[PHONE]`, and 16-digit card numbers become `[CARD]`.

The log can be analyzed over time to:
- Identify patterns in escalated tickets (tune urgency keywords or lower the confidence threshold)
- Measure automation rate and accuracy
- Flag tickets where the route was incorrect (requires human outcome tagging)
- Retrain or fine-tune the decision thresholds based on real-world performance

To view recent decisions:

```bash
curl "http://localhost:8000/logs?limit=20"
# or directly:
python3 -c "import pandas as pd; print(pd.read_csv('logs/decisions.csv').to_string())"
```
