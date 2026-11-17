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
                apps = (qs.get("apps") or [""])[0]
                if cmd == "random" and folder:
                    cmd = "random:" + folder
                if cmd in ("clip", "record") and apps:
                    cmd = f"{cmd}:{apps}"
                if cmd == "say":
                    body = {}
                    if self._body:
                        try:
                            body = json.loads(self._body.decode("utf-8"))
                        except ValueError:
                            body = {}
                    if not isinstance(body, dict):
                        body = {}
                    for k in ("text", "voice", "fx"):
                        if k not in body and qs.get(k):
                            body[k] = qs[k][0]
                    if isinstance(body.get("fx"), str):
                        body["fx"] = body["fx"] in ("1", "true", "yes", "on")
                    cmd = "say:" + json.dumps({k: body.get(k) for k in ("text", "voice", "fx")}, ensure_ascii=False)
                if not ctl.remote_command_ok(cmd):
                    self._json({"ok": False, "error": "unbekannter Befehl"}, 404)
                    return
                ctl.remoteCommand.emit(cmd)
                self._json({"ok": True})
                return
            self._json({"ok": False, "error": "nicht gefunden"}, 404)

        _body = b""

        def do_GET(self):
            try:
                self._handle()
            except (BrokenPipeError, ConnectionResetError):
                pass
            except Exception:
                log.exception("Fernbedienung")

        def do_POST(self):
            try:
                n = int(self.headers.get("Content-Length") or 0)
            except ValueError:
                n = 0
            if n > 8192:
                self._json({"ok": False, "error": "zu gross"}, 413)
                return
            self._body = self.rfile.read(n) if n > 0 else b""
            self.do_GET()

        do_HEAD = do_GET

    return Handler


# ---------------------------------------------------------------- Webseiten

def _texts() -> dict:
    from . import i18n
    de = i18n.LANG == "de"
    D = {
        "sounds": ("Sounds", "Sounds"), "clip": ("Clip", "Clip"), "voice": ("Stimme", "Voice"),
        "say": ("Vorlesen", "Speak"), "all": ("Alle", "All"), "fav": ("★ Favoriten", "★ Favorites"),
        "stop": ("Stopp", "Stop"), "random": ("🎲 Zufall", "🎲 Random"), "search": ("Sound suchen…", "Search sounds…"),
        "empty": ("Noch keine Sounds – am PC ins Soundboard ziehen", "No sounds yet – drop some into the soundboard on the PC"),
        "offline": ("Keine Verbindung zum PC", "Can't reach the PC"), "online": ("verbunden", "connected"),
        "clip_all": ("✂ Clip – alles", "✂ Clip – everything"),
        "clip_hint": ("Speichert die letzten Sekunden.", "Saves the last few seconds."),
        "clip_app": ("Nur eine App clippen", "Clip just one app"),
        "rec": ("Aufnahme", "Recording"), "rec_which": ("Was soll aufgenommen werden?", "What should be recorded?"),
        "rec_all": ("Alles", "Everything"), "rec_start": ("● Aufnahme starten", "● Start recording"),
        "rec_stop": ("■ Aufnahme stoppen", "■ Stop recording"), "rec_running": ("Läuft", "Recording"),
        "on": ("An", "On"), "off": ("Aus", "Off"), "voice_fx": ("Stimmeffekt", "Voice effect"),
        "strength": ("Stärke", "Strength"), "say_ph": ("Was soll vorgelesen werden?", "What should be read out?"),
        "say_btn": ("🗣 Vorlesen", "🗣 Speak"), "say_fx": ("Mit Stimmeffekt", "With voice effect"),
        "say_hint": ("Du und deine Freunde in Discord hören es.", "You and your friends in Discord will hear it."),
        "say_voice": ("Windows-Stimme", "Windows voice"), "sent": ("Gesendet", "Sent"),
        "look": ("Look", "Look"), "pro": ("Profi", "Pro"), "potato": ("Potato", "Potato"),
    }
    return {k: v[0] if de else v[1] for k, v in D.items()}


