import os
import json
import requests
import msal
import base64
from dotenv import load_dotenv

load_dotenv()

from bs4 import BeautifulSoup
import re

GRAPH_BASE = "https://graph.microsoft.com/v1.0"
LOCAL_CONCIERGE = "http://127.0.0.1:8000/concierge-email"
SCOPES = ["User.Read", "Mail.Read", "Mail.ReadWrite"]  # add Mail.Send later if you want

TOKEN_CACHE_PATH = os.path.join(os.path.dirname(__file__), ".token_cache.bin")

def load_cache():
    cache = msal.SerializableTokenCache()
    if os.path.exists(TOKEN_CACHE_PATH):
        cache.deserialize(open(TOKEN_CACHE_PATH, "r").read())
    return cache

def save_cache(cache: msal.SerializableTokenCache):
    if cache.has_state_changed:
        with open(TOKEN_CACHE_PATH, "w") as f:
            f.write(cache.serialize())

def get_token(client_id: str, authority: str) -> str:
    cache = load_cache()
    app = msal.PublicClientApplication(client_id=client_id, authority=authority, token_cache=cache)

    accounts = app.get_accounts()
    if accounts:
        result = app.acquire_token_silent(SCOPES, account=accounts[0])
        if result and "access_token" in result:
            save_cache(cache)
            return result["access_token"]

    flow = app.initiate_device_flow(scopes=SCOPES)
    if "user_code" not in flow:
        raise RuntimeError(f"Failed to create device flow: {flow}")

    print(flow["message"])  # shows URL + code to enter
    result = app.acquire_token_by_device_flow(flow)

    if "access_token" not in result:
        raise RuntimeError(f"Auth failed: {result}")

    save_cache(cache)
    return result["access_token"]

def graph_get(token: str, url: str):
    headers = {"Authorization": f"Bearer {token}"}
    r = requests.get(url, headers=headers, timeout=60)

    if not r.ok:
        print("\n--- GRAPH REQUEST FAILED ---")
        print("URL:", url)
        print("Status:", r.status_code)
        print("WWW-Authenticate:", r.headers.get("WWW-Authenticate"))
        print("Body:", r.text)
        print("--- END ---\n")
        r.raise_for_status()

    return r.json()

def graph_post(token: str, url: str, payload=None):
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    r = requests.post(url, headers=headers, json=payload, timeout=60)
    r.raise_for_status()
    return r.json() if r.text else {}

def graph_patch(token: str, url: str, payload):
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    r = requests.patch(url, headers=headers, json=payload, timeout=60)
    r.raise_for_status()
    return r.json() if r.text else {}

def debug_token_claims(access_token: str):
    # Decode JWT without verification (safe for debugging claims locally)
    parts = access_token.split(".")
    if len(parts) < 2:
        print("Token doesn't look like a JWT.")
        return

    payload_b64 = parts[1] + "==="  # pad
    payload_json = base64.urlsafe_b64decode(payload_b64.encode("utf-8")).decode("utf-8")
    claims = json.loads(payload_json)

    print("\n--- TOKEN CLAIMS (debug) ---")
    print("aud:", claims.get("aud"))
    print("scp:", claims.get("scp"))  # delegated scopes
    print("tid:", claims.get("tid"))
    print("preferred_username:", claims.get("preferred_username"))
    print("--- END ---\n")
def html_to_text(html: str) -> str:
    if not html:
        return ""

    soup = BeautifulSoup(html, "lxml")

    # Remove junk
    for tag in soup(["script", "style", "img", "svg", "meta", "link"]):
        tag.decompose()

    text = soup.get_text("\n")

    # Normalize whitespace
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"[ \t]{2,}", " ", text)
    return text.strip()
def infer_human_sender(sender: str, subject: str, body: str) -> bool:
    sender_l = (sender or "").lower()
    subject_l = (subject or "").lower()
    body_l = (body or "").lower()

    # Strong non-human patterns
    nonhuman_sender_markers = ["noreply", "no-reply", "donotreply", "do-not-reply", "mailer-daemon", "notification", "automated"]
    if any(m in sender_l for m in nonhuman_sender_markers):
        return False

    # List/newsletter markers (these are big tells)
    list_markers = ["unsubscribe", "view in browser", "manage preferences", "email preferences"]
    if any(m in body_l for m in list_markers):
        return False

    # Transactional indicators
    transactional_keywords = ["receipt", "invoice", "order", "confirmation", "transaction"]
    if any(k in subject_l for k in transactional_keywords):
        return False

    # Human-ish cues: conversational tone / signoff
    signoffs = ["thanks,", "thank you,", "sincerely,", "best,", "regards,", "talk to you", "see you", "peace,"]
    if any(s in body_l for s in signoffs):
        return True

    # Personal email provider domains are often human (not perfect, but good)
    personal_domains = ["gmail.com", "outlook.com", "hotmail.com", "icloud.com", "yahoo.com", "proton.me", "protonmail.com"]
    if any(d in sender_l for d in personal_domains):
        return True

    # Default conservative: unknown
    return False
    
