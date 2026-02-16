import os
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from openai import OpenAI

from schemas import (
    DraftReplyRequest,
    DraftReplyResponse,
    ClassifyEmailRequest,
    ClassifyEmailResponse,
    ConciergeEmailRequest,
    ConciergeEmailResponse,
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
def _classify(req: ClassifyEmailRequest) -> ClassifyEmailResponse:
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

    # 5) IGNORE / AUTO-ARCHIVE
    return ClassifyEmailResponse(
        priority_level="IGNORE / AUTO-ARCHIVE",
        folder="5 - Ignore (Promo)",
        notify=False,
        reason="Default classification: promotional/low-value or unknown importance."
    )


def _should_reply(classification: ClassifyEmailResponse, req: ConciergeEmailRequest) -> bool:
    # Reply recommended only for human-centric categories.
    if classification.priority_level in ("INTERRUPT NOW", "NOTIFY (NON-URGENT)"):
        # If it's a reply or known contact, we generally want to respond.
        return bool(req.is_reply_to_user or req.known_contact)
    return False


def _recommended_action(classification: ClassifyEmailResponse, reply_recommended: bool) -> str:
    if classification.priority_level == "INTERRUPT NOW":
        return "Review now and reply promptly. Confirm details or next steps."
    if classification.priority_level == "NOTIFY (NON-URGENT)":
        return "Review during reply window and respond with a brief, warm acknowledgment."
    if classification.priority_level == "LOG SILENTLY":
        return "No reply needed. Archive/label for records."
    if classification.priority_level == "BATCH FOR LATER":
        return "No reply needed. Read during batch window or summarize."
    if classification.priority_level == "IGNORE / AUTO-ARCHIVE":
        return "No action needed. Ignore or archive."
    return "Review and decide."


@app.post("/concierge-email", response_model=ConciergeEmailResponse)
def concierge_email(req: ConciergeEmailRequest):
    # 1) Classify using deterministic ladder
    classification = _classify(ClassifyEmailRequest(
        sender=req.sender,
        subject=req.subject,
        body=req.body,
        is_reply_to_user=req.is_reply_to_user,
        known_contact=req.known_contact,
        is_transactional=req.is_transactional,
        is_newsletter=req.is_newsletter,
    ))

    # 2) Decide whether a reply is recommended
    reply_recommended = _should_reply(classification, req)
    action = _recommended_action(classification, reply_recommended)

    # 3) Optionally draft a reply (never send)
    draft_text = None
    if reply_recommended:
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
            draft_text = response.output_text.strip()
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"OpenAI error (drafting): {e}")

    return ConciergeEmailResponse(
        priority_level=classification.priority_level,
        folder=classification.folder,
        notify=classification.notify,
        reason=classification.reason,
        recommended_action=action,
        reply_recommended=reply_recommended,
        draft=draft_text,
    )
