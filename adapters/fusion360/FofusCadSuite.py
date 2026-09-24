# FOFUS CAD Suite - Fusion 360 adapter (v2.1)
# Design-time addin: FOFUS account login, designer status palette, presence heartbeats.
# Panel text includes WORKS (your job board) + EARNINGS (wallet + recent events) —
# the web app inside Fusion, no other dependency.
#
# Install: copy FofusCadSuite/ + FofusCadSuite.py to %APPDATA%\Autodesk\Autodesk Fusion 360\API\AddIns\FofusCadSuite\
#          (Scripts and Add-Ins → FofusCadSuite → Run / check "Run on startup")
# First run: click "Log in with FOFUS" in the FOFUS panel → browser handoff.
#
# Uninstall: untick in Utilities → Add-Ins + remove folder + Revoke on dashboard.

import adsk.core, adsk.fusion, traceback
import hashlib, hmac, json, threading, time, urllib.request, urllib.parse, urllib.error

API = "https://designai.fofus.in/api"
CAD_LINK = "https://designai.fofus.in/cad-link"
TOOL = "fusion360"
HEARTBEAT_SEC = 60
IDLE_SEC = 600

_app = None
_ui = None
_last_activity = 0.0
_timer = None
_state = {"jwt": "", "token": "", "acc": {}}


def _touch(*_args):
    global _last_activity
    _last_activity = time.time()


def _api_post(path, body, headers=None):
    data = json.dumps(body).encode()
    h = {"Content-Type": "application/json"}
    if headers:
        h.update(headers)
    req = urllib.request.Request(API + path, data=data, headers=h, method="POST")
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.loads(r.read().decode())


def _api_get(path, jwt):
    req = urllib.request.Request(API + path, headers={"Authorization": "Bearer " + jwt})
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.loads(r.read().decode())


def _refresh_account():
    try:
        prof = _api_get("/designers/me/profile", _state["jwt"])
        _state["acc"] = {"name": prof.get("name") or "Designer",
                         "rank": prof.get("rank") or "",
                         "wallet": prof.get("wallet_balance") or "",
                         "points": prof.get("points") or ""}
    except Exception:
        _state["acc"] = {"name": "Designer", "error": True}


def _refresh_works():
    """Pull the designer's kanban board into compact text lines."""
    try:
        board = _api_get("/designers/me/board", _state["jwt"])
        cols = board.get("columns") or {}
        stats = board.get("stats") or {}
        lines = []
        for col_name, cards in cols.items():
            for c in cards:
                line = "{} {} - {}".format(
                    c.get("project_number") or c.get("id", ""), c.get("title", "?"), col_name)
                if c.get("price"):
                    line += " · Rs{}".format(c["price"])
                if c.get("est_earnings"):
                    line += " · earn Rs{}".format(c["est_earnings"])
                if c.get("chat_unread"):
                    line += " · {} chat!".format(c["chat_unread"])
                lines.append(line)
        if not lines:
            lines = ["No works yet - see Opportunities."]
        stats = board.get("stats") or {}
        active = stats.get("In Progress", 0) + stats.get("Working", 0) + stats.get("Active", 0)
        available = stats.get("Available", 0) + stats.get("Unassigned", 0) + stats.get("Opportunities", 0)
        _state["works"] = {"stats": "{} active · {} available".format(active, available),
                           "lines": lines[:10], "error": ""}
    except Exception as e:
        _state["works"] = {"error": str(e)[:100]}


def _refresh_earnings():
    try:
        w = _api_get("/wallet", _state["jwt"])
        ev = _api_get("/earn/mine", _state["jwt"]).get("events") or []
        lines = ["Rs{} - {} - {}".format(e.get("credits", "?"), e.get("source", ""),
                                         str(e.get("period", ""))) for e in ev[:10]]
        if not lines:
            lines = ["No earnings yet - finish a work to earn."]
        _state["earn"] = {"avail": str(w.get("available_balance", "")),
                          "pending": str(w.get("pending_balance", "")),
                          "lifetime": str(w.get("lifetime_earnings", "")),
                          "lines": lines, "error": ""}
    except Exception as e:
        _state["earn"] = {"error": str(e)[:100]}


def _heartbeat_loop():
    global _timer
    while True:
        time.sleep(HEARTBEAT_SEC)
        tok = _state.get("token")
        if not tok or not _app:
            continue
        try:
            idle = int(time.time() - _last_activity)
            active = idle <= IDLE_SEC
            ts = int(time.time())
            sig = hmac.new(tok.encode(), f"{ts}:{TOOL}:{active}:{idle}".encode(), hashlib.sha256).hexdigest()
            body = json.dumps({"tool": TOOL, "active": active, "idle_sec": idle, "ts": ts, "sig": sig})
            req = urllib.request.Request(API + "/designers/presence/heartbeat", data=body.encode(),
                                         headers={"Content-Type": "application/json", "x-fofus-presence": tok})
            urllib.request.urlopen(req, timeout=10)
        except Exception:
            pass


