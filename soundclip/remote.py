"""Fernbedienung: Soundboard im Handy-Browser (WLAN) und Aufruf-Links fuer Stream Deck / OBS.

Ein kleiner HTTP-Server im Hintergrund. Jede Anfrage braucht den geheimen Schluessel (Token) aus den
Einstellungen - ohne ihn kann niemand im Netz etwas ausloesen. Ohne Handy-Fernbedienung hoert der Server
nur auf diesem PC (127.0.0.1)."""
from __future__ import annotations

import json
import logging
import secrets
import socket
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, quote, unquote, urlparse

log = logging.getLogger("soundclip")

DEFAULT_PORT = 8765


def lan_ip() -> str:
    """IP-Adresse dieses PCs im Heimnetz (es wird dabei nichts gesendet)."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("10.255.255.255", 1))
        ip = s.getsockname()[0]
    except Exception:
        ip = "127.0.0.1"
    finally:
        s.close()
    return ip


def ensure_token(cfg) -> str:
    tok = str(cfg.get("remote_token") or "")
    if len(tok) < 12:
        tok = secrets.token_urlsafe(12)
        cfg["remote_token"] = tok
    return tok


class RemoteServer:
    def __init__(self, ctl):
        self.ctl = ctl
        self.httpd: ThreadingHTTPServer | None = None
        self.thread: threading.Thread | None = None
        self.host = ""
        self.port = 0
        self.error = ""

    # ---- Lebenszyklus
    def wanted_host(self) -> str:
        cfg = self.ctl.cfg
        if cfg.get("remote_enabled"):
            return "0.0.0.0"
        if cfg.get("api_enabled"):
            return "127.0.0.1"
        return ""

    def sync(self):
        host = self.wanted_host()
        if self.httpd and host == self.host:
            return
        self.stop()
        if host:
            self.start(host)

    def start(self, host: str):
        ensure_token(self.ctl.cfg)
        base = int(self.ctl.cfg.get("remote_port") or DEFAULT_PORT)
        self.error = ""
        for port in range(base, base + 10):
            try:
                httpd = ThreadingHTTPServer((host, port), _make_handler(self))
                break
            except OSError as e:
                self.error = str(e)
                httpd = None
        if httpd is None:
            log.warning("Fernbedienung: kein freier Port (%s)", self.error)
            return
        httpd.daemon_threads = True
        self.httpd, self.host, self.port = httpd, host, httpd.server_address[1]
        self.error = ""
        self.thread = threading.Thread(target=httpd.serve_forever, kwargs={"poll_interval": 0.3},
                                       daemon=True, name="remote-http")
        self.thread.start()
        log.info("Fernbedienung laeuft auf %s:%s", host, self.port)

    def stop(self):
        h = self.httpd
        self.httpd = None
        self.host = ""
        if h:
            try:
                h.shutdown()
                h.server_close()
            except Exception:
                pass

    @property
    def running(self) -> bool:
        return self.httpd is not None

    # ---- Adressen fuer die Einstellungen
    def phone_url(self) -> str:
        return f"http://{lan_ip()}:{self.port}/?t={quote(ensure_token(self.ctl.cfg))}"

    def local_url(self, path: str) -> str:
        sep = "&" if "?" in path else "?"
        return f"http://127.0.0.1:{self.port}{path}{sep}t={quote(ensure_token(self.ctl.cfg))}"


def _make_handler(server: RemoteServer):
    ctl = server.ctl

    class Handler(BaseHTTPRequestHandler):
        server_version = "PotatoClips"
        protocol_version = "HTTP/1.1"

        def log_message(self, *a):
            pass

        # ---- Hilfen
        def _token_ok(self, qs) -> bool:
            want = ensure_token(ctl.cfg)
            got = (qs.get("t") or [""])[0] or self.headers.get("X-Token", "")
            if not got:
                for part in self.headers.get("Cookie", "").split(";"):
                    k, _, v = part.strip().partition("=")
                    if k == "pc_t":
                        got = v
            return bool(got) and secrets.compare_digest(got, want)

        def _send(self, code: int, body: bytes, ctype: str, extra: dict | None = None):
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "no-referrer")
            for k, v in (extra or {}).items():
                self.send_header(k, v)
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(body)

        def _json(self, obj, code=200):
            self._send(code, json.dumps(obj, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")

        def _handle(self):
            u = urlparse(self.path)
            qs = parse_qs(u.query)
            path = u.path.rstrip("/") or "/"
            if path == "/favicon.ico":
                self._send(204, b"", "text/plain")
                return
            if not self._token_ok(qs):
                self._send(403, "Kein Zugriff – Link aus den Potato-Clips-Einstellungen verwenden.".encode("utf-8"),
                           "text/plain; charset=utf-8")
                return
            tok = ensure_token(ctl.cfg)
            cookie = {"Set-Cookie": f"pc_t={tok}; Path=/; HttpOnly; SameSite=Strict; Max-Age=31536000"}
            if path == "/":
                self._send(200, page_html(ctl).encode("utf-8"), "text/html; charset=utf-8", cookie)
                return
            if path == "/overlay":
                self._send(200, overlay_html(ctl).encode("utf-8"), "text/html; charset=utf-8", cookie)
                return
            if path == "/api/state":
                self._json(ctl.remote_state())
                return
            if path == "/api/now":
                self._json(ctl.remote_now())
                return
            if path.startswith("/api/"):
                cmd = unquote(path[5:])
                folder = (qs.get("folder") or [""])[0]
                if cmd == "random" and folder:
                    cmd = "random:" + folder
                if not ctl.remote_command_ok(cmd):
                    self._json({"ok": False, "error": "unbekannter Befehl"}, 404)
                    return
                ctl.remoteCommand.emit(cmd)
                self._json({"ok": True})
                return
            self._json({"ok": False, "error": "nicht gefunden"}, 404)

        def do_GET(self):
            try:
                self._handle()
            except (BrokenPipeError, ConnectionResetError):
                pass
            except Exception:
                log.exception("Fernbedienung")

        def do_POST(self):
            n = int(self.headers.get("Content-Length") or 0)
            if 0 < n <= 4096:
                self.rfile.read(n)
            self.do_GET()

        do_HEAD = do_GET

    return Handler


# ---------------------------------------------------------------- Webseiten

def _texts() -> dict:
    from . import i18n
    de = i18n.LANG == "de"
    return {
        "all": "Alle" if de else "All", "fav": "★ Favoriten" if de else "★ Favorites",
        "stop": "■ Stopp" if de else "■ Stop", "random": "🎲 Zufall" if de else "🎲 Random",
        "clip": "✂ Clip" if de else "✂ Clip", "voice": "Stimme" if de else "Voice",
        "off": "aus" if de else "off", "on": "AN" if de else "ON", "search": "Suchen…" if de else "Search…",
        "empty": "Noch keine Sounds" if de else "No sounds yet",
        "offline": "Keine Verbindung zum PC" if de else "Can't reach the PC",
        "rec": "● Aufnahme" if de else "● Record",
    }


def page_html(ctl) -> str:
    potato = ctl.cfg.get("ui_theme") == "potato"
    t = json.dumps(_texts(), ensure_ascii=False)
    css_theme = """
  --bg:#FFE94D; --panel:#fff; --text:#111; --muted:#333; --accent:#FF3D8B; --border:3px solid #111;
  --radius:0; --shadow:4px 4px 0 #111; --font:'Comic Sans MS','Comic Neue',system-ui,sans-serif;""" if potato else """
  --bg:#0D0E11; --panel:#16181D; --text:#E9EAEE; --muted:#8B909C; --accent:#F2A93B; --border:1px solid #2C3038;
  --radius:12px; --shadow:none; --font:Inter,system-ui,-apple-system,'Segoe UI',sans-serif;"""
    return """<!doctype html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,maximum-scale=1,user-scalable=no">
