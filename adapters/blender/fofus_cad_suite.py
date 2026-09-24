# FOFUS CAD Suite — Blender adapter (v2)
# Login with your FOFUS account, show your designer status, open your dashboard.
# Install: Blender → Edit → Preferences → Add-ons → Install → pick this file.
#
# First run: click "Log in with FOFUS" → browser opens designai.fofus.in/cad-link
# → after login the page hands your session back to this addon automatically.
# Fallback: paste an email + password (sent once over HTTPS, only a JWT is stored).
#
# Uninstall: remove here + click Log out (revokes this device server-side).

bl_info = {
    "name": "FOFUS CAD Suite",
    "author": "FOFUS (GNI Labs LLP)",
    "version": (2, 0, 0),
    "blender": (3, 0, 0),
    "location": "View3D > Sidebar > FOFUS",
    "description": "FOFUS account login, designer status panel, and genuine-designing presence",
    "category": "System",
}

import bpy
import hashlib
import hmac
import http.server
import json
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

API = "https://designai.fofus.in/api"
CAD_LINK = "https://designai.fofus.in/cad-link"
TOOL = "blender"
HEARTBEAT_SEC = 60
IDLE_SEC = 600

_last_activity = 0.0
_timer_running = False
_callback_server = None


def _touch(*_args):
    global _last_activity
    _last_activity = time.time()


# ---------------------------------------------------------------- auth helpers

def _store(**values):
    try:
        prefs = bpy.context.preferences.addons[__name__].preferences
        for k, v in values.items():
            setattr(prefs, k, v)
        return True
    except Exception:
        return False


def _load(prop_name):
    try:
        return getattr(bpy.context.preferences.addons[__name__].preferences, prop_name, "")
    except Exception:
        return ""


def _api_post(path, body, extra_headers=None):
    data = json.dumps(body).encode()
    headers = {"Content-Type": "application/json"}
    if extra_headers:
        headers.update(extra_headers)
    req = urllib.request.Request(API + path, data=data, headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.loads(r.read().decode())


def _api_get(path, jwt):
    req = urllib.request.Request(API + path, headers={"Authorization": "Bearer " + jwt})
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.loads(r.read().decode())


def _login(email, password):
    """POST /api/login -> JWT. Raises with server detail on failure."""
    return _api_post("/login", {"email": email, "password": password})


def _auto_pair(jwt):
    """Mint a presence token for this device directly (no manual pairing code)."""
    return _api_post("/designers/me/presence/auto-pair?tool=" + TOOL, {},
                     {"Authorization": "Bearer " + jwt})


def _refresh_account(jwt):
    try:
        prof = _api_get("/designers/me/profile", jwt)
        _store(jwt=jwt)
        # profile shape: DesignerProfileOut — pick the fields we show
        name = prof.get("name") or prof.get("user", {}).get("name") or "Designer"
        rank = prof.get("rank") or prof.get("rank_position") or ""
        wallet = prof.get("wallet_balance") or prof.get("wallet") or ""
        points = prof.get("points") or prof.get("credit_points") or ""
        _store(acc_name=str(name), acc_rank=str(rank), acc_wallet=str(wallet),
               acc_points=str(points), acc_error="")
    except Exception as e:
        _store(acc_error=str(e)[:120])


# ------------------------------------------------- localhost callback receiver

class _CallbackHandler(http.server.BaseHTTPRequestHandler):  # noqa: N801
    def do_GET(self):  # noqa: N802
        q = urllib.parse.urlparse(self.path)
        params = urllib.parse.parse_qs(q.query)
        jwt = (params.get("jwt") or [""])[0]
        if q.path == "/fofus-cad-callback" and jwt:
            _store(jwt=jwt, login_state="linked")
            try:
                pair = _auto_pair(jwt)
                _store(token=pair.get("token", ""))
            except Exception as e:
                _store(acc_error=str(e)[:120])
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(b"<h2>FOFUS CAD Suite connected.</h2>You can close this tab.")
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, format, *args):  # noqa: A002
        pass


