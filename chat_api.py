"""AI chat API used by the chat widget (frontend/Template/Sources/js/chatWidget.js).

Passes the conversation on to OpenRouter, so the API key stays on the server.
main.py registers chat_bp with the app.
"""

import json
import logging
import os
import threading
import time
from collections import deque

import requests
from flask import Blueprint, Response, current_app, jsonify, request, stream_with_context

chat_bp = Blueprint("chat_api", __name__)

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
DEFAULT_CHAT_MODEL = "nvidia/nemotron-3.5-super-vl:free"  # Used unless OPENROUTER_MODEL is set.

# Sent before every conversation. Visitors can't change it.
CHAT_SYSTEM_PROMPT = """
You are a virtual assistant on T Level Connect, a website about T Levels and T Level industry placements at Amazon, run for the Amazon Emerging Talent Programs Team. Visitors are mostly students, their parents and carers, and teachers or careers advisers at schools and colleges.

You help with:
- What T Levels are: two-year technical qualifications in England, taken after GCSEs, worth the same as three A levels. Each one includes an industry placement of at least 315 hours (about 45 days) with an employer.
- T Level placements at Amazon: Amazon offers placements in Digital, Business, Media, Finance and Engineering. Explain what a placement involves, the skills it builds, and how it can lead to apprenticeships, university or work.
- Practical advice: choosing a T Level, preparing for a placement, CVs and interviews, and what to expect on a first day at work.
- Finding your way around this website, including the T Levels, Advice, Quiz, FAQs and Contact pages, the accessibility settings, downloading course specifications, and creating an account to register interest.
- Related Amazon routes, such as Amazon Apprenticeships and Step Up work experience.

Rules:
- Answer from the reference information below whenever it covers the question, and do not contradict it. When you send someone to a page on this website, name the page and give its path, for example "the T Levels page (/t-levels)".
- If the reference information does not cover a question about this website or Amazon placements, say you are not sure rather than guessing.
- You cannot see application systems, placement availability, dates, deadlines, locations, pay or eligibility decisions. Never invent these, or names, contact details or policies. If you are not sure, say so and point them to the Contact page or the official Amazon T Level placements page: https://www.aboutamazon.co.uk/amazon-for-schools/online-hub-offerings/t-level-placements
- Never promise that anyone will get a placement or job.
- Many visitors are under 18. Do not ask for personal details such as full names, addresses, phone numbers, email addresses or dates of birth. If someone shares them, do not repeat them.
- If someone says they are unsafe, being harmed, or thinking about harming themselves, tell them kindly to speak to a trusted adult such as a parent, carer or teacher. If they are in immediate danger, tell them to call 999. They can also contact Childline on 0800 1111.
- Stay on topic. If you are asked about something unrelated, politely steer back to T Levels, placements and careers.
- Be fair and inclusive. Do not make assumptions about people based on gender, ethnicity, disability, background or any other characteristic.
- Keep replies short, clear, friendly and encouraging, in plain UK English. Use plain text only, with no markdown.
""".strip()

# Facts about T Levels and the site's pages, kept in a file so they can be edited without touching
# code. Read once at start-up, so restart the server after editing it.
CHAT_KNOWLEDGE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "chat_knowledge.md")
try:
    with open(CHAT_KNOWLEDGE_FILE, encoding="utf-8") as f:
        CHAT_KNOWLEDGE = f.read().strip()
except OSError:
    # The chat still works with just the rules above.
    logging.getLogger(__name__).warning("Chat knowledge file not found: %s", CHAT_KNOWLEDGE_FILE)
    CHAT_KNOWLEDGE = ""
if CHAT_KNOWLEDGE:
    CHAT_SYSTEM_PROMPT += "\n\nReference information:\n\n" + CHAT_KNOWLEDGE