PAGE = r"""<!doctype html><html data-theme="__THEME__" lang="__LANG__"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<meta name="theme-color" content="#0D0E11"><title>Potato Clips</title>
<style>
:root[data-theme=pro]{--bg:#0D0E11;--panel:#16181D;--panel2:#1D2027;--text:#E9EAEE;--muted:#8B909C;--acc:#F2A93B;--acc-t:#111;
 --line:1px solid #262A32;--r:14px;--sh:none;--font:Inter,system-ui,-apple-system,'Segoe UI',Roboto,sans-serif;--red:#E5484D;--tf:none}
:root[data-theme=potato]{--bg:#FFE94D;--panel:#fff;--panel2:#fff;--text:#111;--muted:#333;--acc:#FF3D8B;--acc-t:#111;
 --line:3px solid #111;--r:0;--sh:4px 4px 0 #111;--font:'Comic Neue','Comic Sans MS',system-ui,sans-serif;--red:#FF2E2E;--tf:uppercase}
*{box-sizing:border-box;-webkit-tap-highlight-color:transparent}
html,body{margin:0;background:var(--bg);color:var(--text);font-family:var(--font)}
body{padding:calc(64px + env(safe-area-inset-top)) 14px calc(86px + env(safe-area-inset-bottom))}
button,input,select,textarea{font:inherit;color:inherit}
header{position:fixed;top:0;left:0;right:0;z-index:5;display:flex;align-items:center;gap:10px;
 padding:calc(10px + env(safe-area-inset-top)) 14px 10px;background:var(--bg);border-bottom:var(--line)}
.logo{font-weight:800;font-size:18px;display:flex;align-items:center;gap:8px;flex:1;text-transform:var(--tf)}
.logo i{font-style:normal;width:30px;height:30px;display:grid;place-items:center;background:var(--acc);border-radius:9px;
 border:var(--line);font-size:16px}
.pill{font-size:12px;color:var(--muted);display:flex;align-items:center;gap:6px}
.pill b{width:8px;height:8px;border-radius:50%;background:#3DD68C;display:inline-block}
.pill.off b{background:var(--red)} .pill.rec{color:var(--red);font-weight:800}
.pill.rec b{background:var(--red);animation:bl 1s infinite}@keyframes bl{50%{opacity:.2}}
.btn{border:var(--line);border-radius:var(--r);background:var(--panel);padding:10px 14px;font-weight:700;box-shadow:var(--sh);
 cursor:pointer}
.btn:active{transform:translate(1px,1px)} .btn.acc{background:var(--acc);color:var(--acc-t);border-color:transparent}
:root[data-theme=potato] .btn.acc{border:var(--line)}
.btn.red{background:var(--red);color:#fff;border-color:transparent} .btn.big{width:100%;padding:16px;font-size:17px}
.btn.sm{padding:7px 11px;font-size:13px}
nav{position:fixed;left:0;right:0;bottom:0;z-index:5;display:grid;grid-template-columns:repeat(4,1fr);background:var(--panel);
 border-top:var(--line);padding:6px 6px calc(6px + env(safe-area-inset-bottom))}
nav button{background:none;border:0;padding:8px 2px;border-radius:10px;color:var(--muted);font-size:12px;font-weight:700;
 display:flex;flex-direction:column;align-items:center;gap:3px;text-transform:var(--tf)}
nav button span{font-size:20px;line-height:1} nav button em{font-style:normal} nav button.on{color:var(--text);background:var(--panel2)}
:root[data-theme=potato] nav button.on{background:var(--acc)}
section{display:none} section.on{display:block}
h2{font-size:13px;color:var(--muted);text-transform:uppercase;letter-spacing:.06em;margin:20px 2px 10px}
.card{background:var(--panel);border:var(--line);border-radius:var(--r);padding:14px;box-shadow:var(--sh);margin-bottom:12px}
input[type=search],textarea,select{width:100%;padding:12px 14px;border:var(--line);border-radius:var(--r);background:var(--panel);
 font-size:16px;outline:none}
textarea{min-height:110px;resize:vertical}
.chips{display:flex;gap:8px;overflow-x:auto;padding:10px 0 4px;scrollbar-width:none} .chips::-webkit-scrollbar{display:none}
.chips.wrap{flex-wrap:wrap;overflow:visible}
.chip{flex:none;border:var(--line);border-radius:999px;background:var(--panel);padding:8px 14px;font-size:14px;font-weight:700}
:root[data-theme=potato] .chip{border-radius:0}
.chip.on{background:var(--acc);color:var(--acc-t);border-color:transparent}
:root[data-theme=potato] .chip.on{border:var(--line)}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(150px,1fr));gap:10px;margin-top:8px}
.tile{position:relative;min-height:78px;border:var(--line);border-radius:var(--r);background:var(--panel);font-weight:700;
 font-size:15px;text-align:left;padding:12px 12px 12px 18px;box-shadow:var(--sh);overflow:hidden;word-break:break-word}
.tile:active{transform:translate(2px,2px)} .tile i{position:absolute;left:0;top:0;bottom:0;width:6px}
.tile.play{outline:2px solid var(--acc);outline-offset:-2px} .tile .f{position:absolute;right:9px;top:7px;font-size:12px;color:var(--acc)}
.tile .fo{display:block;font-size:11px;color:var(--muted);font-weight:500;margin-top:4px}
.row{display:flex;gap:10px;align-items:center} .row>*{flex:1}
.muted{color:var(--muted);font-size:13px}
.sw{display:flex;align-items:center;justify-content:space-between;gap:12px;font-weight:700}
.tg{width:54px;height:30px;border-radius:999px;background:#3A3E47;border:0;position:relative;flex:none}
.tg::after{content:"";position:absolute;top:3px;left:3px;width:24px;height:24px;border-radius:50%;background:#fff;transition:.15s}
.tg.on{background:var(--acc)} .tg.on::after{left:27px}
:root[data-theme=potato] .tg{border:3px solid #111;border-radius:0;background:#fff} :root[data-theme=potato] .tg::after{background:#111;border-radius:0;top:2px;left:2px}
:root[data-theme=potato] .tg.on{background:var(--acc)} :root[data-theme=potato] .tg.on::after{left:25px}
input[type=range]{width:100%;accent-color:var(--acc)}
.presets{display:grid;grid-template-columns:repeat(auto-fill,minmax(130px,1fr));gap:8px;margin-top:4px}
.preset{border:var(--line);border-radius:var(--r);background:var(--panel);padding:12px 8px;font-size:14px;font-weight:700;
 box-shadow:var(--sh);text-align:center}
.preset.on{background:var(--acc);color:var(--acc-t);border-color:transparent} :root[data-theme=potato] .preset.on{border:var(--line)}
.recbox{display:flex;align-items:center;justify-content:space-between;margin-bottom:12px}
.recbox .t{font-size:30px;font-weight:800;font-variant-numeric:tabular-nums;color:var(--red)}
.toast{position:fixed;left:50%;bottom:calc(92px + env(safe-area-inset-bottom));transform:translateX(-50%);z-index:9;
 background:var(--text);color:var(--bg);padding:9px 16px;border-radius:999px;font-size:14px;font-weight:700;opacity:0;
 transition:.2s;pointer-events:none} .toast.on{opacity:1}
.msg{color:var(--muted);text-align:center;padding:36px 10px}
</style></head><body>
<header><div class="logo"><i>🥔</i>Potato Clips</div><span class="pill" id="st"><b></b><span></span></span>
<button class="btn sm" id="b_look" title="Look"></button><button class="btn red sm" id="b_stop"></button></header>

<section id="t_sounds" class="on">
<input id="q" type="search" autocomplete="off">
<div class="chips" id="folders"></div>
<div class="row" style="margin-top:6px"><button class="btn" id="b_rand"></button></div>
<div class="grid" id="grid"></div><div class="msg" id="msg"></div>
</section>

<section id="t_clip">
<button class="btn acc big" id="b_clip" style="margin-top:6px"></button>
<p class="muted" id="clip_hint"></p>
<h2 id="h_clip_app"></h2><div class="chips wrap" id="clip_apps"></div>
<h2 id="h_rec"></h2>
<div class="card"><div class="recbox" id="recbox" style="display:none"><span class="muted" id="rec_what"></span><span class="t" id="rec_t">0:00</span></div>
<div class="muted" id="rec_which"></div><div class="chips wrap" id="rec_apps"></div>
<button class="btn big" id="b_rec" style="margin-top:10px"></button></div>
</section>

<section id="t_voice">
<div class="card"><div class="sw"><span id="l_vfx"></span><button class="tg" id="vt"></button></div>
<div style="margin-top:14px"><div class="muted" id="l_str"></div><input type="range" id="amt" min="0" max="100"></div></div>
<div class="presets" id="presets"></div>
</section>

<section id="t_say">
<div class="card"><textarea id="say_t" maxlength="300"></textarea>
<div class="row" style="margin-top:10px"><select id="say_v"></select></div>
<div class="sw" style="margin-top:12px"><span id="l_sfx"></span><button class="tg" id="say_fx"></button></div>
<button class="btn acc big" id="b_say" style="margin-top:14px"></button>
<p class="muted" id="say_hint"></p></div>
</section>

<nav id="nav"><button data-t="sounds" class="on"><span>🔊</span><em></em></button><button data-t="clip"><span>✂️</span><em></em></button>
<button data-t="voice"><span>🎭</span><em></em></button><button data-t="say"><span>🗣</span><em></em></button></nav>
<div class="toast" id="toast"></div>
<script>
const T=__T__;
let S=null,filter="",q="",recSel=new Set(),sayFx=false,lastOk=0,clockOff=0;
const $=id=>document.getElementById(id);
const esc=s=>String(s).replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
function store(k,v){try{localStorage.setItem(k,v)}catch(e){}} function load_(k){try{return localStorage.getItem(k)}catch(e){return null}}
// Texte
$("q").placeholder=T.search;$("b_stop").textContent="■ "+T.stop;$("b_rand").textContent=T.random;$("b_clip").textContent=T.clip_all;
$("clip_hint").textContent=T.clip_hint;$("h_clip_app").textContent=T.clip_app;$("h_rec").textContent=T.rec;
$("rec_which").textContent=T.rec_which;$("l_vfx").textContent=T.voice_fx;$("l_str").textContent=T.strength;
$("say_t").placeholder=T.say_ph;$("l_sfx").textContent=T.say_fx;$("b_say").textContent=T.say_btn;$("say_hint").textContent=T.say_hint;
const navNames={sounds:T.sounds,clip:T.clip,voice:T.voice,say:T.say};
document.querySelectorAll("#nav button").forEach(b=>b.querySelector("em").textContent=navNames[b.dataset.t]);
// Look
function setLook(l){document.documentElement.dataset.theme=l;$("b_look").textContent=l==="pro"?"🥔":"🕶";
 $("b_look").title=T.look+": "+(l==="pro"?T.potato:T.pro)}
setLook(load_("pc_look")||document.documentElement.dataset.theme);
$("b_look").onclick=()=>{const l=document.documentElement.dataset.theme==="pro"?"potato":"pro";setLook(l);store("pc_look",l)};
// Tabs
function tab(t){document.querySelectorAll("section").forEach(s=>s.classList.toggle("on",s.id==="t_"+t));
 document.querySelectorAll("#nav button").forEach(b=>b.classList.toggle("on",b.dataset.t===t));store("pc_tab",t);window.scrollTo(0,0)}
$("nav").onclick=e=>{const b=e.target.closest("button");if(b)tab(b.dataset.t)};
tab(load_("pc_tab")||"sounds");
// Aktionen
function toast(m){const t=$("toast");t.textContent=m;t.classList.add("on");clearTimeout(t._h);t._h=setTimeout(()=>t.classList.remove("on"),1400)}
function api(c,body){return fetch("/api/"+c,{method:"POST",credentials:"same-origin",headers:body?{"Content-Type":"application/json"}:{},
 body:body?JSON.stringify(body):undefined}).then(r=>{if(!r.ok)throw 0;setTimeout(load,200);return r}).catch(()=>toast(T.offline))}
$("b_stop").onclick=()=>api("stop");
$("b_rand").onclick=()=>api("random"+(filter?"?folder="+encodeURIComponent(filter):""));
$("b_clip").onclick=()=>api("clip").then(()=>toast("✂ "+T.sent));
$("vt").onclick=()=>api("voice/toggle");
$("amt").onchange=e=>api("voice/amount/"+e.target.value);
$("say_fx").onclick=()=>{sayFx=!sayFx;$("say_fx").classList.toggle("on",sayFx)};
$("b_say").onclick=()=>{const t=$("say_t").value.trim();if(!t){$("say_t").focus();return}
 api("say",{text:t,voice:$("say_v").value,fx:sayFx}).then(()=>toast("🗣 "+T.sent));store("pc_voice",$("say_v").value)};
$("b_rec").onclick=()=>{if(S&&S.rec.active)api("record/stop");else api("record"+(recSel.size?"?apps="+encodeURIComponent([...recSel].join(",")):""))};
document.addEventListener("click",e=>{
 const t=e.target.closest("[data-id]");if(t){api("play/"+encodeURIComponent(t.dataset.id));return}
 const f=e.target.closest("[data-f]");if(f){filter=f.dataset.f;render();return}
 const c=e.target.closest("[data-clip]");if(c){api("clip?apps="+encodeURIComponent(c.dataset.clip)).then(()=>toast("✂ "+c.textContent));return}
 const r=e.target.closest("[data-rec]");if(r&&!(S&&S.rec.active)){const k=r.dataset.rec;if(k==="*")recSel.clear();else recSel.has(k)?recSel.delete(k):recSel.add(k);render();return}
 const p=e.target.closest("[data-p]");if(p){api("voice/set/"+encodeURIComponent(p.dataset.p));return}
});
$("q").addEventListener("input",e=>{q=e.target.value.toLowerCase().trim();render()});
function render(){
 if(!S)return;
 // Sounds
 let h='<button class="chip'+(filter===""?" on":"")+'" data-f="">'+esc(T.all)+'</button>';
 if(S.sounds.some(s=>s.fav))h+='<button class="chip'+(filter==="*fav"?" on":"")+'" data-f="*fav">'+esc(T.fav)+'</button>';
 for(const x of S.folders)h+='<button class="chip'+(filter===x?" on":"")+'" data-f="'+esc(x)+'">'+esc(x)+'</button>';
 $("folders").innerHTML=h;
 const list=S.sounds.filter(s=>(filter===""||(filter==="*fav"?s.fav:s.folder===filter))&&(!q||s.name.toLowerCase().includes(q)));
 $("grid").innerHTML=list.map(s=>'<button class="tile'+(s.playing?" play":"")+'" data-id="'+esc(s.id)+'"><i style="background:'+
  esc(s.color||"#888")+'"></i>'+(s.fav?'<span class="f">★</span>':'')+esc(s.name)+(s.folder&&filter===""?'<span class="fo">'+esc(s.folder)+'</span>':'')+'</button>').join("");
 $("msg").textContent=list.length?"":T.empty;
 // Clip & Aufnahme
 $("clip_apps").innerHTML=S.apps.map(a=>'<button class="chip" data-clip="'+esc(a.key)+'">'+esc(a.label)+'</button>').join("");
 const ra=S.rec.active,keys=new Set(ra?S.rec.keys:[...recSel]);
 $("rec_apps").innerHTML='<button class="chip'+(keys.size===0?" on":"")+'" data-rec="*">'+esc(T.rec_all)+'</button>'+
  S.apps.map(a=>'<button class="chip'+(keys.has(a.key)?" on":"")+'" data-rec="'+esc(a.key)+'">'+esc(a.label)+'</button>').join("");
 $("rec_apps").style.opacity=ra?.55:1;
 $("b_rec").textContent=ra?T.rec_stop:T.rec_start;$("b_rec").className="btn big "+(ra?"":"red");
 $("recbox").style.display=ra?"flex":"none";
 $("rec_what").textContent=T.rec_running+": "+(S.rec.keys.length?S.rec.keys.map(k=>(S.apps.find(a=>a.key===k)||{label:k}).label).join(", "):T.rec_all);
 // Stimme
 $("vt").classList.toggle("on",S.voice.enabled);
 if(document.activeElement!==$("amt"))$("amt").value=S.amount;
 $("presets").innerHTML=S.presets.map(p=>'<button class="preset'+(p.key===S.voice.preset?" on":"")+'" data-p="'+esc(p.key)+'">'+esc(p.name)+'</button>').join("");
 // Vorlesen
 const sv=$("say_v");
 if(sv.options.length!==S.tts.length+1){const keep=sv.value||load_("pc_voice")||"";
  sv.innerHTML='<option value="">'+esc(T.say_voice)+'</option>'+S.tts.map(v=>'<option value="'+esc(v.name)+'">'+esc(v.label)+'</option>').join("");sv.value=keep}
 // Status
 const st=$("st");st.className="pill"+(ra?" rec":"");st.querySelector("span").textContent=ra?"REC":T.online;
}
function tick(){
 if(S&&S.rec.active){const sec=Math.max(0,Math.floor(Date.now()/1000+clockOff-S.rec.since));$("rec_t").textContent=Math.floor(sec/60)+":"+String(sec%60).padStart(2,"0")}
 if(Date.now()-lastOk>5000){const st=$("st");st.className="pill off";st.querySelector("span").textContent=T.offline}
}
function load(){fetch("/api/state",{credentials:"same-origin"}).then(r=>{if(!r.ok)throw 0;return r.json()}).then(j=>{
 S=j;lastOk=Date.now();clockOff=j.now-Date.now()/1000;if(!S.sounds.some(s=>s.fav)&&filter==="*fav")filter="";render()}).catch(()=>{})}
if(location.search.includes("t="))history.replaceState(null,"","/");
load();setInterval(load,1500);setInterval(tick,500);
</script></body></html>"""


def page_html(ctl) -> str:
    from . import i18n
    theme = "potato" if ctl.cfg.get("ui_theme") == "potato" else "pro"
    return (PAGE.replace("__THEME__", theme).replace("__LANG__", i18n.LANG)
            .replace("__T__", json.dumps(_texts(), ensure_ascii=False)))


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
