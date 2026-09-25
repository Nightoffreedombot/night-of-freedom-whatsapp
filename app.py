import os
import requests
from flask import Flask, request

app = Flask(__name__)

# Meta/WhatsApp configuration is supplied through Railway environment variables.
VERIFY_TOKEN = os.environ.get("VERIFY_TOKEN", "")
WHATSAPP_ACCESS_TOKEN = os.environ.get("WHATSAPP_ACCESS_TOKEN", "")
PHONE_NUMBER_ID = os.environ.get("PHONE_NUMBER_ID", "")
GRAPH_API_VERSION = os.environ.get("GRAPH_API_VERSION", "v26.0")
AUTO_REPLY_TEXT = os.environ.get(
    "AUTO_REPLY_TEXT",
    "Thanks for your message! We received it and will get back to you shortly.",
)


def send_whatsapp_text(recipient_wa_id: str, message_text: str):
    """Send a text message through Meta's WhatsApp Cloud API."""
    if not WHATSAPP_ACCESS_TOKEN or not PHONE_NUMBER_ID:
        raise RuntimeError(
            "WHATSAPP_ACCESS_TOKEN and PHONE_NUMBER_ID must be configured."
        )

    url = (
        f"https://graph.facebook.com/{GRAPH_API_VERSION}/"
        f"{PHONE_NUMBER_ID}/messages"
    )

    headers = {
        "Authorization": f"Bearer {WHATSAPP_ACCESS_TOKEN}",
        "Content-Type": "application/json",
    }

    payload = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": recipient_wa_id,
        "type": "text",
        "text": {
            "preview_url": False,
            "body": message_text,
        },
    }

    response = requests.post(url, headers=headers, json=payload, timeout=20)

    if not response.ok:
        # Log the API error without ever logging the access token.
        print(f"WhatsApp API error {response.status_code}: {response.text}")
        response.raise_for_status()

    result = response.json()
    print(f"WhatsApp reply sent to {recipient_wa_id}: {result}")
    return result


@app.route("/", methods=["GET"])
def home():
    return "Night of Freedom WhatsApp webhook is running.", 200


@app.route("/webhook", methods=["GET"])
def verify_webhook():
    mode = request.args.get("hub.mode")
    token = request.args.get("hub.verify_token")
    challenge = request.args.get("hub.challenge")

    if mode == "subscribe" and VERIFY_TOKEN and token == VERIFY_TOKEN:
        return challenge, 200

    return "Verification failed", 403


@app.route("/webhook", methods=["POST"])
def receive_webhook():
    data = request.get_json(silent=True) or {}
    print("WhatsApp webhook received:")
    print(data)

    # Ignore non-WhatsApp webhook payloads.
    if data.get("object") != "whatsapp_business_account":
        return "EVENT_RECEIVED", 200

    try:
        for entry in data.get("entry", []):
            for change in entry.get("changes", []):
                value = change.get("value", {})

                # Status updates (sent/delivered/read/failed) are not messages.
                messages = value.get("messages", [])
                for message in messages:
                    # Only reply to incoming text messages for now.
                    if message.get("type") != "text":
                        continue

                    sender = message.get("from")
                    if not sender:
                        continue

                    incoming_text = message.get("text", {}).get("body", "")
                    print(f"Incoming WhatsApp text from {sender}: {incoming_text}")

                    send_whatsapp_text(sender, AUTO_REPLY_TEXT)

    except Exception as exc:
        # Return 200 so Meta doesn't repeatedly retry a webhook solely because
        # our downstream send failed. The full error remains visible in Railway logs.
        print(f"Webhook processing error: {exc}")

    return "EVENT_RECEIVED", 200


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)