def _start_callback_server():
    global _callback_server
    if _callback_server is not None:
        return
    import http.server
    import socketserver

    class _AllowReuse(socketserver.ThreadingTCPServer):
        allow_reuse_address = True

    try:
        _callback_server = _AllowReuse(("127.0.0.1", 7462), _CallbackHandler)
    except OSError:
        _callback_server = None
        return
    threading.Thread(target=_callback_server.serve_forever, daemon=True).start()


def _open_browser(url):
    try:
        import webbrowser
        webbrowser.open(url)
    except Exception:
        pass


# ------------------------------------------------------------------- presence

def _heartbeat():
    global _timer_running
    tok = _load("token")
    if tok:
        try:
            idle = int(time.time() - _last_activity)
            active = idle <= IDLE_SEC
            ts = int(time.time())
            sig = hmac.new(tok.encode(), f"{ts}:{TOOL}:{active}:{idle}".encode(),
                           hashlib.sha256).hexdigest()
            body = json.dumps({"tool": TOOL, "active": active, "idle_sec": idle,
                               "ts": ts, "sig": sig})
            req = urllib.request.Request(
                API + "/designers/presence/heartbeat",
                data=body.encode(),
                headers={"Content-Type": "application/json",
                         "x-fofus-presence": tok})
            urllib.request.urlopen(req, timeout=10)
        except Exception:
            pass
    _timer_running = bpy.app.timers.is_registered(_heartbeat)


# --------------------------------------------------------------------- panels

class FOFUS_OT_login_browser(bpy.types.Operator):
    bl_idname = "fofus.login_browser"
    bl_label = "Log in with FOFUS"
    bl_description = "Opens designai.fofus.in — after login this addon links itself"

    def execute(self, context):
        _start_callback_server()
        _open_browser(CAD_LINK + "?tool=" + TOOL)
        self.report({"INFO"}, "Browser opened - finish login there")
        return {"FINISHED"}


class FOFUS_OT_login_manual(bpy.types.Operator):
    bl_idname = "fofus.login_manual"
    bl_label = "Log in (email + password)"
    bl_idname_dox = None
    email: bpy.props.StringProperty(name="Email")
    password: bpy.props.StringProperty(name="Password", subtype="PASSWORD")

    def execute(self, context):
        try:
            resp = _login(self.email, self.password)
            jwt = resp.get("access_token", "")
            if not jwt:
                self.report({"ERROR"}, "Login failed")
                return {"CANCELLED"}
            _store(jwt=jwt, login_state="linked", acc_error="")
            try:
                pair = _auto_pair(jwt)
                _store(token=pair.get("token", ""))
            except Exception as e:
                self.report({"WARNING"}, "Linked, but auto-pair failed: " + str(e)[:60])
            _refresh_account(jwt)
            self.report({"INFO"}, "Logged in as " + str(_load("acc_name")))
            return {"FINISHED"}
        except urllib.error.HTTPError as e:
            self.report({"ERROR"}, "Login failed: HTTP %d" % e.code)
            return {"CANCELLED"}
        except Exception as e:
            self.report({"ERROR"}, "Login failed: " + str(e)[:80])
            return {"CANCELLED"}

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self)


class FOFUS_OT_logout(bpy.types.Operator):
    bl_idname = "fofus.logout"
    bl_label = "Log out"

    def execute(self, context):
        _store(jwt="", token="", login_state="", acc_name="", acc_rank="",
               acc_wallet="", acc_points="", acc_error="")
        self.report({"INFO"}, "Logged out - revoke the device on the dashboard too")
        return {"FINISHED"}


class FOFUS_OT_open_dashboard(bpy.types.Operator):
    bl_idname = "fofus.open_dashboard"
    bl_label = "Open FOFUS Dashboard"

    def execute(self, context):
        _open_browser("https://designai.fofus.in")
        return {"FINISHED"}


