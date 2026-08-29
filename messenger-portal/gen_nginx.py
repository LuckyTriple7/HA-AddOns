#!/usr/bin/env python3
"""Generates the nginx reverse-proxy config from /data/options.json at startup."""
import json
import os
import re
import subprocess

import addon_hosts

CONFIG_PATH = '/data/options.json'
# Getrennte Listener: der Ingress-Port ist absichtlich NICHT unter "ports:"
# gemappt und damit nur vom Supervisor erreichbar. Nur dort darf der Header
# X-Ingress-Path geglaubt werden - er kommt sonst vom Client und waere als
# Erkennungsmerkmal fuer "HA hat schon authentifiziert" faelschbar.
INGRESS_PORT = 8099
LAN_PORT = 17770
NGINX_CONF   = '/etc/nginx/http.d/messenger-portal.conf'

# Draggable back-to-portal button injected into every proxied page.
# IMPORTANT: no single quotes allowed (nginx sub_filter uses them as delimiters).
BACK_BTN = (
    '<style>@media(max-width:600px){#mp-back{display:none!important}}</style>'
    '<div id="mp-back" style="position:fixed;bottom:18px;right:18px;'
    'z-index:2147483647;background:linear-gradient(135deg,#25D366,#2AABEE);'
    'border-radius:12px;padding:10px 16px;cursor:grab;user-select:none;'
    'touch-action:none;box-shadow:0 4px 20px rgba(0,0,0,.45);'
    'font-family:system-ui,-apple-system,sans-serif">'
    '<span style="color:#fff;font-size:13px;font-weight:600;'
    'display:flex;align-items:center;gap:6px;pointer-events:none">'
    '<svg width="14" height="14" fill="#fff" viewBox="0 0 24 24">'
    '<path d="M20 11H7.83l5.59-5.59L12 4l-8 8 8 8 1.41-1.41L7.83 13H20v-2z">'
    '</path></svg>Portal</span></div>'
    '<script>(function(){'
    'var b=document.getElementById("mp-back");'
    'var dragged=false,sx,sy,sr,sb;'
    'try{var p=JSON.parse(localStorage.getItem("mp-bp")||"null");'
    'if(p){b.style.right=p.r;b.style.bottom=p.b;}}catch(e){}'
    'function gs(el,prop){return parseInt(el.style[prop])||18;}'
    'b.addEventListener("mousedown",function(e){'
    'dragged=false;sx=e.clientX;sy=e.clientY;sr=gs(b,"right");sb=gs(b,"bottom");'
    'b.style.cursor="grabbing";e.preventDefault();});'
    'document.addEventListener("mousemove",function(e){'
    'if(sx===undefined)return;'
    'var dx=sx-e.clientX,dy=sy-e.clientY;'
    'if(Math.abs(dx)+Math.abs(dy)>5)dragged=true;'
    'if(dragged){b.style.right=Math.max(0,sr+dx)+"px";b.style.bottom=Math.max(0,sb+dy)+"px";}});'
    'document.addEventListener("mouseup",function(){'
    'if(sx===undefined)return;b.style.cursor="grab";'
    'if(dragged)try{localStorage.setItem("mp-bp",JSON.stringify({r:b.style.right,b:b.style.bottom}));}catch(e){}'
    'sx=undefined;});'
    'b.addEventListener("click",function(e){'
    'if(dragged){e.preventDefault();}else{window.location.href="../../";}});'
    'b.addEventListener("touchstart",function(e){'
    'var t=e.touches[0];dragged=false;sx=t.clientX;sy=t.clientY;'
    'sr=gs(b,"right");sb=gs(b,"bottom");},{passive:true});'
    'document.addEventListener("touchmove",function(e){'
    'if(sx===undefined)return;var t=e.touches[0],dx=sx-t.clientX,dy=sy-t.clientY;'
    'if(Math.abs(dx)+Math.abs(dy)>5)dragged=true;'
    'if(dragged){b.style.right=Math.max(0,sr+dx)+"px";b.style.bottom=Math.max(0,sb+dy)+"px";e.preventDefault();}}'
    ',{passive:false});'
    'document.addEventListener("touchend",function(){'
    'if(sx===undefined)return;'
    'if(dragged)try{localStorage.setItem("mp-bp",JSON.stringify({r:b.style.right,b:b.style.bottom}));}catch(e){}'
    'else window.location.href="../../";sx=undefined;});'
    'document.addEventListener("keydown",function(e){'
    'if(e.altKey&&e.shiftKey&&(e.key==="h"||e.key==="H")){'
    'e.preventDefault();window.location.href="../../";}});'
    '})();</script></body>'
)


