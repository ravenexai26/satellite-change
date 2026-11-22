#!/usr/bin/env python3
"""Start the Ravenex Satellite Change web app.

    python serve.py                  # http://localhost:8000, opens your browser
    python serve.py --port 9000 --no-browser
    python serve.py --host 0.0.0.0   # let other computers on your network open it (use only on a trusted network)
"""
import argparse
import threading
import webbrowser

import uvicorn


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8000)
    ap.add_argument("--no-browser", action="store_true")
    a = ap.parse_args()
    url = f"http://{'localhost' if a.host in ('127.0.0.1', '0.0.0.0') else a.host}:{a.port}"
    print(f"Ravenex Satellite Change running at {url}  (Ctrl+C to stop)")
    if not a.no_browser:
        threading.Timer(1.5, lambda: webbrowser.open(url)).start()
    uvicorn.run("schange.server:app", host=a.host, port=a.port, log_level="warning")


if __name__ == "__main__":
    main()