class _CallbackHandler:
    """Serves 127.0.0.1:7462 during login handoff (same port as Blender)."""
    @staticmethod
    def serve_once():
        import http.server, socketserver

        class H(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                q = urllib.parse.urlparse(self.path)
                params = urllib.parse.parse_qs(q.query)
                jwt = (params.get("jwt") or [""])[0]
                if q.path == "/fofus-cad-callback" and jwt:
                    _state["jwt"] = jwt
                    try:
                        pair = _api_post("/designers/me/presence/auto-pair?tool=" + TOOL, {}, {"Authorization": "Bearer " + jwt})
                        _state["token"] = pair.get("token", "")
                    except Exception:
                        pass
                    _refresh_account()
                    self.send_response(200)
                    self.send_header("Content-Type", "text/html")
                    self.end_headers()
                    self.wfile.write(b"<h2>FOFUS CAD Suite connected.</h2>You can close this tab.")
                else:
                    self.send_response(404)
                    self.end_headers()

            def log_message(self, format, *a):  # noqa: A002
                pass

        class Reuse(socketserver.ThreadingTCPServer):
            allow_reuse_address = True
            daemon_threads = True

        httpd = Reuse(("127.0.0.1", 7462), H)
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
        return httpd


def _open_browser(url):
    try:
        import webbrowser
        webbrowser.open(url)
    except Exception:
        pass


def _login_manual(email, password):
    resp = _api_post("/auth/login", {"email": email, "password": password})
    _state["jwt"] = resp.get("access_token", "")
    if _state["jwt"]:
        try:
            pair = _api_post("/designers/me/presence/auto-pair?tool=" + TOOL, {},
                             {"Authorization": "Bearer " + _state["jwt"]})
            _state["token"] = pair.get("token", "")
        except Exception:
            pass
        _refresh_account()
        _refresh_works()
        _refresh_earnings()


class FofusLoginBrowserCommand(adsk.core.CommandBaseEventHandler):
    def __init__(self):
        super().__init__()
        self._handler = None

    def notify(self, args):
        try:
            httpd = _CallbackHandler.serve_once()
            threading.Timer(300, lambda: httpd.shutdown()).start()
            _open_browser(CAD_LINK + "?tool=" + TOOL)
        except Exception:
            if _ui:
                _ui.messageBox("Could not open browser:\n{}".format(traceback.format_exc()))


class FofusLogoutCommand(adsk.core.CommandBaseEventHandler):
    def notify(self, args):
        _state.update({"jwt": "", "token": "", "acc": {}, "works": {}, "earn": {}})
        if _ui:
            _ui.messageBox("Logged out. Revoke the device on the dashboard too.")


class FofusOpenDashboardCommand(adsk.core.CommandBaseEventHandler):
    def notify(self, args):
        _open_browser("https://designai.fofus.in")


class FofusRefreshCommand(adsk.core.CommandBaseEventHandler):
    def notify(self, args):
        if _state.get("jwt"):
            _refresh_account()
            _refresh_works()
            _refresh_earnings()
        if _ui:
            _ui.messageBox(_panel_text())


class FofusOpenBoardCommand(adsk.core.CommandBaseEventHandler):
    def notify(self, args):
        _open_browser("https://designai.fofus.in/designer/board")


def _panel_text():
    acc = _state.get("acc") or {}
    lines = ["FOFUS"]
    if _state.get("jwt"):
        lines.append("ACCOUNT")
        lines.append("  " + str(acc.get("name", "Designer")))
        for k, label in (("rank", "Rank"), ("wallet", "Wallet"), ("points", "Points")):
            if acc.get(k):
                lines.append("  {}: {}".format(label, acc[k]))
        lines.append("Status: presence active")
        lines.append("")
        w = _state.get("works") or {}
        lines.append("WORKS")
        if w.get("stats"):
            lines.append("  " + w["stats"])
        for ln in w.get("lines", []):
            lines.append("  " + ln[:80])
        if w.get("error"):
            lines.append("  (works load failed — run Refresh)")
        lines.append("")
        e = _state.get("earn") or {}
        lines.append("EARNINGS")
        if e.get("avail"):
            lines.append("  Available: Rs" + e["avail"])
        if e.get("pending"):
            lines.append("  Pending: Rs" + e["pending"])
        for ln in e.get("lines", [])[:5]:
            lines.append("  " + ln[:80])
        if e.get("error"):
            lines.append("  (earnings load failed — run Refresh)")
        lines.append("")
        lines.append("Dashboard: designai.fofus.in")
        lines.append("Full board: designai.fofus.in/designer/board")
        lines.append("Earnings: designai.fofus.in/designer/earnings")
    else:
        lines.append("Not logged in")
    return "\n".join(lines)


def run(context):
    global _app, _ui, _timer
    try:
        _app = adsk.core.Application.get()
        _ui = _app.userInterface

        _touch()
        _timer = threading.Thread(target=_heartbeat_loop, daemon=True)
        _timer.start()

        if _state.get("jwt"):
            _refresh_account()
            _refresh_works()
            _refresh_earnings()

        if _ui:
            _ui.messageBox("FOFUS CAD Suite loaded.\n\n" + _panel_text())
    except Exception:
        if _ui:
            _ui.messageBox("Failed:\n{}".format(traceback.format_exc()))


def stop(context):
    try:
        if _timer:
            pass  # daemon thread exits with process
        if _ui:
            _ui.messageBox("FOFUS CAD Suite stopped.")
    except Exception:
        pass