class FOFUS_OT_refresh(bpy.types.Operator):
    bl_idname = "fofus.refresh_account"
    bl_label = "Refresh account"

    def execute(self, context):
        jwt = _load("jwt")
        if jwt:
            _refresh_account(jwt)
        return {"FINISHED"}


class FOFUS_PT_panel(bpy.types.Panel):
    bl_label = "FOFUS"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "FOFUS"

    def draw(self, context):
        layout = self.layout
        jwt = _load("jwt")
        if not jwt:
            layout.label(text="Not logged in", icon="USER")
            layout.operator("fofus.login_browser", icon="URL")
            layout.operator("fofus.login_manual", icon="USER")
            return
        col = layout.column(align=True)
        col.label(text="Account", icon="USER")
        name = _load("acc_name") or "Designer"
        col.label(text="  " + name)
        if _load("acc_rank"):
            col.label(text="  Rank: " + _load("acc_rank"))
        if _load("acc_wallet"):
            col.label(text="  Wallet: " + _load("acc_wallet"))
        if _load("acc_points"):
            col.label(text="  Points: " + _load("acc_points"))
        if _load("acc_error"):
            col.label(text="  Sync error", icon="ERROR")
        layout.operator("fofus.refresh_account", icon="FILE_REFRESH")
        layout.operator("fofus.open_dashboard", icon="URL")
        layout.operator("fofus.logout", icon="X")


# --------------------------------------------------------------- registration

classes = (
    FOFUS_OT_login_browser,
    FOFUS_OT_login_manual,
    FOFUS_OT_logout,
    FOFUS_OT_open_dashboard,
    FOFUS_OT_refresh,
    FOFUS_PT_panel,
)


class FofusPreferences(bpy.types.AddonPreferences):
    bl_idname = __name__

    jwt: bpy.props.StringProperty(default="")
    token: bpy.props.StringProperty(default="")
    login_state: bpy.props.StringProperty(default="")
    acc_name: bpy.props.StringProperty(default="")
    acc_rank: bpy.props.StringProperty(default="")
    acc_wallet: bpy.props.StringProperty(default="")
    acc_points: bpy.props.StringProperty(default="")
    acc_error: bpy.props.StringProperty(default="")

    def draw(self, context):
        layout = self.layout
        layout.label(text="FOFUS CAD Suite - presence + account")
        if not _load("jwt"):
            layout.operator("fofus.login_browser", icon="URL")
            layout.operator("fofus.login_manual", icon="USER")


def register():
    for c in classes:
        bpy.utils.register_class(c)
    bpy.utils.register_class(FofusPreferences)
    global _timer_running
    if not _timer_running:
        if not bpy.app.timers.is_registered(_heartbeat):
            bpy.app.timers.register(_heartbeat, first_interval=HEARTBEAT_SEC, persistent=True)
        _timer_running = True
    _install_handlers()


def _install_handlers():
    handlers = (
        bpy.app.handlers.load_post,
        bpy.app.handlers.save_post,
        bpy.app.handlers.depsgraph_update_post,
        bpy.app.handlers.frame_change_post,
    )
    for h in handlers:
        for fn in tuple(h):
            if fn.__name__ == "_touch":
                h.remove(fn)
        h.append(_touch)


def unregister():
    global _timer_running, _callback_server
    if bpy.app.timers.is_registered(_heartbeat):
        bpy.app.timers.unregister(_heartbeat)
    _timer_running = False
    for h in (bpy.app.handlers.load_post, bpy.app.handlers.save_post,
              bpy.app.handlers.depsgraph_update_post, bpy.app.handlers.frame_change_post):
        for fn in tuple(h):
            if fn.__name__ == "_touch":
                h.remove(fn)
    if _callback_server is not None:
        _callback_server.shutdown()
        _callback_server = None
    for c in reversed(classes):
        bpy.utils.unregister_class(c)
    bpy.utils.unregister_class(FofusPreferences)


if __name__ == "__main__":
    register()