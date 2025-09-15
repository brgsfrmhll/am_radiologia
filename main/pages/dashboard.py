import dash
from dash import html, dcc, Input, Output, State
import dash_bootstrap_components as dbc
import plotly.express as px
import pandas as pd
from datetime import datetime

from core.backend import (
    list_exams, list_materials, material_price_map, MOD_LABEL, aggregate_exam_material_usage
)

dash.register_page(__name__, path="/dashboard", name="Dashboard")

def filtros():
    return dbc.Card([
        dbc.CardHeader("Filtros"),
        dbc.CardBody(
            dbc.Row([
                dbc.Col(dcc.Dropdown(id="f_modalidade", placeholder="Modalidades", multi=True,
                                     options=[{"label":MOD_LABEL.get(x,x), "value":x} for x in ["RX","CT","US","MR","MG","NM"]]), md=4),
                dbc.Col(dbc.Input(id="f_medico", placeholder="Médico (contém)"), md=4),
                dbc.Col(dbc.Input(id="f_periodo", placeholder="Período (DD/MM/YYYY a DD/MM/YYYY)"), md=4),
            ])
        )
    ], className="shadow-sm")

def kpis():
    return dbc.Row([
        dbc.Col(dbc.Card(dbc.CardBody([html.H6("Total de Exames"), html.H2(id="kpi_total")])), md=3),
        dbc.Col(dbc.Card(dbc.CardBody([html.H6("Custo Total Materiais"), html.H2(id="kpi_total_material_cost")])), md=3),
        dbc.Col(dbc.Card(dbc.CardBody([html.H6("Custo Médio/Exame"), html.H2(id="kpi_avg_exam_cost")])), md=3),
        dbc.Col(dbc.Card(dbc.CardBody([html.H6("Total Contraste (mL)"), html.H2(id="kpi_total_contrast_ml")])), md=3),
    ], className="mb-3")

layout = dbc.Container([
    filtros(),
    html.Hr(),
    kpis(),
    dcc.Loading([
        dcc.Graph(id="g_exames_modalidade"),
        dcc.Graph(id="g_series_tempo"),
        dcc.Graph(id="g_exames_por_idade"),
        dcc.Graph(id="g_top_materials_cost")
    ], type="circle")
], fluid=True)

# ===== Helpers de filtro =====
def _parse_periodo(txt):
    if not txt or "a" not in txt: return None, None
    try:
        a, b = [t.strip() for t in txt.split("a", 1)]
        d1 = datetime.strptime(a, "%d/%m/%Y")
        d2 = datetime.strptime(b, "%d/%m/%Y")
        if d1 > d2: d1, d2 = d2, d1
        return d1, d2
    except Exception:
        return None, None

def _apply_filters(exams, modalidades, medico_contains, periodo_txt):
    d1, d2 = _parse_periodo(periodo_txt)
    out = []
    for e in exams:
        if modalidades and e.get("modalidade") not in modalidades: 
            continue
        if medico_contains and medico_contains.strip():
            if medico_contains.strip().lower() not in (e.get("medico","").lower()):
                continue
        if d1 and d2:
            try:
                dt = datetime.fromisoformat(e.get("data_hora"))
                if not (d1 <= dt <= d2.replace(hour=23,minute=59,second=59)):
                    continue
            except Exception:
                pass
        out.append(e)
    return out

# ===== KPIs =====
@dash.callback(
    Output("kpi_total","children"),
    Output("kpi_total_material_cost","children"),
    Output("kpi_avg_exam_cost","children"),
    Output("kpi_total_contrast_ml","children"),
    Input("f_modalidade","value"),
    Input("f_medico","value"),
    Input("f_periodo","value"),
)
def _kpis(mods, medico, periodo):
    exams = _apply_filters(list_exams(), mods, medico, periodo)
    prices = material_price_map()

    total = len(exams)
    total_cost = 0.0
    total_contrast_ml = 0.0

    for e in exams:
        cost_exam = 0.0
        for it in e.get("materiais_usados", []) or []:
            qty = float(it.get("quantidade") or 0.0)
            mid = it.get("material_id")
            if mid in prices:
                cost_exam += qty * prices[mid]
            # estimativa: se nome do material implicar mL de contraste (id conhecido no seed = 1)
            if mid == 1:
                total_contrast_ml += qty
        total_cost += cost_exam

    avg_cost = (total_cost / total) if total > 0 else 0.0

    return (
        f"{total:,}".replace(",", "."),
        f"R$ {total_cost:,.2f}".replace(",", "X").replace(".", ",").replace("X","."),
        f"R$ {avg_cost:,.2f}".replace(",", "X").replace(".", ",").replace("X","."),
        f"{total_contrast_ml:,.2f} mL".replace(",", "X").replace(".", ",").replace("X","."),
    )

# ===== Gráficos =====
@dash.callback(
    Output("g_exames_modalidade","figure"),
    Output("g_series_tempo","figure"),
    Output("g_exames_por_idade","figure"),
    Output("g_top_materials_cost","figure"),
    Input("f_modalidade","value"),
    Input("f_medico","value"),
    Input("f_periodo","value"),
)
def _figs(mods, medico, periodo):
    exams = _apply_filters(list_exams(), mods, medico, periodo)
    if not exams:
        return px.bar(title="Sem dados"), px.line(title="Sem dados"), px.histogram(title="Sem dados"), px.bar(title="Sem dados")

    # DF principal
    df = pd.DataFrame(exams)

    # 1) Por modalidade
    df_mod = df.groupby("modalidade").size().reset_index(name="qtd")
    df_mod["modalidade"] = df_mod["modalidade"].map(lambda m: MOD_LABEL.get(m, m))
    fig1 = px.bar(df_mod, x="modalidade", y="qtd", title="Exames por Modalidade")

    # 2) Série temporal (por dia)
    def _to_day(x):
        try: return datetime.fromisoformat(x).date()
        except Exception: return None
    df["dia"] = df["data_hora"].map(_to_day)
    df_d = df.dropna(subset=["dia"]).groupby("dia").size().reset_index(name="qtd")
    fig2 = px.line(df_d, x="dia", y="qtd", markers=True, title="Exames por Dia")

    # 3) Histograma por idade
    if "idade" in df.columns:
        fig3 = px.histogram(df.dropna(subset=["idade"]), x="idade", nbins=20, title="Distribuição de Idade")
    else:
        fig3 = px.histogram(title="Distribuição de Idade")

    # 4) Top materiais por custo (consumo total x preço)
    usage = aggregate_exam_material_usage()
    prices = material_price_map()
    rows = []
    for mid, qty in usage.items():
        price = prices.get(mid, 0.0)
        rows.append({"material_id": mid, "quantidade": qty, "custo": qty*price})
    df_mat = pd.DataFrame(rows)
    if not df_mat.empty:
        df_mat = df_mat.sort_values("custo", ascending=False).head(10)
        # nomes:
        id2name = {m["id"]: m["nome"] for m in list_materials()}
        df_mat["material"] = df_mat["material_id"].map(lambda x: id2name.get(x, f"ID {x}"))
        fig4 = px.bar(df_mat, x="material", y="custo", title="Top Materiais por Custo (Total)")
    else:
        fig4 = px.bar(title="Top Materiais por Custo (Total)")

    return fig1, fig2, fig3, fig4
