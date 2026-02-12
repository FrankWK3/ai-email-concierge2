from pydantic import BaseModel, Field

class DraftReplyRequest(BaseModel):
    sender: str = Field(..., description="From address or display name")
    subject: str = Field(..., description="Email subject")
    body: str = Field(..., description="Email body text")
    user_notes: str | None = Field(None, description="Optional extra context or intent")

class DraftReplyResponse(BaseModel):
    draft: str
class ClassifyEmailRequest(BaseModel):
    sender: str
    subject: str
    body: str
    is_reply_to_user: bool = False
    known_contact: bool = False
    is_transactional: bool = False
    is_newsletter: bool = False

class ClassifyEmailResponse(BaseModel):
    priority_level: str
    folder: str
    notify: bool
    reason: str
