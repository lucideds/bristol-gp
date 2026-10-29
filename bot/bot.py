# Posts each contact form message to Slack, with buttons the team can use to triage it.
# main.py starts it in the background. To run only the bot:  python -m bot.bot
import json
import logging
import os

from dotenv import load_dotenv
from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler
from slack_sdk.errors import SlackApiError

log = logging.getLogger(__name__)

# Load the .env file in the project folder (one level up from this bot folder).
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"))

SLACK_BOT_TOKEN = os.environ.get("SLACK_BOT_TOKEN")
SLACK_APP_TOKEN = os.environ.get("SLACK_APP_TOKEN")
SLACK_CHANNEL_ID = os.environ.get("SLACK_CHANNEL_ID")

# Slack only lets a button carry up to 2000 characters.
MAX_BUTTON_VALUE = 2000

# token_verification_enabled=False stops Bolt calling Slack when this file is imported,
# so the website still starts if Slack is down or the token is wrong.
# Bolt refuses to start with no token, so a placeholder is used until one is set;
# is_configured() stops anything being sent with it.
app = App(token=SLACK_BOT_TOKEN or "xoxb-not-set", token_verification_enabled=False)


def is_configured():
    """True when the tokens needed to post messages are set in .env."""
    return bool(SLACK_BOT_TOKEN and SLACK_CHANNEL_ID)


def escape(text):
    """Stops form text being read as Slack formatting, e.g. "<!channel>" pinging everyone."""
    return str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def send_to_slack(payload: dict):
    """Posts one contact form message ({"name", "email", "message"}) to SLACK_CHANNEL_ID."""
    pretty_json = json.dumps(payload, indent=2)[:MAX_BUTTON_VALUE]

    blocks = [
        {
            "type": "header",
            "text": {"type": "plain_text", "text": "📩 New Contact Form Submission"},
        },
        {
            "type": "section",
            "fields": [
                {"type": "mrkdwn", "text": f"*Name:*\n{escape(payload.get('name', ''))}"},
                {"type": "mrkdwn", "text": f"*Email:*\n{escape(payload.get('email', ''))}"},
            ],
        },
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"*Message:*\n```{escape(payload.get('message', ''))}```",
            },
        },
        {
            "type": "actions",
            "elements": [
                {
                    "type": "button",
                    "text": {"type": "plain_text", "text": "✅ Mark Handled"},
                    "style": "primary",
                    "action_id": "mark_handled",
                },
                {
                    "type": "button",
                    "text": {"type": "plain_text", "text": "⭐ Priority"},
                    "style": "danger",
                    "action_id": "priority",
                },
                {
                    "type": "button",
                    "text": {"type": "plain_text", "text": "↩ Reply Needed"},
                    "action_id": "reply_needed",
                },
                {
                    "type": "button",
                    "text": {"type": "plain_text", "text": "📋 View JSON"},
                    "value": pretty_json,
                    "action_id": "view_json",
                },
            ],
        },
    ]

    app.client.chat_postMessage(
        channel=SLACK_CHANNEL_ID,
        blocks=blocks,
        text="New contact form submission",
    )


def reply_in_thread(body, client, text):
    channel_id = body["channel"]["id"]
    message_ts = body["message"]["ts"]
    client.chat_postMessage(channel=channel_id, thread_ts=message_ts, text=text)


@app.action("mark_handled")
def mark_handled(ack, body, client):
    ack()
    user_id = body["user"]["id"]
    reply_in_thread(body, client, f"✅ Handled by <@{user_id}>")


@app.action("priority")
def priority(ack, body, client):
    ack()
    user_id = body["user"]["id"]
    reply_in_thread(body, client, f"⭐ Marked as *HIGH PRIORITY* by <@{user_id}>")


@app.action("reply_needed")
def reply_needed(ack, body, client):
    ack()
    user_id = body["user"]["id"]
    reply_in_thread(body, client, f"↩ Follow-up required. Flagged by <@{user_id}>.")


@app.action("view_json")
def view_json(ack, body, client):
    ack()
    trigger_id = body.get("trigger_id")
    raw_json = escape(body["actions"][0].get("value", "{}"))

    try:
        client.views_open(
            trigger_id=trigger_id,
            view={
                "type": "modal",
                "title": {"type": "plain_text", "text": "Submission JSON"},
                "close": {"type": "plain_text", "text": "Close"},
                "blocks": [
                    {
                        "type": "section",
                        "text": {
                            "type": "mrkdwn",
                            "text": f"```{raw_json[:2900]}```",
                        },
                    }
                ],
            },
        )
    except SlackApiError:
        reply_in_thread(body, client, f"```{raw_json}```")


_handler = None  # Kept so the background connection isn't thrown away.


def start_in_background():
    """Listens for button clicks in a background thread, so main.py can run the website and the bot together.
    Socket Mode connects out to Slack, so it doesn't open any port on this computer."""
    if not (is_configured() and SLACK_APP_TOKEN):
        log.info("Slack bot not started: set SLACK_BOT_TOKEN, SLACK_APP_TOKEN and SLACK_CHANNEL_ID in .env.")
        return
    global _handler
    _handler = SocketModeHandler(app, SLACK_APP_TOKEN)
    _handler.connect()  # connect() returns straight away; start() would block.
    log.info("Slack bot connected.")


if __name__ == "__main__":
    SocketModeHandler(app, SLACK_APP_TOKEN).start()