CHAT_MAX_MESSAGES = 20
CHAT_MAX_MESSAGE_CHARS = 4000
CHAT_MAX_BODY_BYTES = 100_000
CHAT_RATE_LIMIT = 10            # Requests per IP address...
CHAT_RATE_WINDOW = 60           # ...per this many seconds.
CHAT_TIMEOUT = (5, 90)          # (connect, read) seconds. When streaming, "read" is the longest gap between chunks.
CHAT_STREAM_MAX_SECONDS = 120   # Longest a whole streamed reply may take.
CHAT_MAX_TOKENS = 4096          # Includes the model's thinking.
# Low effort keeps thinking to a small share of CHAT_MAX_TOKENS, so the reply isn't cut off.
# exclude stops the thinking ever being sent back to us or to visitors.
CHAT_REASONING = {"effort": "low", "exclude": True}

# IP address -> times of its recent chat requests. In memory, so it resets on restart.
# Uses request.remote_addr, not X-Forwarded-For, because anyone can fake that header. If the site
# is ever put behind a proxy, use Werkzeug's ProxyFix so remote_addr is the real visitor.
_chat_hits = {}
_chat_hits_lock = threading.Lock()


def _drop_old_hits(hits, now):
    while hits and now - hits[0] >= CHAT_RATE_WINDOW:
        hits.popleft()


def chat_rate_limited(ip):
    """Records a chat request from this IP. Returns 0 if it's allowed, or the seconds to wait."""
    now = time.monotonic()
    with _chat_hits_lock:
        if len(_chat_hits) > 1000:  # Forget IPs that have gone quiet, so memory use stays small.
            for key in list(_chat_hits):
                _drop_old_hits(_chat_hits[key], now)
                if not _chat_hits[key]:
                    del _chat_hits[key]

        hits = _chat_hits.setdefault(ip, deque())
        _drop_old_hits(hits, now)
        if len(hits) >= CHAT_RATE_LIMIT:
            return int(CHAT_RATE_WINDOW - (now - hits[0])) + 1  # Until the oldest request expires.
        hits.append(now)
        return 0


def validate_chat_messages(payload):
    """Checks the JSON sent by the chat widget.
    Returns (clean_messages, None) if it's fine, or (None, "reason") if it isn't."""
    if not isinstance(payload, dict):
        return None, "expected a JSON object."
    messages = payload.get("messages")
    if not isinstance(messages, list):
        return None, "'messages' must be a list."
    if not 1 <= len(messages) <= CHAT_MAX_MESSAGES:
        return None, f"'messages' must contain between 1 and {CHAT_MAX_MESSAGES} items."

    clean = []
    for item in messages:
        if not isinstance(item, dict):
            return None, "each message must be an object."
        role = item.get("role")
        content = item.get("content")
        # Only "user" and "assistant" are allowed, so visitors can't send their own "system" instructions.
        if role not in ("user", "assistant"):
            return None, "each message role must be 'user' or 'assistant'."
        if not isinstance(content, str) or not content.strip():
            return None, "each message must have some text."
        content = content.strip()
        if len(content) > CHAT_MAX_MESSAGE_CHARS:
            return None, f"each message must be at most {CHAT_MAX_MESSAGE_CHARS} characters."
        clean.append({"role": role, "content": content})  # Drop any other keys.

    if clean[-1]["role"] != "user":
        return None, "the last message must be from the user."
    return clean, None


def chat_error(message, status):
    return jsonify({"error": message}), status


def check_chat_request():
    """Runs the checks both chat routes share: rate limit, body size, JSON, API key.
    Returns (error_response, None) if something is wrong, or (None, (messages, api_key, model)) if it's fine."""
    # Rate limit first, so it protects everything below. Both routes share one limit.
    retry_after = chat_rate_limited(request.remote_addr or "unknown")
    if retry_after:
        response, status = chat_error(
            "You're sending messages too quickly. Please wait a moment and try again.", 429
        )
        response.headers["Retry-After"] = str(retry_after)
        return (response, status), None

    if request.content_length is not None and request.content_length > CHAT_MAX_BODY_BYTES:
        return chat_error("Your message is too long.", 413), None
    # A conversation can be bigger than main.py's 16 KB form limit, so raise it for this request only.
    request.max_content_length = CHAT_MAX_BODY_BYTES

    # silent=True gives None for bad JSON. get_json also needs the application/json content type,
    # which normal HTML forms can't send.
    clean, problem = validate_chat_messages(request.get_json(silent=True))
    if problem:
        return chat_error("Invalid request: " + problem, 400), None

    # Read per request, so the settings can change without a code edit.
    api_key = os.environ.get("OPENROUTER_API_KEY", "").strip()
    if not api_key:
        return chat_error("The chat assistant is not available: API key not configured.", 503), None
    model = os.environ.get("OPENROUTER_MODEL", "").strip() or DEFAULT_CHAT_MODEL
    return None, (clean, api_key, model)