def detect_gateway() -> str:
    try:
        out = subprocess.check_output(['ip', 'route', 'show', 'default'],
                                      text=True, stderr=subprocess.DEVNULL)
        for token, value in zip(out.split(), out.split()[1:]):
            if token == 'via':
                return value
    except Exception:
        pass
    return '172.30.32.2'


def var_name(slug: str) -> str:
    """nginx-Variablenname aus einem Slug - nur [a-z0-9_] ist dort erlaubt."""
    return 'mp_' + re.sub(r'[^a-z0-9_]', '_', slug.lower())


def proxy_block(slug: str, name: str, host: str, port: int) -> str:
    prefix = f'/proxy/{slug}/'
    var = var_name(slug)
    return f"""
    # ── {slug} ──────────────────────────────────────────
    location {prefix} {{
        auth_request /auth-check;
        error_page 401 = @login_redirect;
        error_page 502 503 504 = @offline_{slug};

        # Ziel als Variable + resolver: so loest nginx den Namen erst beim
        # Request auf. Sonst verweigert nginx den Start, solange das Add-on
        # aus ist (alle Messenger stehen auf boot: manual) - mit Variable
        # landet der Fall stattdessen wie gewohnt auf @offline_{slug}.
        set                     ${var} "{host}:{port}";
        rewrite                 ^{prefix}(.*)$ /$1 break;
        proxy_pass              http://${var};
        proxy_http_version      1.1;
        proxy_set_header        Host              $http_host;
        proxy_set_header        X-Real-IP         $remote_addr;
        proxy_set_header        X-Forwarded-For   $proxy_add_x_forwarded_for;
        proxy_set_header        X-Forwarded-Proto $scheme;
        proxy_set_header        Accept-Encoding   "";

        # WebSocket
        proxy_set_header        Upgrade    $http_upgrade;
        proxy_set_header        Connection $connection_upgrade;
        proxy_read_timeout      86400s;
        proxy_send_timeout      86400s;

        # Rewrite absolute paths in HTML/JS responses
        sub_filter_once  off;
        # text/html filtert sub_filter immer, es hier zu nennen erzeugt nur
        # die Warnung 'duplicate MIME type "text/html"' bei jedem nginx-Start.
        sub_filter_types text/javascript application/javascript application/json;
        sub_filter 'href="/'   'href="{prefix}';
        sub_filter 'src="/'    'src="{prefix}';
        sub_filter 'action="/' 'action="{prefix}';
        sub_filter "href='/"   "href='{prefix}";
        sub_filter "src='/"    "src='{prefix}";
        sub_filter 'fetch("/'  'fetch("{prefix}';
        sub_filter "fetch('/"  "fetch('{prefix}";
        sub_filter '"url":"/'  '"url":"{prefix}';
        sub_filter 'url: "/'   'url: "{prefix}';
        sub_filter "url: '/"   "url: '{prefix}";

        # Inject back-to-portal button
        sub_filter '</body>' '{BACK_BTN}';
    }}

    location @offline_{slug} {{
        rewrite            ^ /proxy-offline break;
        proxy_pass         http://127.0.0.1:5000;
        proxy_set_header   X-Messenger-Name  "{name}";
        proxy_set_header   X-Messenger-Icon  "{slug}";
        proxy_set_header   Cookie            $http_cookie;
        proxy_set_header   Host              $host;
    }}
"""


