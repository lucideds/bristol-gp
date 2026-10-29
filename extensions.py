"""Flask extensions shared by main.py and chat_api.py.

They live here, not in main.py, so chat_api.py can use them without a circular import.
main.py attaches them to the app with init_app().
"""

from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

# Counts requests per IP address, in memory, so the counts reset when the server restarts.
# get_remote_address uses request.remote_addr, not X-Forwarded-For, which anyone can fake.
# If the site is ever put behind a proxy, use Werkzeug's ProxyFix so remote_addr is the real visitor.
limiter = Limiter(get_remote_address, storage_uri="memory://")