<meta name="theme-color" content="#111"><title>Potato Clips</title>
<style>
:root{""" + css_theme + """}
*{box-sizing:border-box;-webkit-tap-highlight-color:transparent}
body{margin:0;background:var(--bg);color:var(--text);font-family:var(--font);padding:12px 12px 90px}
h1{font-size:20px;margin:4px 2px 12px;display:flex;align-items:center;gap:8px}
h1 small{font-size:12px;color:var(--muted);font-weight:400}
.bar{display:flex;gap:8px;overflow-x:auto;padding-bottom:6px;margin-bottom:8px;scrollbar-width:none}
.chip{flex:none;border:var(--border);border-radius:999px;background:var(--panel);color:var(--text);padding:8px 14px;
 font:inherit;font-size:14px;font-weight:700}
.chip.on{background:var(--accent);color:#111}
input{width:100%;padding:11px 14px;border:var(--border);border-radius:var(--radius);background:var(--panel);
 color:var(--text);font:inherit;font-size:16px;margin-bottom:10px}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(140px,1fr));gap:10px}
.tile{position:relative;min-height:84px;border:var(--border);border-radius:var(--radius);background:var(--panel);
 color:var(--text);font:inherit;font-weight:800;font-size:15px;text-align:left;padding:12px 12px 12px 16px;
 box-shadow:var(--shadow);overflow:hidden;word-break:break-word}