def main():
    try:
        with open(CONFIG_PATH) as f:
            config = json.load(f)
    except Exception as e:
        print(f'[WARN] Could not read {CONFIG_PATH}: {e} – using defaults')
        config = {}

    configured = config.get('internal_host', '').strip()
    if configured:
        fallback = configured
        print(f'[INFO] internal_host aus Config: {fallback}')
    else:
        fallback = detect_gateway()
        print(f'[INFO] internal_host auto-erkannt (Gateway): {fallback}')

    # Bevorzugt wird der Container-Hostname aus der Supervisor-API: der bleibt
    # auch dann erreichbar, wenn das Add-on seinen Host-Port nicht mehr
    # veroeffentlicht. Der HA-Host bleibt Notnagel.
    prefix = addon_hosts.lookup()
    if prefix:
        print(f'[INFO] Add-on-Praefix "{prefix}" - Messenger werden ueber ihren '
              f'Container-Namen angesprochen')
    else:
        print('[WARN] Kein Add-on-Praefix vom Supervisor - benutze den HA-Host')

    messengers = [m for m in config.get('messengers', []) if m.get('enabled', True)]
    targets = [
        (m['icon'].lower(), m['name'],
         addon_hosts.resolve_host(m['icon'], fallback, configured), m['port'])
        for m in messengers
        if m.get('icon') and m.get('port')
    ]

    proxy_blocks = ''.join(proxy_block(*t) for t in targets)

    resolvers = addon_hosts.nameservers()
    print(f'[INFO] nginx-resolver: {resolvers}')

    conf = f"""# Auto-generated by gen_nginx.py – do not edit manually

map $http_upgrade $connection_upgrade {{
    default  upgrade;
    ''       close;
}}
{server_block(INGRESS_PORT, '$http_x_ingress_path', proxy_blocks, resolvers)}
{server_block(LAN_PORT, '""', proxy_blocks, resolvers)}
"""

    os.makedirs(os.path.dirname(NGINX_CONF), exist_ok=True)
    with open(NGINX_CONF, 'w', encoding='utf-8') as f:
        f.write(conf)
    print(f'[INFO] nginx config written → {NGINX_CONF}')
    print(f'[INFO] Ingress-Listener auf {INGRESS_PORT}, LAN-Listener auf {LAN_PORT}')
    for slug, _name, thost, tport in targets:
        print(f'[INFO]   /proxy/{slug}/ -> http://{thost}:{tport}/')


def server_block(listen: int, ingress: str, proxy_blocks: str, resolvers: str) -> str:
    """Ein server-Block. `ingress` ist der Ausdruck, den nginx als
    X-Ingress-Path weiterreicht: auf dem Ingress-Port die Kopfzeile des
    Supervisors, auf dem LAN-Port die leere Zeichenkette."""
    return f"""
server {{
    listen {listen};

    # Namen werden zur Laufzeit aufgeloest (siehe proxy_block)
    resolver {resolvers} valid=30s ipv6=off;

    # Default (1m) is too small for pasted screenshots/media uploads
    # forwarded to proxied messenger add-ons (e.g. WhatsApp send-media).
    client_max_body_size 64m;

    # ── Internal session check ────────────────────────────
    location = /auth-check {{
        internal;
        proxy_pass              http://127.0.0.1:5000/auth-check;
        proxy_pass_request_body off;
        proxy_set_header        Content-Length  "";
        proxy_set_header        Cookie          $http_cookie;
        proxy_set_header        X-Real-IP       $remote_addr;
        proxy_set_header        X-Ingress-Path  {ingress};
    }}

    location @login_redirect {{
        return 302 /login;
    }}

    # ── Suppress logs for polling endpoints ──────────────
    location = /health {{
        access_log off;
        proxy_pass         http://127.0.0.1:5000;
        proxy_set_header   Host $host;
    }}

    location = /status {{
        access_log off;
        proxy_pass         http://127.0.0.1:5000;
        proxy_set_header   Host           $host;
        proxy_set_header   Cookie         $http_cookie;
        proxy_set_header   X-Ingress-Path {ingress};
    }}

    # ── Flask app (login, portal, static) ────────────────
    location / {{
        proxy_pass         http://127.0.0.1:5000;
        proxy_set_header   Host              $host;
        proxy_set_header   X-Real-IP         $remote_addr;
        proxy_set_header   X-Forwarded-For   $proxy_add_x_forwarded_for;
        proxy_set_header   X-Forwarded-Proto $scheme;
        proxy_set_header   X-Ingress-Path    {ingress};
    }}
{proxy_blocks}
}}
"""


if __name__ == '__main__':
    main()
