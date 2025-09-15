# pages/home.py
from datetime import datetime, date

import dash
from dash import html, dcc, callback, Output, Input
import dash_bootstrap_components as dbc

from core.backend import read_settings, list_exams, compute_stock_snapshot

dash.register_page(__name__, path="/", redirect_from=["/home"], name="Início", order=0)

# --------------------------- Helpers ---------------------------

def br_currency(x: float) -> str:
    try:
        v = float(x)
    except Exception:
        return "R$ 0,00"
    s = f"{v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"R$ {s}"

def kpi_card(id_value: str, label: str, icon: str, tooltip: str | None = None):
    card = dbc.Card(
        dbc.CardBody([
            # meta (ícone + rótulo) CENTRALIZADOS
            html.Div([
                html.I(className=f"fa {icon} fa-lg me-2"),
                html.Span(label, className="text-muted small")
            ], className="d-flex justify-content-center align-items-center mb-2 kpi-meta"),
            # valor principal (tamanho ajustado via CSS)
            html.Div(id=id_value, className="display-6 fw-semibold kpi-value"),
        ], className="kpi-body"),
        className="kpi-card shadow-sm h-100"
    )
    if tooltip:
        return html.Div(
            [card, dbc.Tooltip(tooltip, target=id_value, placement="bottom", autohide=True)],
            className="h-100"
        )
    return card

def hero():
    s = read_settings()
    title = s.get("portal_name", "Portal Radiológico")
    return html.Div([
        html.Div(className="hero-bg"),
        html.Div([
            html.H1(title, className="mb-2 fw-bold"),
            html.P("Fluxo rápido para cadastro de exames, estoque por lote e visão gerencial.",
                   className="lead mb-0"),
        ], className="position-relative", style={"zIndex": 2}),
    ], className="hero glass shadow-sm rounded-4 p-4 p-md-5 mb-4 position-relative overflow-hidden")

# --------------------------- Cards simples ---------------------------

CARDS = [
    {"title":"Cadastro de Exame", "icon":"fa-file-signature", "path":"/cadastro"},
    {"title":"Dashboard",         "icon":"fa-chart-line",     "path":"/dashboard"},
    {"title":"Exames",            "icon":"fa-table",          "path":"/exames"},
    {"title":"Gestão de estoque", "icon":"fa-boxes-stacked",  "path":"/estoque"},
    {"title":"Gerencial",         "icon":"fa-user-gear",      "path":"/gerencial"},
    {"title":"Exportar",          "icon":"fa-file-csv",       "path":"/exportar"},
]

def simple_card(item):
    icon = html.I(className=f"fa {item['icon']} feature-icon mb-3")
    title = html.Div(item["title"], className="h5 mb-0 fw-semibold")
    card_body = dbc.CardBody(
        [icon, title],
        className="text-center d-flex flex-column align-items-center justify-content-center py-4"
    )
    card = dbc.Card(card_body, className="feature-card shadow-sm h-100 text-center")
    return dcc.Link(
        card,
        href=dash.get_relative_path(item["path"]),
        className="text-decoration-none text-reset feature-item"
    )

# --------------------------- Layout ---------------------------

layout = dbc.Container([
    hero(),

    # KPIs (agora como DIV com GRID, centralizado e gap de 1 cm)
    html.Div([
        kpi_card("kpi_total_exams", "Exames (total)", "fa-file-medical", "Total de exames cadastrados."),
        kpi_card("kpi_today_exams", "Exames hoje", "fa-calendar-day", "Exames com data de hoje."),
        kpi_card("kpi_low_stock", "Abaixo do mínimo", "fa-triangle-exclamation", "Materiais abaixo do mínimo."),
        kpi_card("kpi_stock_value", "Valor do estoque", "fa-coins", "Estimativa: estoque atual × valor unitário."),
    ], className="kpi-grid mb-4"),

    html.H5("Acessos rápidos", className="mt-2 mb-3 text-center"),

    # GRID com 3 colunas e gap de 1 cm (funções)
    html.Div([simple_card(c) for c in CARDS], className="features-grid mb-5"),

    dcc.Interval(id="home_refresh", interval=60_000, n_intervals=0)
], fluid=True)

# --------------------------- Callbacks ---------------------------

@callback(
    Output("kpi_total_exams", "children"),
    Output("kpi_today_exams", "children"),
    Output("kpi_low_stock", "children"),
    Output("kpi_stock_value", "children"),
    Input("home_refresh", "n_intervals"),
)
def load_kpis(_n):
    rows = list_exams()
    total = len(rows)

    today = date.today()
    today_count = 0
    for e in rows:
        dt_iso = e.get("data_hora")
        if not dt_iso:
            continue
        try:
            dt = datetime.fromisoformat(dt_iso)
            if dt.date() == today:
                today_count += 1
        except Exception:
            pass

    snap = compute_stock_snapshot()
    low = sum(1 for r in snap if r.get("abaixo_minimo"))
    stock_value = 0.0
    for r in snap:
        try:
            stock_value += float(r.get("estoque_atual") or 0.0) * float(r.get("valor_unitario") or 0.0)
        except Exception:
            pass

    return f"{total}", f"{today_count}", f"{low}", br_currency(stock_value)
