"""
Gmail MCP Agent — Main daemon
Semantically classifies and auto-labels incoming Gmail messages using Claude.
"""

import os
import base64
import json
import time
from datetime import datetime
from typing import Optional

from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
import anthropic
from dotenv import load_dotenv

load_dotenv()

SCOPES = [
    "https://www.googleapis.com/auth/gmail.modify",
    "https://www.googleapis.com/auth/gmail.labels",
]

CATEGORIES = {
    "IMPORTANT_ACTION": "Action Required",
    "PROJECT_WORK": "Projects",
    "NEWSLETTER": "Newsletters",
    "COLD_OUTREACH": "Cold Outreach",
    "SPAM_SOCIAL": "Spam/Social",
    "FINANCE": "Finance & Billing",
    "ARCHIVE": "Auto-Archive",
}

client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))


# ── Auth ───────────────────────────────────────────────────────────────────
def get_gmail_service():
    creds: Optional[Credentials] = None
    token_path = "token.json"
    creds_path = "credentials.json"

    if os.path.exists(token_path):
        creds = Credentials.from_authorized_user_file(token_path, SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(creds_path, SCOPES)
            creds = flow.run_local_server(port=0)
        with open(token_path, "w") as f:
            f.write(creds.to_json())

    return build("gmail", "v1", credentials=creds)


# ── Email Parsing ──────────────────────────────────────────────────────────
def get_email_body(payload: dict) -> str:
    """Extract plain text body from Gmail message payload."""
    body = ""
    if "parts" in payload:
        for part in payload["parts"]:
            if part["mimeType"] == "text/plain":
                data = part["body"].get("data", "")
                body = base64.urlsafe_b64decode(data).decode("utf-8", errors="ignore")
                break
    else:
        data = payload["body"].get("data", "")
        if data:
            body = base64.urlsafe_b64decode(data).decode("utf-8", errors="ignore")
    return body[:2000]  # Truncate for API efficiency


def get_email_headers(headers: list) -> dict:
    result = {}
    for h in headers:
        if h["name"].lower() in ("from", "subject", "date", "to"):
            result[h["name"].lower()] = h["value"]
    return result


# ── Classification ─────────────────────────────────────────────────────────
def classify_email(subject: str, sender: str, body: str) -> dict:
    """Use Claude to semantically classify an email."""
    categories_list = "\n".join(f"- {k}: {v}" for k, v in CATEGORIES.items())

    prompt = f"""Classify this email into exactly ONE category from the list below.
Respond with JSON only: {{"category": "CATEGORY_KEY", "confidence": 0.0-1.0, "reason": "brief reason"}}

Categories:
{categories_list}

Email:
From: {sender}
Subject: {subject}
Body preview: {body[:800]}"""

    message = client.messages.create(
        model="claude-3-haiku-20240307",
        max_tokens=200,
        messages=[{"role": "user", "content": prompt}],
    )

    raw = message.content[0].text.strip()
    # Extract JSON from response
    start = raw.find("{")
    end = raw.rfind("}") + 1
    return json.loads(raw[start:end])


# ── Label Management ───────────────────────────────────────────────────────
def ensure_labels(service) -> dict:
    """Create MCP agent labels if they don't exist. Returns {name: id}."""
    existing = service.users().labels().list(userId="me").execute().get("labels", [])
    existing_map = {l["name"]: l["id"] for l in existing}
    label_ids = {}

    for key, display in CATEGORIES.items():
        label_name = f"MCP/{display}"
        if label_name not in existing_map:
            created = service.users().labels().create(
                userId="me",
                body={"name": label_name, "labelListVisibility": "labelShow",
                      "messageListVisibility": "show"}
            ).execute()
            label_ids[key] = created["id"]
        else:
            label_ids[key] = existing_map[label_name]

    return label_ids


def apply_label(service, msg_id: str, label_id: str, archive: bool = False):
    """Apply a label and optionally archive the message."""
    body = {"addLabelIds": [label_id], "removeLabelIds": []}
    if archive:
        body["removeLabelIds"].append("INBOX")
    service.users().messages().modify(userId="me", id=msg_id, body=body).execute()


# ── Main Loop ──────────────────────────────────────────────────────────────
def process_inbox(service, label_ids: dict, max_emails: int = 20):
    """Fetch unread emails and classify them."""
    results = service.users().messages().list(
        userId="me", q="is:unread in:inbox", maxResults=max_emails
    ).execute()

    messages = results.get("messages", [])
    if not messages:
        print(f"[{datetime.now().isoformat()}] No new emails to process.")
        return

    processed = []
    for msg_ref in messages:
        msg = service.users().messages().get(
            userId="me", id=msg_ref["id"], format="full"
        ).execute()

        headers = get_email_headers(msg["payload"].get("headers", []))
        body = get_email_body(msg["payload"])

        subject = headers.get("subject", "(no subject)")
        sender = headers.get("from", "unknown")

        try:
            result = classify_email(subject, sender, body)
            category = result.get("category", "ARCHIVE")
            confidence = result.get("confidence", 0.0)
            reason = result.get("reason", "")

            label_id = label_ids.get(category, label_ids["ARCHIVE"])
            should_archive = category in ("SPAM_SOCIAL", "NEWSLETTER", "ARCHIVE", "COLD_OUTREACH")
            apply_label(service, msg_ref["id"], label_id, archive=should_archive)

            entry = {
                "id": msg_ref["id"],
                "subject": subject,
                "from": sender,
                "category": category,
                "confidence": confidence,
                "reason": reason,
                "archived": should_archive,
                "timestamp": datetime.now().isoformat(),
            }
            processed.append(entry)
            print(f"  ✓ [{category}] ({confidence:.0%}) — {subject[:60]}")

        except Exception as e:
            print(f"  ✗ Error classifying '{subject}': {e}")

    # Save log
    log_path = "classification_log.json"
    log = []
    if os.path.exists(log_path):
        with open(log_path) as f:
            log = json.load(f)
    log.extend(processed)
    with open(log_path, "w") as f:
        json.dump(log, f, indent=2)

    print(f"[{datetime.now().isoformat()}] Processed {len(processed)} email(s).")


def main():
    print("🤖 Gmail MCP Agent starting...")
    service = get_gmail_service()
    label_ids = ensure_labels(service)
    print(f"✅ Labels ready: {list(CATEGORIES.keys())}")

    poll_interval = int(os.getenv("POLL_INTERVAL_SECONDS", "60"))
    while True:
        process_inbox(service, label_ids)
        print(f"   Sleeping {poll_interval}s...")
        time.sleep(poll_interval)


if __name__ == "__main__":
    main()