def main():
    # 1) Fill these in once after app registration
    CLIENT_ID = os.getenv("MS_CLIENT_ID")
    TENANT = os.getenv("MS_TENANT_ID", "common")  # 'common' works often; tenant id also ok
    if not CLIENT_ID:
        raise RuntimeError("Missing MS_CLIENT_ID. Set it in server/.env or your terminal env vars.")

    authority = f"https://login.microsoftonline.com/{TENANT}"
    token = get_token(CLIENT_ID, authority)
    debug_token_claims(token)

    # 🔎 Test simple Graph endpoint first
    profile = graph_get(token, f"{GRAPH_BASE}/me?$select=displayName,userPrincipalName,id")
    print("ME:", profile)
    
    # 2) List latest inbox messages
    inbox = graph_get(
        token,
        f"{GRAPH_BASE}/me/mailFolders/inbox/messages?$top=10&$select=id,subject,from,receivedDateTime,bodyPreview"
    )
    msgs = inbox.get("value", [])
    if not msgs:
        print("No messages found.")
        return

    print("\n=== Latest Inbox Messages ===")
    for i, m in enumerate(msgs, start=1):
        sender = (m.get("from", {}) or {}).get("emailAddress", {}) or {}
        print(f"{i:2d}. {m.get('subject','(no subject)')}")
        print(f"    From: {sender.get('name','')} <{sender.get('address','')}>")
        print(f"    ID: {m.get('id')}")
        print()

    choice = int(input("Pick a message number to concierge: ").strip())
    picked = msgs[choice - 1]
    msg_id = picked["id"]

    # 3) Fetch full body
    full = graph_get(
        token,
        f"{GRAPH_BASE}/me/messages/{msg_id}?$select=subject,from,body"
    )
    sender = (full.get("from", {}) or {}).get("emailAddress", {}) or {}
    sender_str = f"{sender.get('name','')} <{sender.get('address','')}>".strip()
    subject = full.get("subject", "")
    body_html = (full.get("body", {}) or {}).get("content", "")
    body_text = html_to_text(body_html)
    human_sender = infer_human_sender(sender_str, subject, body_text)
    print("Inferred human_sender =", human_sender)
    
    # 4) Call your local concierge engine
    payload = {
        "sender": sender_str,
        "subject": subject,
        "body": body_text,
        "user_notes": "Draft a concise reply if needed. Do not send.",
        "human_sender": human_sender
        
        # minimal hints; heuristics will handle promo/transactional/newsletter
    }
    r = requests.post(LOCAL_CONCIERGE, json=payload, timeout=90)
    r.raise_for_status()
    concierge = r.json()

    print("\n=== QUICK VIEW ===")
    print("Priority:", concierge.get("priority_level"))
    print("Folder:", concierge.get("folder"))
    print("Notify:", concierge.get("notify"))
    print("Reply recommended:", concierge.get("reply_recommended"))
    print("Reason:", concierge.get("reason"))
    print("\n=== Concierge Output ===")
    print(json.dumps(concierge, indent=2))

    draft_text = concierge.get("draft")

    if not draft_text:
        force = input("\nNo AI draft generated. Force a TEST draft to validate Outlook draft creation? (y/N): ").strip().lower() == "y"
        if not force:
            print("Done.")
            return

        draft_text = (
            "Draft reply (TEST):\n\n"
            "Thanks for the email — received. (This is a test draft to validate Outlook draft creation.)\n\n"
            "Best,\nFrank"
        )

    print("\n=== DRAFT THAT WILL BE WRITTEN TO OUTLOOK ===\n")
    print(draft_text)

    # Create a simple test draft body (so we can test Outlook Draft creation)
    concierge["draft"] = (
        "Draft reply (TEST):\n\n"
        "Thanks for the email — received. (This is a test draft to validate Outlook draft creation.)\n\n"
        "Best,\nFrank"
    )

    # 5) Create a reply draft in Outlook (Graph)
    # This creates a draft reply message; we'll patch the body with our AI draft.
    reply = graph_post(token, f"{GRAPH_BASE}/me/messages/{msg_id}/createReply")
    draft_id = reply.get("id")
    if not draft_id:
        raise RuntimeError(f"createReply did not return a draft id: {reply}")

    # Patch the draft body (HTML) with our drafted text (simple pre-wrap)
    html_body = "<pre style='font-family:Segoe UI, Arial; white-space:pre-wrap;'>" + \
                draft_text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;") + \
                "</pre>"

    graph_patch(token, f"{GRAPH_BASE}/me/messages/{draft_id}", {
        "body": {"contentType": "HTML", "content": html_body}
    })

    print(f"\n✅ Draft reply created in Outlook. Draft message id: {draft_id}")
    print("Open Outlook → Drafts folder to review and send manually.")

if __name__ == "__main__":
    main()