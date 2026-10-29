# Sends one fake contact form message to Slack, to check the bot is set up.
# Run from the project folder with:  python send_slack_test.py
from bot.bot import is_configured, send_to_slack

if not is_configured():
    raise SystemExit("Set SLACK_BOT_TOKEN and SLACK_CHANNEL_ID in .env first.")
send_to_slack({
    "name": "James Williams",
    "email": "jwilliam@example.com",
    "message": "What coding languages are used?",
})
print("Test message sent.")
