"""
FastAPI Server — main entry point for n8n to call.
Exposes two endpoints:
  POST /process-ticket  — full pipeline for a single ticket
  GET  /logs            — returns last N log entries
"""

import os
import traceback
from dotenv import load_dotenv
load_dotenv()

from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, field_validator
import pandas as pd
from pathlib import Path

from preprocessor import preprocess
from analysis_agent import analyze_ticket, seed_knowledge_base
from draft_agent import generate_draft_response
from decision_engine import decide
from logger import log_decision, log_draft

@asynccontextmanager
async def lifespan(app: FastAPI):
    seed_knowledge_base()
    yield


app = FastAPI(title="InsightTicket API", version="1.0.0", lifespan=lifespan)


class Ticket(BaseModel):
    id: str
    created_at: str
    customer_name: str
    customer_email: str
    subject: str
    message: str
    status: str = "open"

    @field_validator("subject", "message")
    @classmethod
    def must_not_be_blank(cls, v, info):
        if not v or not v.strip():
            raise ValueError(f"{info.field_name} cannot be blank")
        return v.strip()


@app.post("/process-ticket")
async def process_ticket(ticket: Ticket):
    try:
        ticket_dict = ticket.model_dump()

        # Step 1: Pre-process
        preprocessed = preprocess(ticket_dict)

        # Step 2: If urgent, skip LLM analysis — fast-path escalate
        if preprocessed["urgency_level"] == "urgent":
            decision = {
                "route": "escalate",
                "reason": "Urgency keywords detected in pre-processing",
                "priority": "high"
            }
            analysis = {
                "intent": "unknown",
                "sentiment": "urgent",
                "summary": f"URGENT: {ticket.subject}",
                "suggested_action": "Immediate human review required",
                "confidence_score": 0.0,
                "can_be_automated": False,
                "reasoning": "Bypassed LLM — urgent flag set by pre-processor",
                "entities": {
                    "product_mentioned": None,
                    "issue_type": None,
                    "account_reference": None
                },
                "rag_contexts_used": []
            }
        else:
            # Step 3: Analysis Agent
            analysis = analyze_ticket(ticket_dict, preprocessed)

            # Step 4: Decision Agent
            decision = decide(analysis)

        # Step 5: Draft response for automatable tickets
        draft_response = None
        if decision["route"] == "automate":
            draft_response = generate_draft_response(ticket_dict, analysis)
            log_draft(ticket_dict, analysis, draft_response)
        analysis.pop("_rag_documents", None)

        # Step 6: Log
        log_decision(ticket_dict, preprocessed, analysis, decision)

        return {
            "ticket_id": ticket.id,
            "route": decision["route"],
            "priority": decision["priority"],
            "reason": decision["reason"],
            "analysis": analysis,
            "preprocessed": preprocessed,
            "draft_response": draft_response,
            "logged": True
        }

    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/logs")
async def get_logs(limit: int = 20):
    log_path = Path(__file__).parent / "logs" / "decisions.csv"
    if not log_path.exists():
        return {"logs": []}
    df = pd.read_csv(log_path)
    return {"logs": df.tail(limit).to_dict(orient="records")}


@app.get("/health")
async def health():
    return {"status": "ok"}
