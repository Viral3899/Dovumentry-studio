"""Single entry point for the documentary generator API.

The API implementation lives in ``app.py`` so it remains importable by tests
and WSGI servers. Running this file starts the same Flask application used by
the frontend and exposes both pipeline stages through its API routes.
"""

import os

from app import app


if __name__ == "__main__":
    app.run(
        debug=os.getenv("FLASK_DEBUG") == "1",
        use_reloader=False,
        host="0.0.0.0",
        port=int(os.getenv("PORT", "5000")),
    )