#!/usr/bin/env python3
"""Generates the nginx reverse-proxy config from /data/options.json at startup."""
import json
import os
import subprocess

CONFIG_PATH = '/data/options.json'
NGINX_CONF   = '/etc/nginx/http.d/messenger-portal.conf'

# Draggable back-to-portal button injected into every proxied page.
# IMPORTANT: no single quotes allowed (nginx sub_filter uses them as delimiters).
BACK_BTN = (
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
    'if(dragged){e.preventDefault();}else{window.location.href="/";}});'
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
    'else window.location.href="/";sx=undefined;});'
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


def proxy_block(slug: str, name: str, host: str, port: int) -> str:
    prefix = f'/proxy/{slug}/'
    return f"""
    # ── {slug} ──────────────────────────────────────────
    location {prefix} {{
        auth_request /auth-check;
        error_page 401 = @login_redirect;
        error_page 502 503 504 = @offline_{slug};

        proxy_pass              http://{host}:{port}/;
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

        proxy_cookie_path / {prefix};
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
        host = configured
        print(f'[INFO] internal_host aus Config: {host}')
    else:
        host = detect_gateway()
        print(f'[INFO] internal_host auto-erkannt (Gateway): {host}')

    messengers = [m for m in config.get('messengers', []) if m.get('enabled', True)]

    proxy_blocks = ''.join(
        proxy_block(m['icon'].lower(), m['name'], host, m['port'])
        for m in messengers
        if m.get('icon') and m.get('port')
    )

    conf = f"""# Auto-generated by gen_nginx.py – do not edit manually

map $http_upgrade $connection_upgrade {{
    default  upgrade;
    ''       close;
}}

server {{
    listen 17770;

    # ── Internal session check ────────────────────────────
    location = /auth-check {{
        internal;
        proxy_pass              http://127.0.0.1:5000/auth-check;
        proxy_pass_request_body off;
        proxy_set_header        Content-Length  "";
        proxy_set_header        Cookie          $http_cookie;
        proxy_set_header        X-Real-IP       $remote_addr;
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
        proxy_set_header   Host   $host;
        proxy_set_header   Cookie $http_cookie;
    }}

    # ── Flask app (login, portal, static) ────────────────
    location / {{
        proxy_pass         http://127.0.0.1:5000;
        proxy_set_header   Host              $host;
        proxy_set_header   X-Real-IP         $remote_addr;
        proxy_set_header   X-Forwarded-For   $proxy_add_x_forwarded_for;
        proxy_set_header   X-Forwarded-Proto $scheme;
    }}
{proxy_blocks}
}}
"""

    os.makedirs(os.path.dirname(NGINX_CONF), exist_ok=True)
    with open(NGINX_CONF, 'w') as f:
        f.write(conf)
    print(f'[INFO] nginx config written → {NGINX_CONF}')
    for m in messengers:
        print(f'[INFO]   /proxy/{m["icon"].lower()}/ → http://{host}:{m["port"]}/')


if __name__ == '__main__':
    main()