def call_openrouter(clean, api_key, model, stream=False):
    """Sends the conversation to OpenRouter.
    Returns (response, None) if OpenRouter answered, or (None, error_response) if it couldn't be reached.
    Error messages sent back never include the key, upstream details or tracebacks."""
    body = {
        "model": model,
        "messages": [{"role": "system", "content": CHAT_SYSTEM_PROMPT}] + clean,
        "max_tokens": CHAT_MAX_TOKENS,
        "temperature": 0.3,
        "reasoning": dict(CHAT_REASONING),
    }
    if stream:
        body["stream"] = True
    try:
        resp = requests.post(
            OPENROUTER_URL,
            headers={
                "Authorization": "Bearer " + api_key,
                "Content-Type": "application/json",
                "HTTP-Referer": os.environ.get("OPENROUTER_SITE_URL") or request.host_url,
                "X-Title": "T Level Connect",
            },
            json=body,
            timeout=CHAT_TIMEOUT,
            stream=stream,
        )
    except requests.Timeout:
        current_app.logger.warning("OpenRouter request timed out")
        return None, chat_error("The assistant took too long to reply. Please try again.", 504)
    except requests.RequestException as exc:
        current_app.logger.warning("OpenRouter request failed: %s", type(exc).__name__)
        return None, chat_error("Couldn't reach the assistant service. Please try again later.", 502)
    return resp, None


def upstream_status_error(resp):
    """Returns an error response if OpenRouter answered with an error status, or None if it's fine."""
    if 200 <= resp.status_code < 300:
        return None
    current_app.logger.warning("OpenRouter error %s: %s", resp.status_code, resp.text[:300])
    if resp.status_code == 429:  # OpenRouter (or the free model) is rate limiting us.
        return chat_error("The assistant is busy right now. Please try again in a minute.", 503)
    return chat_error("The assistant is temporarily unavailable. Please try again later.", 502)  # e.g. a bad key (401/403).


@chat_bp.route("/api/chat", methods=["POST"])
def chat():
    """Returns the whole reply as {"reply": "..."}, or {"error": "..."}."""
    error, ctx = check_chat_request()
    if error:
        return error
    resp, error = call_openrouter(*ctx)
    if error:
        return error
    error = upstream_status_error(resp)
    if error:
        return error

    no_reply = "The assistant couldn't come up with a reply. Please try again."
    try:
        data = resp.json()
        content = None
        if isinstance(data, dict) and "error" not in data:
            choice = data["choices"][0]
            content = choice["message"]["content"]
            if choice.get("finish_reason") == "length":
                current_app.logger.warning("OpenRouter reply hit max_tokens")
    except ValueError:
        current_app.logger.warning("OpenRouter returned invalid JSON: %s", resp.text[:300])
        return chat_error(no_reply, 502)
    except Exception:  # Unexpected shape, e.g. no "choices".
        current_app.logger.exception("Unexpected OpenRouter response")
        return chat_error(no_reply, 502)

    if not isinstance(content, str) or not content.strip():
        current_app.logger.warning("OpenRouter gave no reply text: %s", resp.text[:300])
        return chat_error(no_reply, 502)

    return jsonify({"reply": content.strip()})


# ----- Streaming chat -----
# /api/chat/stream sends the reply as Server-Sent Events: "data: <json>" lines, each followed
# by a blank line. The JSON is one of:
#   {"delta": "some text"}   - more of the reply, add it to the end
#   {"done": true}           - the reply is finished
#   {"error": "message"}     - something went wrong (the stream ends after this)
# Problems found before streaming starts (bad request, rate limit, no key, OpenRouter down)
# are sent back as normal JSON errors with a status code, like /api/chat.

STREAM_NO_REPLY = "The assistant couldn't come up with a reply. Please try again."
STREAM_INTERRUPTED = "The assistant's reply was interrupted. Please try again."
STREAM_UPSTREAM_ERROR = "The assistant is temporarily unavailable. Please try again later."
STREAM_TOO_LONG = "The assistant took too long to reply. Please try again."