.tile:active{transform:translate(2px,2px)}
.tile i{position:absolute;left:0;top:0;bottom:0;width:6px}
.tile.playing{outline:3px solid var(--accent)}
.tile .f{position:absolute;right:8px;top:6px;font-size:13px}
.dock{position:fixed;left:0;right:0;bottom:0;display:flex;gap:8px;padding:10px 12px calc(10px + env(safe-area-inset-bottom));
 background:var(--bg);border-top:var(--border)}
.dock button{flex:1;padding:14px 4px;border:var(--border);border-radius:var(--radius);background:var(--panel);
 color:var(--text);font:inherit;font-weight:800;font-size:15px}
.dock .stop{background:#e5484d;color:#fff}
.dock .on{background:var(--accent);color:#111}
select{padding:10px;border:var(--border);border-radius:var(--radius);background:var(--panel);color:var(--text);
 font:inherit;font-size:15px;max-width:48%}
.row{display:flex;gap:8px;align-items:center;margin-bottom:10px}
.msg{color:var(--muted);text-align:center;padding:30px 0}
</style></head><body>
<h1>🥔 Potato Clips <small id="st"></small></h1>
<input id="q" type="search" autocomplete="off">
<div class="bar" id="folders"></div>
<div class="row"><select id="voice"></select><button class="chip" id="vt"></button></div>
<div class="grid" id="grid"></div>
<div class="msg" id="msg"></div>
<div class="dock"><button class="stop" id="b_stop"></button><button id="b_rand"></button>
<button id="b_clip"></button><button id="b_rec"></button></div>
<script>
const T=""" + t + """;
let S=null,filter="",q="";
const $=id=>document.getElementById(id);
$("q").placeholder=T.search;$("b_stop").textContent=T.stop;$("b_rand").textContent=T.random;
$("b_clip").textContent=T.clip;$("b_rec").textContent=T.rec;
function api(c){return fetch("/api/"+c,{method:"POST",credentials:"same-origin"}).then(()=>setTimeout(load,150)).catch(()=>{})}
function esc(s){return String(s).replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;","\\"":"&quot;","'":"&#39;"}[c]))}
function render(){
 if(!S)return;
 const f=$("folders");let h='<button class="chip'+(filter===""?" on":"")+'" data-f="">'+T.all+'</button>';
 h+='<button class="chip'+(filter==="*fav"?" on":"")+'" data-f="*fav">'+T.fav+'</button>';
 for(const x of S.folders)h+='<button class="chip'+(filter===x?" on":"")+'" data-f="'+esc(x)+'">'+esc(x)+'</button>';
 f.innerHTML=h;
 const list=S.sounds.filter(s=>(filter===""||(filter==="*fav"?s.fav:s.folder===filter))&&
   (!q||s.name.toLowerCase().includes(q)));
 $("grid").innerHTML=list.map(s=>'<button class="tile'+(s.playing?" playing":"")+'" data-id="'+esc(s.id)+'"><i style="background:'+
   esc(s.color||"#888")+'"></i>'+(s.fav?'<span class="f">★</span>':'')+esc(s.name)+'</button>').join("");
 $("msg").textContent=list.length?"":T.empty;
 const v=$("voice");
 if(v.options.length!==S.presets.length){v.innerHTML=S.presets.map(p=>'<option value="'+esc(p.key)+'">'+esc(p.name)+'</option>').join("")}
 v.value=S.voice.preset;
 $("vt").textContent=T.voice+": "+(S.voice.enabled?T.on:T.off);$("vt").className="chip"+(S.voice.enabled?" on":"");
 $("b_rec").className=S.recording?"on":"";
 $("st").textContent="";
}
function load(){fetch("/api/state",{credentials:"same-origin"}).then(r=>r.json()).then(j=>{S=j;render()})
 .catch(()=>{$("st").textContent=T.offline})}
