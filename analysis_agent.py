"""
Analysis Agent
- Uses OpenAI GPT to classify intent, detect sentiment, extract entities, summarize
- Uses ChromaDB + OpenAI embeddings for RAG (retrieves relevant FAQ context)
- Returns structured analysis with confidence score
"""

import json
import os
from pathlib import Path
from openai import OpenAI, APIError, RateLimitError
import chromadb
from chromadb.utils import embedding_functions
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

CHROMA_PATH = Path(__file__).parent / "vector_store"
COLLECTION_NAME = "faq_knowledge_base"

_openai_ef = embedding_functions.OpenAIEmbeddingFunction(
    api_key=os.getenv("OPENAI_API_KEY"),
    model_name="text-embedding-3-small"
)
_chroma_client = chromadb.PersistentClient(path=str(CHROMA_PATH))
_collection = _chroma_client.get_or_create_collection(
    name=COLLECTION_NAME,
    embedding_function=_openai_ef
)


def seed_knowledge_base():
    """Load FAQs into ChromaDB if not already seeded."""
    if _collection.count() > 0:
        return

    faq_path = Path(__file__).parent / "knowledge_base" / "faqs.json"
    with open(faq_path) as f:
        faqs = json.load(f)

    documents = [f"Q: {faq['question']}\nA: {faq['answer']}" for faq in faqs]
    ids = [faq["id"] for faq in faqs]
    metadatas = [{"category": faq["category"], "question": faq["question"]} for faq in faqs]

    _collection.add(documents=documents, ids=ids, metadatas=metadatas)
    print(f"Seeded {len(faqs)} FAQs into ChromaDB")


def retrieve_context(query: str, n_results: int = 3) -> list[dict]:
    results = _collection.query(query_texts=[query], n_results=n_results)

    contexts = []
    for i, doc in enumerate(results["documents"][0]):
        contexts.append({
            "document": doc,
            "distance": results["distances"][0][i],
            "metadata": results["metadatas"][0][i]
        })
    return contexts


@retry(
    retry=retry_if_exception_type((RateLimitError, APIError)),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    stop=stop_after_attempt(3)
)
def analyze_ticket(ticket: dict, preprocessed: dict) -> dict:
    """Run full LLM analysis with RAG context."""

    # Retrieve relevant FAQ context
    rag_contexts = retrieve_context(preprocessed["combined_text"])
    rag_text = "\n\n".join([f"[Context {i+1}]: {c['document']}" for i, c in enumerate(rag_contexts)])

    complexity = preprocessed["urgency_level"]  # "complex" or "simple" at this point

    prompt = f"""You are a customer support analysis agent. Analyze the following support ticket and return a JSON response.

TICKET:
Subject: {ticket['subject']}
Message: {ticket['message']}
Pre-classification (rule-based hint, use your own judgment): {complexity} — {"keyword matching suggests this ticket may involve multiple issues or technical depth" if complexity == "complex" else "keyword matching suggests this ticket appears straightforward"}

RELEVANT KNOWLEDGE BASE CONTEXT:
{rag_text}

Return a JSON object with these exact fields:
{{
  "intent": "one of: billing_issue, account_access, technical_support, general_inquiry, cancellation, feature_request, complaint, refund_request",
  "sentiment": "one of: positive, neutral, negative, frustrated, urgent",
  "entities": {{
    "product_mentioned": "string or null",
    "issue_type": "string or null",
    "account_reference": "string or null"
  }},
  "summary": "1-2 sentence summary of the ticket",
  "suggested_action": "brief recommended action",
  "confidence_score": 0.0 to 1.0,
  "can_be_automated": true or false,
  "reasoning": "brief explanation of confidence score and automation decision"
}}

Scoring rules:
- confidence_score: how clearly you understand the customer's request (0.0 = very ambiguous, 1.0 = crystal clear)
- can_be_automated: true ONLY if the resolution is a standard reply using known information (FAQ answer, policy explanation, how-to instructions). Set false if the ticket requires a human to take action (fix a bug, process a refund, investigate an account, review a feature request).

Only return valid JSON, no markdown, no extra text."""

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.2
    )

    analysis = json.loads(response.choices[0].message.content)
    analysis["rag_contexts_used"] = [c["metadata"] for c in rag_contexts]
    analysis["_rag_documents"] = [c["document"] for c in rag_contexts]

    return analysis


