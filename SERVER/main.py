import os
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from openai import OpenAI

from schemas import (
    DraftReplyRequest,
    DraftReplyResponse,
    ClassifyEmailRequest,
    ClassifyEmailResponse,
)


load_dotenv()

app = FastAPI(title="AI Email Concierge Server", version="0.1.0")

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
MODEL = os.getenv("OPENAI_MODEL", "gpt-5.2")

SYSTEM_INSTRUCTIONS = """You are my AI email concierge.

Draft reply requirements:
- Tone: warm, calm, professional
- Concise: 2–5 sentences unless necessary
- Avoid over-explaining
- If scheduling is implied, propose 1–2 concrete options
- Do not invent facts
- Do not send the email; output draft text only
- Prefix with: "Draft reply (AI):"
"""

@app.get("/health")
def health():
    return {"ok": True}

@app.post("/draft-reply", response_model=DraftReplyResponse)
def draft_reply(req: DraftReplyRequest):
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise HTTPException(status_code=500, detail="OPENAI_API_KEY missing. Create server/.env from .env.example")

    user_input = f"""Email to respond to:
Sender: {req.sender}
Subject: {req.subject}
Body:
{req.body}

User notes (optional):
{req.user_notes or ""}
"""

    try:
        response = client.responses.create(
            model=MODEL,
            instructions=SYSTEM_INSTRUCTIONS,
            input=user_input,
            text={"verbosity": "low"},
        )
        draft = response.output_text.strip()
        return DraftReplyResponse(draft=draft)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"OpenAI error: {e}")
@app.post("/classify-email", response_model=ClassifyEmailResponse)
def classify_email(req: ClassifyEmailRequest):
    """
    Deterministic classifier (v0.4):
    Uses your Decision Priority Ladder rules.
    """
    # 1) INTERRUPT NOW
    if req.is_reply_to_user:
        return ClassifyEmailResponse(
            priority_level="INTERRUPT NOW",
            folder="1 - Action Now",
            notify=True,
            reason="Reply to a conversation you initiated."
        )

    # 2) NOTIFY (NON-URGENT)
    if req.known_contact:
        return ClassifyEmailResponse(
            priority_level="NOTIFY (NON-URGENT)",
            folder="2 - Notify Later",
            notify=True,
            reason="Human message from a known contact."
        )

    # 3) LOG SILENTLY
    if req.is_transactional:
        return ClassifyEmailResponse(
            priority_level="LOG SILENTLY",
            folder="3 - Log Only",
            notify=False,
            reason="Transactional/receipt email: keep for records, no interruption."
        )

    # 4) BATCH FOR LATER
    if req.is_newsletter:
        return ClassifyEmailResponse(
            priority_level="BATCH FOR LATER",
            folder="4 - Batch Read",
            notify=False,
            reason="Newsletter/brief: review during batch window."
        )

    # 5) IGNORE / AUTO-ARCHIVE (default)
    return ClassifyEmailResponse(
        priority_level="IGNORE / AUTO-ARCHIVE",
        folder="5 - Ignore (Promo)",
        notify=False,
        reason="Default classification: promotional/low-value or unknown importance."
    )
