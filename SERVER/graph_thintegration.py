import os
import json
import requests
import msal
from dotenv import load_dotenv

load_dotenv()

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

def main():
    # 1) Fill these in once after app registration
    CLIENT_ID = os.getenv("MS_CLIENT_ID")
    TENANT = os.getenv("MS_TENANT_ID", "common")  # 'common' works often; tenant id also ok
    if not CLIENT_ID:
        raise RuntimeError("Missing MS_CLIENT_ID. Set it in server/.env or your terminal env vars.")

    authority = f"https://login.microsoftonline.com/{TENANT}"
    token = get_token(CLIENT_ID, authority)

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

    # 4) Call your local concierge engine
    payload = {
        "sender": sender_str,
        "subject": subject,
        "body": body_html,
        "user_notes": "Draft a concise reply if needed. Do not send.",
        # minimal hints; heuristics will handle promo/transactional/newsletter
    }
    r = requests.post(LOCAL_CONCIERGE, json=payload, timeout=90)
    r.raise_for_status()
    concierge = r.json()

    print("\n=== Concierge Output ===")
    print(json.dumps(concierge, indent=2))

    if not concierge.get("draft"):
        print("\nNo draft recommended/generated. Done.")
        return

    # 5) Create a reply draft in Outlook (Graph)
    # This creates a draft reply message; we'll patch the body with our AI draft.
    reply = graph_post(token, f"{GRAPH_BASE}/me/messages/{msg_id}/createReply")
    draft_id = reply.get("id")
    if not draft_id:
        raise RuntimeError(f"createReply did not return a draft id: {reply}")

    draft_text = concierge["draft"]

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