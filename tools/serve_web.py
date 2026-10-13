"""Serve web/ for local testing, without browser caching (python -m http.server sends no Cache-Control, so a browser keeps
the page's files for hours and can run an old script next to a new one).

    python tools/serve_web.py [port]      (default 8000)
"""
from __future__ import annotations
import functools
import http.server
import sys
from pathlib import Path

WEB = Path(__file__).resolve().parent.parent / "web"


class NoCache(http.server.SimpleHTTPRequestHandler):
    def end_headers(self) -> None:
        self.send_header("Cache-Control", "no-store, max-age=0")
        super().end_headers()


def main() -> None:
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8000
    handler = functools.partial(NoCache, directory=str(WEB))
    with http.server.ThreadingHTTPServer(("127.0.0.1", port), handler) as srv:
        print(f"serving {WEB} on http://localhost:{port}/ (no cache)", flush=True)
        srv.serve_forever()


if __name__ == "__main__":
    main()
