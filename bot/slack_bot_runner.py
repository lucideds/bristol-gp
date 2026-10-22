# Runs only the Slack bot (button clicks), without the website.
# Not needed if you start main.py, which runs the bot too.
# Run from the project folder with:  python -m bot.slack_bot_runner
from slack_bolt.adapter.socket_mode import SocketModeHandler
from bot.bot import app, SLACK_APP_TOKEN

if __name__ == "__main__":
    SocketModeHandler(app, SLACK_APP_TOKEN).start()
