import os
import logging
import traceback
import time  # <- (novo) para cache-busting do logo
from datetime import datetime, timedelta, UTC
from functools import wraps

from flask import Flask, session, redirect, url_for, request, render_template_string, send_from_directory, make_response
from werkzeug.security import check_password_hash

import dash
from dash import html, dcc
import dash_bootstrap_components as dbc
import dash_mantine_components as dmc

# ===== Núcleo (seu backend/JSON/repos/helpers) =====
from core.backend import (
    THEMES, read_settings, write_settings, ensure_dirs,
    find_user_by_email, init_files, compute_stock_snapshot,
)

# ------------------- LOGGING -------------------
logging.basicConfig(level=logging.DEBUG, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("radio-am")

# ------------------- FLASK (auth / arquivos) -------------------
SECRET_KEY = os.getenv("SECRET_KEY", "change-me-in-prod")
DATA_DIR   = os.getenv("DATA_DIR", "data")
UPLOAD_DIR = os.path.join(DATA_DIR, "uploads")

ensure_dirs()
init_files()

server = Flask(__name__)
server.secret_key = SECRET_KEY

# ===== Prefixos usados pelo Dash (mantenha em sincronia com Dash abaixo) =====
APP_PREFIX = "/app"          # deve bater com requests_pathname_prefix/routes_pathname_prefix
ASSETS_PREFIX = f"{APP_PREFIX}/assets"

def resolve_logo_url(settings) -> str:
    """
    Resolve a URL de logo para a UI pública (login/nav), normalizando o prefixo de assets.
    Ordem: settings.logo_url (normaliza '/assets' -> '/app/assets') -> settings.logo_file (uploads) -> padrão.
    """
    url = settings.get("logo_url")
    if url:
        # normaliza '/assets/...'
        if url.startswith("/assets/"):
            url = ASSETS_PREFIX + url[len("/assets"):]
        # se já vier '/app/assets/...', mantém
        return url

    # compatibilidade antiga: logo salvo em uploads (s["logo_file"])
    if settings.get("logo_file"):
        try:
            return url_for("serve_uploads", filename=settings["logo_file"])
        except Exception:
            pass

    # padrão
    return f"{ASSETS_PREFIX}/logo.png"

@server.route("/healthz")
def healthz():
    return {"status": "ok"}, 200

@server.route("/uploads/<path:filename>")
def serve_uploads(filename):
    return send_from_directory(UPLOAD_DIR, filename)

def login_required(view_func):
    @wraps(view_func)
    def w(*args, **kw):
        uid = session.get("user_id")
        last = session.get("last_active")
        if not uid:
            return redirect(url_for("login", next=request.path))
        try:
            if last and datetime.now(UTC) - datetime.fromisoformat(last) > timedelta(minutes=30):
                session.clear()
                return redirect(url_for("login"))
        except Exception:
            session.clear()
            return redirect(url_for("login"))
        session["last_active"] = datetime.now(UTC).isoformat()
        return view_func(*args, **kw)
    return w

@server.route("/")
def root():
    # use /app/ (com barra final) para estabilidade do Dash Router
    return redirect("/app/")

# ---------- PROTEÇÃO DO SUBPATH /app VIA FLASK ----------
@server.before_request
def require_login_on_app():
    """
    Protege /app, permite endpoints internos do Dash e LOGA o fluxo.
    Evita loops de loading e mantém /login fora do /app.
    """
    path = request.path or ""

    # Normaliza: força barra final em /app
    if path == "/app":
        log.debug("301 fix: /app -> /app/")
        return redirect("/app/")

    if path.startswith("/app"):
        log.debug(f"[before_request] path={path} user_id={session.get('user_id')}")

        # whitelists do Dash
        allow_prefixes = (
            "/app/_dash",                 # layout, deps, update
            "/app/_favicon",              # favicon
            "/app/_reload-hash",          # dev reload
            "/app/assets",                # assets
            "/app/_dash-component-suites" # bundles
        )
        if path == "/app/":
            # deixa passar; o Dash buscará _dash-layout / _dash-dependencies depois
            pass
        elif path.startswith(allow_prefixes):
            return None

        if not session.get("user_id"):
            log.debug("[before_request] sem sessão -> redirect /login")
            return redirect("/login")

        # atualiza last_active
        try:
            session["last_active"] = datetime.now(UTC).isoformat()
        except Exception:
            pass
    return None

# ---------- HANDLERS DE ERRO (debug explícito) ----------
@server.errorhandler(500)
def handle_500(e):
    log.error("HTTP 500:\n%s", traceback.format_exc())
    return "Erro interno (veja logs do servidor).", 500

@server.errorhandler(Exception)
def handle_any(e):
    log.error("Unhandled exception:\n%s", traceback.format_exc())
    return "Erro inesperado (veja logs do servidor).", 500

# ---------- LOGIN / LOGOUT ----------
LOGIN_TEMPLATE = """
<!doctype html><html><head><meta charset="utf-8">
<title>{{ portal_name }} - Login</title><meta name="viewport" content="width=device-width, initial-scale=1">
<link rel="stylesheet" href="{{ theme_url }}">
<style>
html,body{height:100%;margin:0;font-family:system-ui,-apple-system,Segoe UI,Roboto,Ubuntu,Arial}
.wrap{display:flex;align-items:center;justify-content:center;height:100%;background:#f6f7fb}
.card{background:#fff;padding:32px;border-radius:16px;width:360px;box-shadow:0 10px 30px rgba(0,0,0,.08)}
.brand{display:flex;align-items:center;justify-content:center;gap:10px;margin-bottom:12px;}
.brand img{height:{{ logo_height_px }}px;width:auto;display:block;}
h1{font-size:20px;margin:0 0 6px}
label{display:block;margin-top:12px;font-size:14px}
input{width:100%;padding:10px 12px;border-radius:10px;border:1px solid #dcdce6;margin-top:6px}
button{margin-top:16px;width:100%;padding:12px;border-radius:12px;border:0;background:#111827;color:#fff;font-weight:600}
.error{color:#b91c1c;font-size:13px;margin-top:8px}.hint{margin-top:12px;font-size:12px;color:#6b7280}
</style></head><body><div class="wrap"><div class="card">
<div class="brand">{% if logo_url %}<img src="{{ logo_url }}">{% else %}<h1>{{ portal_name }}</h1>{% endif %}</div>
<h1>Login</h1>{% if error %}<div class="error">{{ error }}</div>{% endif %}
<form method="post"><label>E-mail</label><input name="email" type="email" required autofocus>
<label>Senha</label><input name="senha" type="password" required><button type="submit">Entrar</button></form>
<div class="hint">Desenvolvido por: <b>Fia Softworks</b> / <b>2025 - v.1.01</b></div></div></div></body></html>
"""

@server.route("/login", methods=["GET","POST"])
def login():
    s = read_settings()

    # URL do tema (Bootstrap) para a página de login
    theme_url = THEMES.get(s.get("theme","Flatly"), list(THEMES.values())[0])

    # Novo: resolve a URL do logo a partir das configurações (assets ou uploads)
    logo_url = resolve_logo_url(s)
    # Cache-busting simples para refletir trocas de logo imediatamente
    if logo_url:
        sep = "&" if "?" in logo_url else "?"
        logo_url = f"{logo_url}{sep}v={int(time.time())}"

    err = None
    if request.method == "POST":
        email = (request.form.get("email") or "").strip().lower()
        senha = request.form.get("senha") or ""
        u = find_user_by_email(email)
        if u and check_password_hash(u.get("senha_hash",""), senha):
            session.update({
                "user_id": u["id"], "user_email": u["email"], "user_name": u["nome"],
                "perfil": u.get("perfil","user"), "last_active": datetime.now(UTC).isoformat()
            })
            log.info("Login OK para %s -> /app/", email)
            return redirect("/app/")
        err = "Credenciais inválidas."
        log.warning("Login FAIL para %s", email)

    return render_template_string(
        LOGIN_TEMPLATE,
        error=err,
        portal_name=s.get("portal_name","Portal Radiológico"),
        theme_url=theme_url,
        logo_url=logo_url,
        logo_height_px=s.get("logo_height_px", 40)
    )

@server.route("/logout")
def logout():
    session.clear()
    # volta direto ao login
    return redirect("/login")

# Alias sob /app (opcional, mas útil se alguém apontar para /app/logout)
@server.route("/app/logout")
def logout_alias():
    return redirect("/logout")

# ------------------- DASH (multipáginas) -------------------
external_stylesheets = [
    dbc.themes.BOOTSTRAP,
    "https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0-beta3/css/all.min.css",
]

app = dash.Dash(
    __name__,
    server=server,                           # usa o Flask com /login e /logout
    use_pages=True,
    suppress_callback_exceptions=True,
    # Prefixos alinhados:
    requests_pathname_prefix="/app/",
    routes_pathname_prefix="/app/",
    external_stylesheets=external_stylesheets,
    prevent_initial_callbacks='initial_duplicate',
    title="Portal Radiológico",
)

# Validação antecipada do layout — inclui páginas E os elementos dinâmicos do Gerencial
try:
    base_pages = [dash.page_registry[p]["layout"] for p in dash.page_registry]

    # Importa o módulo da página Gerencial para injetar as árvores das abas no validation_layout
    try:
        from pages import gerencial as _ger
        gerencial_extras = html.Div([
            # Todas as abas renderizadas (apenas para validação, não aparecem em runtime)
            _ger.tab_users(),
            _ger.tab_doctors(),
            _ger.tab_examtypes(),
            _ger.tab_config(),
            _ger.tab_logs(),
            # Placeholders para elementos que só existem em callbacks (ex.: conteúdo do FAB por aba)
            html.Div(id="fab_feedback_u"),
            html.Div(id="fab_feedback_d"),
            html.Div(id="fab_feedback_e"),
        ])
        app.validation_layout = html.Div(base_pages + [gerencial_extras])
        log.debug("validation_layout estendido com abas do Gerencial e placeholders.")
    except Exception as ge:
        # Se não conseguir importar/instanciar, mantém ao menos as páginas
        app.validation_layout = html.Div(base_pages)
        log.warning("[validation_layout] Falha ao estender com Gerencial: %r", ge)

except Exception as e:
    log.warning("[validation_layout] Aviso: %r", e)

def rel(path: str) -> str:
    # útil para links internos do Dash; NÃO usar para /login e /logout
    return dash.get_app().get_relative_path(path)

def navbar():
    s = read_settings()
    # usa o mesmo logo configurado no Gerencial
    logo_url = resolve_logo_url(s)

    # Marca central com LOGO (72px) + nome
    brand = html.Div(
        [
            html.Img(
                src=logo_url,
                alt="Logo",
                style={"height": "72px", "width": "auto"},
                className="d-inline-block align-middle me-2",
            ),
            html.Span(
                s.get("portal_name", "Portal Radiológico"),
                className="fw-semibold text-uppercase d-none d-sm-inline align-middle text-white",
                style={"letterSpacing": ".04em", "margin": 0},
            ),
        ],
        className="navbar-brand d-flex align-items-center m-0",
    )

    user = session.get("user_name") or "Usuário"
    email = session.get("user_email") or ""

    # Botão "Início" (fica à direita, antes do menu)
    def rel(path: str) -> str:
        return dash.get_app().get_relative_path(path)

    home_btn = dbc.Button(
        [html.I(className="fa-solid fa-house me-2"), "Início"],
        id="btn_nav_home",
        href=rel("/"),  # resolve para /app/
        outline=True,
        color="light",
        size="sm",
        className="rounded-pill me-2 shadow-sm",
        style={"fontWeight": 600, "paddingInline": "14px"},
    )

    # Menu do usuário
    menu = dbc.DropdownMenu(
        label=f"👤 {user}",
        align_end=True,
        children=[
            dbc.DropdownMenuItem(f"Conectado como {email}", header=True),
            dbc.DropdownMenuItem("Sair", href="/logout", external_link=True),
        ],
        className="ms-2",
    )

    right_side = html.Div([home_btn, menu], className="ms-auto d-flex align-items-center")

    return dbc.Navbar(
        dbc.Container(
            [
                # Mantém o brand centralizado como antes
                html.Div(brand, className="position-absolute start-50 translate-middle-x"),
                right_side,
            ],
            fluid=True,
            className="position-relative",
        ),
        dark=True,
        style={
            "background": "linear-gradient(90deg,#0f172a 0%,#111827 40%,#0b2447 100%)",
            "boxShadow": "0 6px 20px rgba(0,0,0,.18)",
            "borderBottom": "1px solid rgba(255,255,255,.06)",
        },
        className="mb-3",
    )

# -------- Layout (sem guard no layout) --------
app.layout = lambda: dmc.MantineProvider(
    dmc.DatesProvider(
        settings={"locale":"pt-br"},
        children=html.Div([
            dcc.Location(id="url"),
            html.Link(
                id="theme_css",
                rel="stylesheet",
                href=THEMES.get(read_settings().get("theme","Flatly"), list(THEMES.values())[0])
            ),
            navbar(),
            dash.page_container
        ])
    )
)

# ---- Rotas protegidas (exemplo de export via Flask com @login_required) ----
@server.route("/export_estoque.csv")
@login_required
def export_estoque_csv():
    import pandas as pd
    df = pd.DataFrame(compute_stock_snapshot())
    if df.empty:
        df = pd.DataFrame(columns=[
            "id","nome","tipo","unidade","valor_unitario",
            "estoque_inicial","entradas","saidas","ajustes","consumo_exames",
            "estoque_atual","estoque_minimo","abaixo_minimo"
        ])
    df = df[[
        "id","nome","tipo","unidade","valor_unitario",
        "estoque_inicial","entradas","saidas","ajustes","consumo_exames",
        "estoque_atual","estoque_minimo","abaixo_minimo"
    ]]
    resp = make_response(df.to_csv(index=False, encoding="utf-8-sig"))
    resp.headers["Content-Disposition"] = "attachment; filename=estoque.csv"
    resp.mimetype = "text/csv"
    return resp

if __name__ == "__main__":
    log.info("Iniciando em http://127.0.0.1:8050/app/")
    app.run(debug=True)
