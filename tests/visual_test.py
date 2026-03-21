#!/usr/bin/env python3
"""
Visual test helper for Incremento PDF cards.

Starts Anki with Chrome DevTools Protocol enabled, navigates to an
Incremento PDF card via AnkiConnect, waits for rendering, then:
  - evaluates JS state in the live card webview
  - captures a screenshot of the page

Usage:
    python tests/visual_test.py [--restart]

    --restart  kill any running Anki first (required to enable debug port
               if Anki was started without it)

Output:
    /tmp/incremento_test.png   (screenshot for Claude to read)
    JS state dict printed to stdout
"""

import base64
import json
import os
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request

DEBUG_PORT = 9222
AC_URL     = "http://localhost:8765"
SCREENSHOT = "/tmp/incremento_test.png"
PDF_QUERY  = 'note:"Incremento PDF"'
ANKI_BIN   = shutil.which("anki") or \
             "/Library/Frameworks/Python.framework/Versions/3.12/bin/anki"


# ── AnkiConnect ──────────────────────────────────────────────────────────────

def ac(action, **params):
    payload = json.dumps({"action": action, "version": 6, "params": params}).encode()
    try:
        resp = json.loads(
            urllib.request.urlopen(
                urllib.request.Request(AC_URL, payload), timeout=5
            ).read()
        )
        if resp.get("error"):
            return None
        return resp["result"]
    except urllib.error.URLError:
        return None


def wait_for_anki(timeout=30):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if ac("version") is not None:
            return True
        time.sleep(0.5)
    return False


# ── Chrome DevTools Protocol ─────────────────────────────────────────────────

def cdp_pages():
    try:
        data = urllib.request.urlopen(
            f"http://localhost:{DEBUG_PORT}/json/list", timeout=2
        ).read()
        return json.loads(data)
    except Exception:
        return []


def cdp_call(ws_url, method, params=None):
    import websocket
    ws = websocket.create_connection(ws_url, timeout=8)
    ws.send(json.dumps({"id": 1, "method": method, "params": params or {}}))
    result = json.loads(ws.recv())
    ws.close()
    return result.get("result", {})


def cdp_eval(ws_url, expression):
    result = cdp_call(ws_url, "Runtime.evaluate", {
        "expression": expression,
        "returnByValue": True,
        "awaitPromise": False,
    })
    return result.get("result", {}).get("value")


def cdp_screenshot(ws_url, output_path):
    result = cdp_call(ws_url, "Page.captureScreenshot", {"format": "png"})
    data = result.get("data", "")
    if data:
        with open(output_path, "wb") as f:
            f.write(base64.b64decode(data))
        return True
    return False


def find_card_page(pages):
    """Find the webview page that contains the PDF card (reviewer or browser preview)."""
    for p in pages:
        url   = p.get("url", "")
        title = p.get("title", "")
        if any(k in url for k in ("/_anki/", "reviewer", "browser")):
            return p
    # fallback: first non-devtools page
    return next((p for p in pages if "devtools" not in p.get("url", "")), None)


# ── macOS window screenshot fallback ─────────────────────────────────────────

def window_screenshot(output_path):
    try:
        script = (
            'tell application "Anki" to activate\n'
            'delay 0.4\n'
            'tell application "System Events"\n'
            '  tell process "Anki"\n'
            '    return id of window 1\n'
            '  end tell\n'
            'end tell'
        )
        win_id = subprocess.check_output(
            ["osascript", "-e", script], text=True, stderr=subprocess.DEVNULL
        ).strip()
        subprocess.run(
            ["screencapture", "-l", win_id, output_path],
            check=True, capture_output=True
        )
        return True
    except Exception:
        try:
            subprocess.run(["screencapture", "-x", output_path], check=True)
            return True
        except Exception:
            return False


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    force_restart = "--restart" in sys.argv

    # ── 1. Start Anki with debug port if needed ──────────────────────────────
    is_running = ac("version") is not None
    debug_available = bool(cdp_pages())

    if force_restart or (is_running and not debug_available):
        print("Restarting Anki with remote debugging enabled...")
        subprocess.run(["pkill", "-x", "anki"], capture_output=True)
        subprocess.run(["pkill", "-x", "Anki"], capture_output=True)
        time.sleep(2)
        is_running = False

    if not is_running:
        print(f"Starting Anki (debug port {DEBUG_PORT})...")
        env = os.environ.copy()
        env["QTWEBENGINE_REMOTE_DEBUGGING"] = str(DEBUG_PORT)
        subprocess.Popen(
            [ANKI_BIN], env=env,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )
        if not wait_for_anki(timeout=35):
            sys.exit("ERROR: Anki did not respond to AnkiConnect within 35s.")
        time.sleep(2)  # let the UI settle
        print("Anki ready.")
    else:
        print("Anki already running" + (" (debug port active)" if debug_available else " (no debug port — pass --restart to enable)") + ".")

    # ── 2. Navigate to a PDF card ─────────────────────────────────────────────
    note_ids = ac("findNotes", query=PDF_QUERY)
    if not note_ids:
        sys.exit(f"No notes found for query: {PDF_QUERY!r}")

    card_ids = ac("findCards", query=f"nid:{note_ids[0]}")
    if not card_ids:
        sys.exit("No cards found for the PDF note.")

    print(f"Opening card {card_ids[0]} in browser...")
    ac("guiBrowse", query=f"cid:{card_ids[0]}")
    time.sleep(2.5)  # wait for preview to render

    # ── 3. JS state via CDP ───────────────────────────────────────────────────
    pages = cdp_pages()
    page  = find_card_page(pages)

    if page:
        ws_url = page["webSocketDebuggerUrl"]
        print(f"\nCDP target: {page.get('title', '?')}  {page.get('url', '')}")

        state = cdp_eval(ws_url, """
            (function() {
                var root    = document.getElementById('pdf-react-root');
                var canvasA = document.getElementById('pdf-canvas-a');
                var label   = document.getElementById('pdf-page-label');
                var errEl   = document.getElementById('pdf-error');
                return JSON.stringify({
                    reactRootFound:  !!root,
                    reactRootHtml:   root ? root.innerHTML.slice(0, 120) : null,
                    canvasFound:     !!canvasA,
                    canvasSize:      canvasA ? canvasA.width + 'x' + canvasA.height : null,
                    pageLabel:       label ? label.textContent : null,
                    errorText:       errEl  ? errEl.textContent : null,
                    pdfjsLoaded:     typeof window.pdfjsLib !== 'undefined',
                    startFnDefined:  typeof window.incrementoPdfStart === 'function',
                });
            })()
        """)

        if state:
            parsed = json.loads(state)
            print("\nJS state:")
            for k, v in parsed.items():
                print(f"  {k}: {v}")
        else:
            print("CDP eval returned nothing.")

        # ── 4. CDP page screenshot (shows exactly what the webview renders) ──
        print(f"\nCapturing page screenshot via CDP → {SCREENSHOT}")
        ok = cdp_screenshot(ws_url, SCREENSHOT)
        if ok:
            print(f"Saved: {SCREENSHOT}")
            return

    # ── Fallback: macOS window screenshot ────────────────────────────────────
    print(f"\nCDP not available — falling back to screencapture → {SCREENSHOT}")
    if window_screenshot(SCREENSHOT):
        print(f"Saved: {SCREENSHOT}")
    else:
        sys.exit("Screenshot failed.")


if __name__ == "__main__":
    main()