def sse(obj):
    return "data: " + json.dumps(obj) + "\n\n"


def generate_chat_stream(resp):
    """Reads OpenRouter's streamed reply and passes on just the reply text, one SSE message at a time.
    Only "content" is ever sent on, never the model's hidden "reasoning"."""
    started = False        # Any reply text sent yet?
    finished = False       # Did OpenRouter say the reply was complete?
    deadline = time.monotonic() + CHAT_STREAM_MAX_SECONDS
    try:
        # iter_lines() gives bytes. We decode them as UTF-8 ourselves, because OpenRouter doesn't say
        # which encoding it uses and requests would guess wrongly (turning ’ and £ into nonsense).
        for raw in resp.iter_lines():
            if time.monotonic() > deadline:
                current_app.logger.warning("OpenRouter stream took longer than %s seconds", CHAT_STREAM_MAX_SECONDS)
                yield sse({"error": STREAM_TOO_LONG})
                return
            line = raw.decode("utf-8", "replace") if isinstance(raw, bytes) else raw
            if not line or line.startswith(":"):  # Blank separators and comments like ": OPENROUTER PROCESSING".
                continue
            if not line.startswith("data:"):
                continue
            data = line[5:].strip()
            if data == "[DONE]":
                finished = True
                break
            try:
                chunk = json.loads(data)
            except ValueError:
                current_app.logger.warning("OpenRouter sent invalid stream JSON: %s", data[:200])
                continue
            if not isinstance(chunk, dict):
                continue
            if "error" in chunk:  # OpenRouter hit a problem part-way through.
                current_app.logger.warning("OpenRouter stream error: %s", str(chunk["error"])[:300])
                yield sse({"error": STREAM_UPSTREAM_ERROR})
                return
            choices = chunk.get("choices")
            if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
                continue  # e.g. the last chunk, which only holds token usage.
            choice = choices[0]
            delta = choice.get("delta")
            text = delta.get("content") if isinstance(delta, dict) else None
            if isinstance(text, str) and text:
                if not started:
                    text = text.lstrip()  # Like .strip() on /api/chat: no blank lines at the start.
                    if not text:
                        continue
                    started = True
                yield sse({"delta": text})
            reason = choice.get("finish_reason")
            if reason == "error":
                current_app.logger.warning("OpenRouter stream finished with an error")
                yield sse({"error": STREAM_UPSTREAM_ERROR})
                return
            if reason == "length":
                current_app.logger.warning("OpenRouter reply hit max_tokens")
            if reason:
                finished = True  # Keep reading until [DONE].
    # A dropped connection or slow reply (read timeouts arrive as ConnectionError).
    except requests.RequestException as exc:
        current_app.logger.warning("OpenRouter stream failed: %s", type(exc).__name__)
        yield sse({"error": STREAM_INTERRUPTED})
        return
    except Exception:
        current_app.logger.exception("Unexpected error while streaming")
        yield sse({"error": STREAM_INTERRUPTED})
        return
    finally:
        resp.close()  # Free the connection to OpenRouter, even if the visitor left.

    if not started:
        current_app.logger.warning("OpenRouter stream gave no reply text")
        yield sse({"error": STREAM_NO_REPLY})
        return
    if not finished:
        current_app.logger.warning("OpenRouter stream ended early")
        yield sse({"error": STREAM_INTERRUPTED})
        return
    yield sse({"done": True})


@chat_bp.route("/api/chat/stream", methods=["POST"])
def chat_stream():
    """Like /api/chat, but sends the reply as Server-Sent Events while it's being written."""
    error, ctx = check_chat_request()
    if error:
        return error
    resp, error = call_openrouter(*ctx, stream=True)
    if error:
        return error
    error = upstream_status_error(resp)
    if error:
        resp.close()
        return error

    # stream_with_context keeps the request (and current_app, used for logging) available
    # while generate_chat_stream runs, which is after this function has returned.
    return Response(
        stream_with_context(generate_chat_stream(resp)),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",  # Stops proxies like nginx buffering the stream.
        },
    )