document.addEventListener("click",e=>{
 const t=e.target.closest("[data-id]");if(t){api("play/"+encodeURIComponent(t.dataset.id));return}
 const f=e.target.closest("[data-f]");if(f){filter=f.dataset.f;render();return}
});
$("q").addEventListener("input",e=>{q=e.target.value.toLowerCase().trim();render()});
$("b_stop").onclick=()=>api("stop");$("b_clip").onclick=()=>api("clip");$("b_rec").onclick=()=>api("record");
$("b_rand").onclick=()=>api("random"+(filter&&filter!=="*fav"?"?folder="+encodeURIComponent(filter):(filter==="*fav"?"?folder=*fav":"")));
$("vt").onclick=()=>api("voice/toggle");
$("voice").onchange=e=>api("voice/set/"+encodeURIComponent(e.target.value));
if(location.search.includes("t="))history.replaceState(null,"","/");
load();setInterval(load,1500);
</script></body></html>"""


def overlay_html(ctl) -> str:
    """Browser-Quelle fuer OBS: zeigt laufende Sounds, Stimmeffekt und Aufnahme (transparenter Hintergrund)."""
    potato = ctl.cfg.get("ui_theme") == "potato"
    box = ("background:#FFE94D;color:#111;border:3px solid #111;box-shadow:4px 4px 0 #111;border-radius:0;"
           "font-family:'Comic Neue','Comic Sans MS',sans-serif") if potato else \
          ("background:rgba(13,14,17,.86);color:#E9EAEE;border:1px solid #2C3038;border-radius:10px;"
           "font-family:Inter,'Segoe UI',sans-serif")
    acc = "#FF3D8B" if potato else "#F2A93B"
    return """<!doctype html><html><head><meta charset="utf-8"><style>
html,body{margin:0;background:transparent;overflow:hidden}
#w{display:flex;flex-direction:column;gap:8px;padding:12px;align-items:flex-start}
.i{""" + box + """;padding:8px 14px;font-size:22px;font-weight:800;display:flex;gap:10px;align-items:center;
 min-width:220px;position:relative;overflow:hidden}
.p{position:absolute;left:0;bottom:0;height:4px;background:""" + acc + """}
.rec{color:#e5484d}
</style></head><body><div id="w"></div><script>
function esc(s){return String(s).replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;","\\"":"&quot;","'":"&#39;"}[c]))}
function tick(){fetch("/api/now",{credentials:"same-origin"}).then(r=>r.json()).then(j=>{
 let h="";if(j.recording)h+='<div class="i rec">● REC</div>';
 if(j.voice)h+='<div class="i">🎭 '+esc(j.voice)+'</div>';
 for(const s of j.playing)h+='<div class="i">▶ '+esc(s.name)+'<div class="p" style="width:'+Math.round(s.progress*100)+'%"></div></div>';
 document.getElementById("w").innerHTML=h}).catch(()=>{})}
setInterval(tick,250);tick();
</script></body></html>"""
