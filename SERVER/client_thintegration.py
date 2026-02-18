import json
import sys
import requests
def infer_is_reply_to_user(subject: str, body: str) -> bool:
    s = (subject or "").lower()
    b = (body or "").lower()
    markers = [
        "re:", "fwd:", "fw:",
        "thanks for reaching out",
        "thanks for your email",
        "thank you for your email",
        "in response to",
        "your request",
        "on ", " wrote:"
    ]
    if any(m in s for m in ["re:", "fwd:", "fw:"]):
        return True
    return any(m in b for m in markers)

def infer_human_sender(sender: str, subject: str, body: str) -> bool:
    sender_l = (sender or "").lower()
    subject_l = (subject or "").lower()
    body_l = (body or "").lower()

    # Strong non-human patterns
    nonhuman_sender_markers = ["noreply", "no-reply", "donotreply", "do-not-reply", "mailer-daemon", "notification", "automated"]
    if any(m in sender_l for m in nonhuman_sender_markers):
        return False

    # Marketing/promo language often means "not human"
    promo_keywords = ["sale", "deal", "promo", "limited time", "offer", "discount", "% off", "free shipping", "shop now", "buy now"]
    if any(k in subject_l for k in promo_keywords) or any(k in body_l for k in promo_keywords):
        return False

    # Transactional indicators
    transactional_keywords = ["receipt", "invoice", "order", "confirmation", "transaction"]
    if any(k in subject_l for k in transactional_keywords):
        return False

    # Human-ish cues: greeting + signoff
    signoffs = ["thanks,", "thank you,", "sincerely,", "best,", "regards,", "peace,", "cheers,"]
    if any(s in body_l for s in signoffs):
        return True

    # Default conservative: unknown
    return False

def confirm_bool(label: str, inferred: bool) -> bool:
    resp = input(f"{label} inferred as {inferred}. Press Enter to accept, or type y/n to override: ").strip().lower()
    if resp == "":
        return inferred
    if resp in ("y", "yes"):
        return True
    if resp in ("n", "no"):
        return False
    return inferred

API_BASE = "http://127.0.0.1:8000"

def prompt_multiline(label: str) -> str:
    print(f"\n{label} (paste, then type END on a new line):")
    lines = []
    while True:
        line = sys.stdin.readline()
        if not line:
            break
        if line.strip() == "END":
            break
        lines.append(line.rstrip("\n"))
    return "\n".join(lines).strip()

def main():
    print("=== AI Email Concierge — Thintegration Client ===")
    sender = input("Sender: ").strip()
    subject = input("Subject: ").strip()

    body = prompt_multiline("Body")
    user_notes = input("\nUser notes (optional): ").strip() or None

    inferred_reply = infer_is_reply_to_user(subject, body)
    inferred_human = infer_human_sender(sender, subject, body)

    is_reply_to_user = confirm_bool("Is reply to a thread you initiated?", inferred_reply)
    human_sender = confirm_bool("Is human sender?", inferred_human)

    # Known contact is different from human; keep it optional for now
    inferred_known = False
    known_contact = confirm_bool("Is known contact (in your address book / relationship)?", inferred_known)

    payload = {
        "sender": sender,
        "subject": subject,
        "body": body,
        "user_notes": user_notes,
        "is_reply_to_user": is_reply_to_user,
        "known_contact": known_contact,
        "human_sender": human_sender

    }

    print("\n--- Calling concierge-email ---")
    r = requests.post(f"{API_BASE}/concierge-email", json=payload, timeout=60)
    r.raise_for_status()
    data = r.json()

    print("\n=== RESULT ===")
    print(json.dumps(data, indent=2))

    print("\n=== QUICK VIEW ===")
    print(f"Priority: {data.get('priority_level')}")
    print(f"Folder:   {data.get('folder')}")
    print(f"Notify:   {data.get('notify')}")
    print(f"Reason:   {data.get('reason')}")
    print(f"Action:   {data.get('recommended_action')}")
    print(f"Reply?:   {data.get('reply_recommended')}")

    draft = data.get("draft")
    if draft:
        print("\n=== DRAFT (copy/paste into Outlook) ===\n")
        print(draft)
    else:
        print("\n(No draft generated.)")

if __name__ == "__main__":
    main()
