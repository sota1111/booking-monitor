"""Shared pytest fixtures for integration tests.

Provides a lightweight local HTTP server that serves the static HTML fixtures
in ``tests/fixtures/``. This lets the check logic run against a mock site
without touching the network, using only the standard library.
"""

import functools
import http.server
import os
import threading

import pytest

FIXTURES_DIR = os.path.join(os.path.dirname(__file__), "fixtures")


@pytest.fixture(scope="session")
def fixture_server():
    """Start a threaded HTTP server serving ``tests/fixtures``.

    Yields the base URL (e.g. ``http://127.0.0.1:54321``). The OS picks a free
    port. The server is shut down cleanly at the end of the session.
    """
    handler = functools.partial(
        http.server.SimpleHTTPRequestHandler, directory=FIXTURES_DIR
    )
    # Port 0 -> OS assigns a free port.
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        # We bound to 127.0.0.1; only the OS-assigned port is dynamic.
        port = server.server_address[1]
        yield f"http://127.0.0.1:{port}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
