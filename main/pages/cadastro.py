# pages/cadastro.py  (QoL + Estoque por lote + FIFO + auto refresh + clamp datetime + debug off)
import json
from datetime import datetime

import dash
from dash import html, dcc, Input, Output, State, ALL, no_update, ctx
import dash_bootstrap_components as dbc
import dash_mantine_components as dmc

# Ligue/desligue o painel de depuração (AGORA DESLIGADO)
DEBUG = False

# =========================
# Imports do backend (core/backend.py)
# =========================
from core.backend import (
    MODALIDADES, MOD_LABEL,
    add_or_update_exam, ensure_doctor,
    get_examtype_names, doctor_names,
    list_materials, material_price_map,
    # REMOVIDO: add_stock_movement  (evita baixa em dobro)
)

# Import opcional (lote/validade).
HAS_BATCHES = False
try:
    from core.backend import list_material_batches
    HAS_BATCHES = True
except Exception:
    def list_material_batches(_material_id: int):
        return []

dash.register_page(__name__, path="/cadastro", name="Cadastro")

# =============== Helpers de debug & datas ===============
def _dbg(event, **kw):
    """Silencioso quando DEBUG=False."""
    if not DEBUG:
        return ""
    ts = datetime.utcnow().strftime("%H:%M:%S")
    line = f"[{ts}] {event} :: " + ", ".join(f"{k}={kw[k]}" for k in kw)
    print(line)
    return line

def _now_utc_iso():
    # ISO naive (UTC) para casar com componentes
    return datetime.utcnow().replace(tzinfo=None).isoformat()

def _clamp_future_to_now(dt_iso_str: str | None) -> str:
    """
    Retorna:
      - agora se None
      - mesmo valor se <= agora
      - agora se for > agora (nunca futuro)
    """
    now = datetime.utcnow()
    if not dt_iso_str:
        return now.isoformat()
    try:
        dt = datetime.fromisoformat(dt_iso_str.replace("Z", ""))
    except Exception:
        return now.isoformat()
    return dt.isoformat() if dt <= now else now.isoformat()

# =============== UI helpers ===============
def _section_title(txt, icon=None):
    return html.Div(
        className="d-flex align-items-center gap-2 mb-2",
        children=[
            html.I(className=f"fa-solid fa-{icon}") if icon else None,
            html.Strong(txt, className="text-uppercase")
        ]
    )

def _soft_text(txt):
    return html.Small(txt, className="text-muted")

def _fmt_money(v):
    return f"R$ {v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

def _parse_qty(q):
    if q is None:
        raise ValueError("Quantidade não informada.")
    if isinstance(q, str):
        q = q.replace(",", ".").strip()
    return float(q)

def _render_materials_table(items):
    header = html.Thead(html.Tr([
        html.Th("#"), html.Th("Material"),
        html.Th("Lote"),
        html.Th("Validade") if HAS_BATCHES else None,
        html.Th("Un."), html.Th("Qtd."), html.Th("R$ unit."), html.Th("R$ total"), html.Th("Ações")
    ]))
    body = []
    prices = material_price_map()
    mats = {m["id"]: m for m in list_materials()}
    batches_by_id = {}
    if HAS_BATCHES:
        for mid in mats:
            for b in list_material_batches(mid):
                if b and "id" in b:
                    batches_by_id[b["id"]] = b

    for idx, it in enumerate(items or []):
        mid = int(it.get("material_id"))
        m = mats.get(mid, {})
        qty = float(it.get("quantidade") or 0.0)
        unit = m.get("unidade") or "-"
        name = m.get("nome") or f"ID {mid}"
        unit_price = float(prices.get(mid, 0.0))
        total = unit_price * qty
        lote_id = it.get("lote_id")
        lote = validade = "-"
        if HAS_BATCHES and (lote_id is not None) and (lote_id in batches_by_id):
            lote = batches_by_id[lote_id].get("lote", "-")
            validade = batches_by_id[lote_id].get("validade", "-")

        row = [
            html.Td(idx + 1),
            html.Td(name),
            html.Td(lote),
            html.Td(validade) if HAS_BATCHES else None,
            html.Td(unit),
            html.Td(f"{qty:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")),
            html.Td(_fmt_money(unit_price)),
            html.Td(_fmt_money(total)),
            html.Td(html.Div([
                dbc.Button("Editar", id={"type": "mat_edit_btn", "idx": idx}, size="sm", className="me-1"),
                dbc.Button("Remover", id={"type": "mat_del_btn", "idx": idx}, size="sm", color="danger"),
            ]))
        ]
        body.append(html.Tr([c for c in row if c is not None]))
    return dbc.Table([header, html.Tbody(body)], bordered=True, hover=True, striped=True, responsive=True, className="align-middle")

def _build_summary(items):
    items = items or []
    prices = material_price_map()
    total_cost = 0.0
    total_lines = len(items)
    for it in items:
        mid = int(it.get("material_id"))
        qty = float(it.get("quantidade") or 0.0)
        unit_cost = float(prices.get(mid, 0.0))
        total_cost += unit_cost * qty
    return html.Div([
        html.Div(f"Itens: {total_lines}", className="small"),
        html.Div(f"Custo estimado: {_fmt_money(total_cost)}", className="small fw-semibold"),
    ])

# =============== Layout ===============
def cadastro_card():
    debug_panel = []
    if DEBUG:
        debug_panel = [
            dbc.Accordion([
                dbc.AccordionItem([
                    html.Div("Último evento:", className="fw-semibold mb-1"),
                    html.Pre(id="dbg_last_event", style={"whiteSpace": "pre-wrap", "fontSize": "12px"}),
                    html.Hr(),
                    html.Div("materials_modal_store (buffer do modal):", className="fw-semibold mb-1"),
                    html.Pre(id="dbg_modal_store", style={"whiteSpace": "pre-wrap", "fontSize": "12px"}),
                    html.Hr(),
                    html.Div("materials_selected_store (confirmados):", className="fw-semibold mb-1"),
                    html.Pre(id="dbg_selected_store", style={"whiteSpace": "pre-wrap", "fontSize": "12px"}),
                ], title="Debug • Estados e Últimos Eventos")
            ], start_collapsed=False, always_open=True, className="mt-3")
        ]

    return dbc.Card([
        dbc.CardHeader(
            html.Div(
                className="d-flex align-items-center justify-content-between",
                children=[
                    html.Div([html.I(className="fa-solid fa-clipboard-list me-2"), html.Strong("Cadastro de Exame (Atendimento)")]),
                    dbc.Button(
                        [html.I(className="fa-solid fa-boxes-stacked me-2"), "Gerenciar Materiais"],
                        id="btn_open_materials_modal",
                        color="secondary",
                        className="btn-sm",
                    ),
                ]
            )
        ),
        dbc.CardBody([
            _section_title("Dados do atendimento", icon="id-card"),
            dbc.Row([
                dbc.Col(dbc.Input(id="exam_id", placeholder="Ex.: E-0001", type="text", maxLength=50), md=3),
                dbc.Col(dcc.Dropdown(
                    id="modalidade",
                    options=[{"label": MOD_LABEL.get(m, m), "value": m} for m in MODALIDADES],
                    placeholder="Modalidade",
                    clearable=True
                ), md=3),
                dbc.Col(dmc.Autocomplete(
                    id="exame_auto",
                    placeholder="Selecione a modalidade para carregar os exames",
                    data=[],
                    limit=100,
                    clearable=True,
                ), md=6),
            ], className="g-3 mb-3"),

            dbc.Row([
                dcc.Store(id="__dtpicker_dummy__"),  # apenas pra evitar warnings em alguns navegadores
                dbc.Col(dmc.DateTimePicker(
                    id="data_dt",
                    placeholder="Data/Hora (padrão: agora)",
                    valueFormat="DD/MM/YYYY HH:mm",
                    # Nota: se sua versão do dmc não aceitar 'clearable', remova a linha abaixo
                    clearable=True,
                    # Evita selecionar DIAS futuros; horário futuro do mesmo dia será travado no salvar
                    maxDate=datetime.utcnow().strftime("%Y-%m-%d"),
                ), md=4),
                dbc.Col(dmc.Autocomplete(
                    id="medico_auto",
                    placeholder="Médico solicitante/realizador",
                    data=[],
                    limit=100,
                    clearable=True,
                ), md=5),
                dbc.Col(dbc.Input(id="idade", placeholder="Idade (0-120)", type="number", min=0, max=120), md=3),
            ], className="g-3"),

            html.Small("Padrão: data/hora atual (UTC). Você pode informar uma data passada, nunca futura.",
                       className="text-muted"),

            html.Hr(className="my-3"),

            _section_title("Materiais do atendimento", icon="flask"),
            dbc.Row([
                dbc.Col(dbc.Alert(
                    id="selected_materials_summary",
                    className="p-2 mb-0",
                    color="light",
                    children=_build_summary([]),
                ), md=8),
                dbc.Col(dbc.Button(
                    [html.I(className="fa-solid fa-floppy-disk me-2"), "Salvar Exame"],
                    id="btn_salvar",
                    color="primary",
                    className="w-100"
                ), md=4),
            ], className="g-3"),

            html.Div(id="save_feedback", className="mt-3"),

            # Stores
            dcc.Store(id="materials_selected_store", data=[], storage_type="session"),  # itens confirmados
            dcc.Store(id="materials_modal_store", data=[]),  # buffer do modal
            dcc.Store(id="materials_edit_index", data=None),
            dcc.Store(id="delete_pending_index", data=None),  # índice aguardando confirmação de exclusão

            # Redirecionamento pós-salvar
            dcc.Location(id="page_redirect"),
            dcc.Interval(id="after_save_interval", interval=2500, n_intervals=0, max_intervals=1, disabled=True),

            # Sumíder para “absorver” saídas de debug quando DEBUG=False
            html.Div(id="void_debug", style={"display": "none"}),

            # Painel de debug (só com DEBUG=True)
            *debug_panel
        ])
    ], className="shadow-sm")

def materials_modal():
    hide_style = {"display": "none"} if not HAS_BATCHES else {}
    # Lote mais largo (md=6) + minWidth 480px
    return dbc.Modal(
        id="materials_modal",
        is_open=False,
        size="xl",
        centered=True,
        children=[
            dbc.ModalHeader(dbc.ModalTitle([html.I(className="fa-solid fa-vial me-2"), "Materiais do atendimento"])),
            dbc.ModalBody([
                _soft_text("Selecione o material, informe a quantidade e utilize os botões para adicionar/editar/remover."),
                dbc.Row([
                    dbc.Col([
                        html.Label("Material"),
                        dcc.Dropdown(id="mat_sel_id", options=[], placeholder="Selecione um material", clearable=True),
                    ], md=4 if HAS_BATCHES else 6),
                    dbc.Col([
                        html.Label("Lote / Validade (Saldo)"),
                        dcc.Dropdown(
                            id="mat_sel_lote",
                            options=[],
                            placeholder="Selecione um lote (opcional)",
                            clearable=True,
                            style={"minWidth": "480px"},
                        ),
                    ], md=6, style=hide_style),
                    dbc.Col([
                        html.Label("Quantidade"),
                        dbc.Input(id="mat_sel_qtd", type="number", step=0.01, min=0, placeholder="Ex.: 10 / 80.0"),
                    ], md=2 if HAS_BATCHES else 6),
                ], className="mb-2 g-2"),

                html.Div(className="d-flex align-items-center gap-2 mb-3", children=[
                    dbc.Badge(id="mat_sel_un_badge", color="light", className="text-dark"),
                    dbc.Badge(id="mat_sel_preco_badge", color="light", className="text-dark"),
                    dbc.Badge(id="mat_sel_saldo_badge", color="light", className="text-dark", style=hide_style),
                    dbc.Button([html.I(className="fa-solid fa-plus me-2"), "Adicionar"], id="mat_add_btn", color="primary", className="ms-auto"),
                    dbc.Button([html.I(className="fa-solid fa-rotate me-2"), "Atualizar item"], id="mat_update_btn", color="success", disabled=True),
                    dbc.Button([html.I(className="fa-regular fa-circle-xmark me-2"), "Limpar seleção"], id="mat_clear_btn", color="secondary", outline=True),
                    html.Div(id="materials_modal_feedback", className="ms-2"),
                ]),

                dbc.Card([
                    dbc.CardHeader([html.I(className="fa-solid fa-list-check me-2"), "Itens selecionados (no modal)"]),
                    dbc.CardBody(html.Div(id="materials_table", className="table-responsive", children=_render_materials_table([])))
                ]),
            ]),
            dbc.ModalFooter([
                dbc.Button("Fechar", id="materials_close_btn", className="me-2"),
                dbc.Button([html.I(className="fa-solid fa-check me-2"), "Concluir"], id="materials_done_btn", color="primary")
            ])
        ]
    )

def confirm_delete_modal():
    return dbc.Modal(
        id="confirm_del_modal",
        is_open=False,
        centered=True,
        children=[
            dbc.ModalHeader(dbc.ModalTitle("Remover item?")),
            dbc.ModalBody("Essa ação não pode ser desfeita."),
            dbc.ModalFooter([
                dbc.Button("Cancelar", id="cancel_del_btn", className="me-2"),
                dbc.Button([html.I(className="fa-solid fa-trash-can me-2"), "Remover"], id="confirm_del_btn", color="danger"),
            ])
        ]
    )

layout = dbc.Container([cadastro_card(), materials_modal(), confirm_delete_modal()], fluid=True)

# =================================================================
# Callbacks
# =================================================================

# 0) Inicializa data/hora com “agora” ao entrar na página (se vazio)
@dash.callback(
    Output("data_dt", "value"),
    Input("_pages_location", "pathname"),
    State("data_dt", "value"),
    prevent_initial_call=False
)
def _init_dt_now(pathname, cur_value):
    try:
        if not pathname or not pathname.endswith("/cadastro"):
            raise dash.exceptions.PreventUpdate
        if cur_value:
            raise dash.exceptions.PreventUpdate
    except Exception:
        raise dash.exceptions.PreventUpdate
    return _now_utc_iso()

# 1) Preencher listas (exame e médico)
@dash.callback(
    Output("exame_auto", "data"),
    Output("medico_auto", "data"),
    Input("modalidade", "value"),
)
def _fill_autocomplete(mod_val):
    return get_examtype_names(mod_val), doctor_names()

# 2A) Abrir/fechar modal (NÃO mexe em stores)
@dash.callback(
    Output("materials_modal", "is_open", allow_duplicate=True),
    Input("btn_open_materials_modal", "n_clicks"),
    Input("materials_close_btn", "n_clicks"),
    State("materials_modal", "is_open"),
    prevent_initial_call=True
)
def _toggle_modal(n_open, n_close, is_open):
    trig = ctx.triggered_id
    if trig == "btn_open_materials_modal":
        _dbg("OPEN_MODAL")
        return True
    _dbg("CLOSE_MODAL_BUTTON")
    return False  # fechar

# 2B) Ao abrir (is_open=True), carrega opções e SINCRONIZA buffer com itens confirmados
@dash.callback(
    Output("mat_sel_id", "options"),
    Output("mat_sel_id", "value"),
    Output("mat_sel_lote", "options", allow_duplicate=True),
    Output("mat_sel_lote", "value", allow_duplicate=True),
    Output("mat_sel_qtd", "value", allow_duplicate=True),
    Output("mat_sel_un_badge", "children", allow_duplicate=True),
    Output("mat_sel_preco_badge", "children", allow_duplicate=True),
    Output("mat_sel_saldo_badge", "children", allow_duplicate=True),
    Output("mat_update_btn", "disabled", allow_duplicate=True),
    Output("materials_modal_feedback", "children", allow_duplicate=True),
    Output("materials_modal_store", "data", allow_duplicate=True),
    Output("dbg_last_event", "children", allow_duplicate=True) if DEBUG else Output("void_debug", "children", allow_duplicate=True),
    Input("materials_modal", "is_open"),
    State("materials_selected_store", "data"),
    prevent_initial_call=True
)
def _on_open_modal(is_open, confirmed_items):
    if not is_open:
        raise dash.exceptions.PreventUpdate
    mats = list_materials()
    opts = [{"label": f"{m['nome']} (R$ {float(m.get('valor_unitario') or 0):.2f}/{m.get('unidade')})", "value": m["id"]} for m in mats]
    items = confirmed_items or []
    dbg = _dbg("ON_OPEN_MODAL", confirmed=len(items))
    return opts, None, [], None, None, "", "", "", True, "", items, dbg

# 3) Lotes/Unidade/Preço/Saldo ao escolher material
@dash.callback(
    Output("mat_sel_lote", "options"),
    Output("mat_sel_un_badge", "children"),
    Output("mat_sel_preco_badge", "children"),
    Output("mat_sel_saldo_badge", "children"),
    Input("mat_sel_id", "value"),
)
def _load_batches(mat_id):
    mats = {m["id"]: m for m in list_materials()}
    if not mat_id or int(mat_id) not in mats:
        return [], "", "", ""
    m = mats[int(mat_id)]
    unidade = m.get("unidade") or "-"
    preco = float(m.get("valor_unitario") or 0)
    if HAS_BATCHES:
        batches = list_material_batches(int(mat_id))
        opt = [{
            "label": f"{b.get('lote','-')} • Val: {b.get('validade','-')} • Saldo: {b.get('saldo',0)}",
            "value": b.get("id")
        } for b in batches]
        saldo_total = sum(float(b.get("saldo") or 0) for b in batches)
        return opt, f"Unidade: {unidade}", f"Preço: {_fmt_money(preco)}/{unidade}", f"Saldo total: {saldo_total:g}"
    else:
        return [], f"Unidade: {unidade}", f"Preço: {_fmt_money(preco)}/{unidade}", ""

# 4) Tabela do MODAL reage ao buffer do modal + espelha no painel de debug
@dash.callback(
    Output("materials_table", "children"),
    Output("dbg_modal_store", "children") if DEBUG else Output("void_debug", "children", allow_duplicate=True),
    Input("materials_modal_store", "data"),
    prevent_initial_call=True,  # importante por causa do allow_duplicate
)
def _refresh_modal_table(items):
    text = ""
    if DEBUG:
        try:
            text = json.dumps(items or [], ensure_ascii=False, indent=2)
        except Exception:
            text = str(items)
    return _render_materials_table(items or []), text

# 5) Resumo lateral reage ao store principal (confirmados) + debug
@dash.callback(
    Output("selected_materials_summary", "children"),
    Output("dbg_selected_store", "children") if DEBUG else Output("void_debug", "children", allow_duplicate=True),
    Input("materials_selected_store", "data"),
    prevent_initial_call=True,  # importante por causa do allow_duplicate
)
def _refresh_summary(items):
    text = ""
    if DEBUG:
        try:
            text = json.dumps(items or [], ensure_ascii=False, indent=2)
        except Exception:
            text = str(items)
    return _build_summary(items or []), text

# 6) Adicionar (no MODAL) → altera apenas o buffer (soma itens iguais)
@dash.callback(
    Output("materials_modal_store", "data", allow_duplicate=True),
    Output("materials_modal_feedback", "children", allow_duplicate=True),
    Output("mat_sel_id", "value", allow_duplicate=True),
    Output("mat_sel_lote", "value", allow_duplicate=True),
    Output("mat_sel_qtd", "value", allow_duplicate=True),
    Output("materials_edit_index", "data", allow_duplicate=True),
    Output("mat_update_btn", "disabled", allow_duplicate=True),
    Output("dbg_last_event", "children", allow_duplicate=True) if DEBUG else Output("void_debug", "children", allow_duplicate=True),
    Input("mat_add_btn", "n_clicks"),
    State("materials_modal_store", "data"),
    State("mat_sel_id", "value"),
    State("mat_sel_lote", "value"),
    State("mat_sel_qtd", "value"),
    prevent_initial_call=True
)
def _add_item(n, items, mat_id, lote_id, qtd):
    if not n:
        raise dash.exceptions.PreventUpdate

    before_len = len(items or [])
    errors = []
    if not mat_id:
        errors.append("Selecione um material.")
    try:
        q = _parse_qty(qtd)
        if q <= 0:
            errors.append("Quantidade deve ser maior que zero.")
    except Exception:
        q = 0.0
        errors.append("Quantidade inválida.")

    lote_norm = int(lote_id) if (HAS_BATCHES and lote_id not in (None, "", "null")) else None

    # Validação por lote se informado
    if HAS_BATCHES and (lote_norm is not None):
        b = next((x for x in list_material_batches(int(mat_id)) if x.get("id") == lote_norm), None)
        if not b:
            errors.append("Lote inválido.")
        else:
            # Se já existe item igual, validar somatório
            current = 0.0
            for it in (items or []):
                if int(it.get("material_id")) == int(mat_id) and (it.get("lote_id") or None) == lote_norm:
                    current += float(it.get("quantidade") or 0.0)
            if current + q > float(b.get("saldo") or 0.0) + 1e-9:
                errors.append(f"Saldo insuficiente no lote. Disponível: {b.get('saldo')}.")

    if errors:
        dbg = _dbg("ADD_FAIL", before=before_len, errors=len(errors))
        return no_update, dbc.Alert(html.Ul([html.Li(e) for e in errors]), color="danger"), no_update, no_update, no_update, no_update, no_update, dbg

    items = list(items or [])
    # Mesma combinação (material + lote) => soma
    merged = False
    for it in items:
        if int(it.get("material_id")) == int(mat_id) and (it.get("lote_id") or None) == lote_norm:
            it["quantidade"] = float(it.get("quantidade") or 0.0) + q
            merged = True
            break
    if not merged:
        items.append({"material_id": int(mat_id), "lote_id": lote_norm, "quantidade": q})

    after_len = len(items)
    dbg = _dbg("ADD_OK", before=before_len, after=after_len, mat=int(mat_id), lote=lote_norm, qtd=q, merged=merged)
    return items, dbc.Alert("Item adicionado.", color="success"), None, None, None, None, True, dbg

# 7) Preparar edição (no MODAL) — só dispara com clique real (>0)
@dash.callback(
    Output("mat_sel_id", "value", allow_duplicate=True),
    Output("mat_sel_lote", "value", allow_duplicate=True),
    Output("mat_sel_qtd", "value", allow_duplicate=True),
    Output("materials_edit_index", "data", allow_duplicate=True),
    Output("mat_update_btn", "disabled", allow_duplicate=True),
    Output("dbg_last_event", "children", allow_duplicate=True) if DEBUG else Output("void_debug", "children", allow_duplicate=True),
    Input({"type": "mat_edit_btn", "idx": ALL}, "n_clicks"),
    State("materials_modal_store", "data"),
    State({"type": "mat_edit_btn", "idx": ALL}, "id"),
    prevent_initial_call=True
)
def _load_item_for_edit(_clicks, items, btn_ids):
    if not ctx.triggered_id or not isinstance(ctx.triggered_id, dict):
        raise dash.exceptions.PreventUpdate

    trg = ctx.triggered_id  # {"type":"mat_edit_btn","idx":N}
    pos = None
    for i, _id in enumerate(btn_ids or []):
        if _id.get("idx") == trg.get("idx"):
            pos = i
            break

    if pos is None or not _clicks or pos >= len(_clicks) or (_clicks[pos] or 0) <= 0:
        raise dash.exceptions.PreventUpdate

    items = items or []
    idx = trg.get("idx")
    if idx is None or idx < 0 or idx >= len(items):
        raise dash.exceptions.PreventUpdate

    it = items[idx]
    dbg = _dbg("EDIT_LOAD", idx=idx, current_len=len(items))
    return it.get("material_id"), it.get("lote_id"), it.get("quantidade"), idx, False, dbg

# 8) Atualizar item (no MODAL)
@dash.callback(
    Output("materials_modal_store", "data", allow_duplicate=True),
    Output("materials_modal_feedback", "children", allow_duplicate=True),
    Output("mat_sel_id", "value", allow_duplicate=True),
    Output("mat_sel_lote", "value", allow_duplicate=True),
    Output("mat_sel_qtd", "value", allow_duplicate=True),
    Output("materials_edit_index", "data", allow_duplicate=True),
    Output("mat_update_btn", "disabled", allow_duplicate=True),
    Output("dbg_last_event", "children", allow_duplicate=True) if DEBUG else Output("void_debug", "children", allow_duplicate=True),
    Input("mat_update_btn", "n_clicks"),
    State("materials_edit_index", "data"),
    State("materials_modal_store", "data"),
    State("mat_sel_id", "value"),
    State("mat_sel_lote", "value"),
    State("mat_sel_qtd", "value"),
    prevent_initial_call=True
)
def _update_item(n, edit_idx, items, mat_id, lote_id, qtd):
    if not n or edit_idx is None:
        raise dash.exceptions.PreventUpdate

    before_len = len(items or [])
    errors = []
    if not mat_id:
        errors.append("Selecione um material.")
    try:
        q = _parse_qty(qtd)
        if q <= 0:
            errors.append("Quantidade deve ser maior que zero.")
    except Exception:
        q = 0.0
        errors.append("Quantidade inválida.")

    lote_norm = int(lote_id) if (HAS_BATCHES and lote_id not in (None, "", "null")) else None

    if HAS_BATCHES and (lote_norm is not None):
        b = next((x for x in list_material_batches(int(mat_id)) if x.get("id") == lote_norm), None)
        if not b:
            errors.append("Lote inválido.")
        else:
            # somatório do mesmo item (excluindo o próprio) + novo q
            current = 0.0
            for i, it in enumerate(items or []):
                if i == int(edit_idx):
                    continue
                if int(it.get("material_id")) == int(mat_id) and (it.get("lote_id") or None) == lote_norm:
                    current += float(it.get("quantidade") or 0.0)
            if current + q > float(b.get("saldo") or 0.0) + 1e-9:
                errors.append(f"Saldo insuficiente no lote. Disponível: {b.get('saldo')}.")

    if errors:
        dbg = _dbg("UPDATE_FAIL", before=before_len, errors=len(errors))
        return no_update, dbc.Alert(html.Ul([html.Li(e) for e in errors]), color="danger"), no_update, no_update, no_update, no_update, no_update, dbg

    items = list(items or [])
    if edit_idx < 0 or edit_idx >= len(items):
        raise dash.exceptions.PreventUpdate
    items[int(edit_idx)] = {"material_id": int(mat_id), "lote_id": lote_norm, "quantidade": q}
    dbg = _dbg("UPDATE_OK", idx=int(edit_idx), len=len(items))
    return items, dbc.Alert("Item atualizado.", color="success"), None, None, None, None, True, dbg

# 9) Click em REMOVER → abre modal de confirmação
@dash.callback(
    Output("confirm_del_modal", "is_open", allow_duplicate=True),
    Output("delete_pending_index", "data", allow_duplicate=True),
    Output("dbg_last_event", "children", allow_duplicate=True) if DEBUG else Output("void_debug", "children", allow_duplicate=True),
    Input({"type": "mat_del_btn", "idx": ALL}, "n_clicks"),
    State({"type": "mat_del_btn", "idx": ALL}, "id"),
    prevent_initial_call=True
)
def _open_confirm_delete(_clicks, btn_ids):
    if not ctx.triggered_id or not isinstance(ctx.triggered_id, dict):
        raise dash.exceptions.PreventUpdate
    trg = ctx.triggered_id
    # localizar pos e checar clique real
    pos = None
    for i, _id in enumerate(btn_ids or []):
        if _id.get("idx") == trg.get("idx"):
            pos = i
            break
    if pos is None or not _clicks or pos >= len(_clicks) or (_clicks[pos] or 0) <= 0:
        raise dash.exceptions.PreventUpdate
    dbg = _dbg("DELETE_PROMPT", idx=trg.get("idx"))
    return True, trg.get("idx"), dbg

# 9b) Confirmar remoção
@dash.callback(
    Output("materials_modal_store", "data", allow_duplicate=True),
    Output("confirm_del_modal", "is_open", allow_duplicate=True),
    Output("delete_pending_index", "data", allow_duplicate=True),
    Output("dbg_last_event", "children", allow_duplicate=True) if DEBUG else Output("void_debug", "children", allow_duplicate=True),
    Input("confirm_del_btn", "n_clicks"),
    State("delete_pending_index", "data"),
    State("materials_modal_store", "data"),
    prevent_initial_call=True
)
def _confirm_delete(n, idx, items):
    if not n:
        raise dash.exceptions.PreventUpdate
    items = list(items or [])
    if idx is None or idx < 0 or idx >= len(items):
        raise dash.exceptions.PreventUpdate
    before = len(items)
    del items[int(idx)]
    dbg = _dbg("DELETE_OK", idx=int(idx), before=before, after=len(items))
    return items, False, None, dbg

# 9c) Cancelar remoção
@dash.callback(
    Output("confirm_del_modal", "is_open", allow_duplicate=True),
    Output("delete_pending_index", "data", allow_duplicate=True),
    Input("cancel_del_btn", "n_clicks"),
    prevent_initial_call=True
)
def _cancel_delete(n):
    if not n:
        raise dash.exceptions.PreventUpdate
    return False, None

# 10) Limpar seleção de campos (não mexe nas listas)
@dash.callback(
    Output("mat_sel_id", "value", allow_duplicate=True),
    Output("mat_sel_lote", "value", allow_duplicate=True),
    Output("mat_sel_qtd", "value", allow_duplicate=True),
    Output("materials_edit_index", "data", allow_duplicate=True),
    Output("mat_update_btn", "disabled", allow_duplicate=True),
    Output("dbg_last_event", "children", allow_duplicate=True) if DEBUG else Output("void_debug", "children", allow_duplicate=True),
    Input("mat_clear_btn", "n_clicks"),
    prevent_initial_call=True
)
def _clear_sel(n):
    if not n:
        raise dash.exceptions.PreventUpdate
    dbg = _dbg("CLEAR_FIELDS")
    return None, None, None, None, True, dbg

# 11) CONCLUIR no modal → valida somatórios com saldo (bloqueia se insuficiente) e aplica
@dash.callback(
    Output("materials_selected_store", "data", allow_duplicate=True),
    Output("materials_modal", "is_open", allow_duplicate=True),
    Output("materials_modal_feedback", "children", allow_duplicate=True),
    Output("dbg_last_event", "children", allow_duplicate=True) if DEBUG else Output("void_debug", "children", allow_duplicate=True),
    Input("materials_done_btn", "n_clicks"),
    State("materials_modal_store", "data"),
    prevent_initial_call=True
)
def _apply_modal_selection(n, modal_items):
    if not n:
        raise dash.exceptions.PreventUpdate
    items = list(modal_items or [])

    # Validação de saldo por material/lote (inclui sem lote: soma total <= saldo total)
    if HAS_BATCHES and items:
        # Mapas: por material -> {None: qtd_sem_lote, lote_id: qtd}
        agg = {}
        for it in items:
            mid = int(it.get("material_id"))
            lid = it.get("lote_id")
            q = float(it.get("quantidade") or 0.0)
            d = agg.setdefault(mid, {})
            d[lid] = d.get(lid, 0.0) + q

        errors = []
        for mid, by_lote in agg.items():
            batches = list_material_batches(mid)
            saldo_tot = sum(float(b.get("saldo") or 0.0) for b in batches)
            qtd_sem_lote = by_lote.get(None, 0.0)
            # Checar cada lote específico
            for b in batches:
                lid = b.get("id")
                req = by_lote.get(lid, 0.0)
                if req > float(b.get("saldo") or 0.0) + 1e-9:
                    errors.append(f"Material ID {mid}: lote {b.get('lote','-')} excede saldo ({req} > {b.get('saldo')}).")
            # Checar total
            req_total = sum(v for k, v in by_lote.items() if k is not None) + qtd_sem_lote
            if req_total > saldo_tot + 1e-9:
                errors.append(f"Material ID {mid}: quantidade total selecionada ({req_total}) excede saldo total ({saldo_tot}).")

        if errors:
            msg = dbc.Alert(html.Ul([html.Li(e) for e in errors]), color="danger")
            dbg = _dbg("APPLY_MODAL_FAIL", errors=len(errors))
            return no_update, no_update, msg, dbg

    dbg = _dbg("APPLY_MODAL", count=len(items))
    return items, False, "", dbg

# 12) Salvar exame (usa itens confirmados) → backend faz baixa/LIFO por lote/FIFO sem duplicar → limpa store e recarrega
@dash.callback(
    Output("save_feedback", "children"),
    Output("materials_selected_store", "data", allow_duplicate=True),
    Output("materials_modal", "is_open", allow_duplicate=True),
    Output("after_save_interval", "disabled", allow_duplicate=True),
    Output("dbg_last_event", "children", allow_duplicate=True) if DEBUG else Output("void_debug", "children", allow_duplicate=True),
    Input("btn_salvar", "n_clicks"),
    State("exam_id", "value"),
    State("modalidade", "value"),
    State("exame_auto", "value"),
    State("data_dt", "value"),
    State("medico_auto", "value"),
    State("idade", "value"),
    State("materials_selected_store", "data"),
    prevent_initial_call=True
)
def _save_exam(n, exam_id, modalidade, exame_nome, data_dt, medico, idade, materiais):
    if not n:
        return no_update, no_update, no_update, no_update, no_update
    if not exam_id or not modalidade or not exame_nome:
        return dbc.Alert("Preencha Exam ID, Modalidade e Exame.", color="danger"), no_update, no_update, no_update, _dbg("SAVE_FAIL_VALIDATION")

    # Data/hora: aceita passado, NUNCA futuro (clamp para agora)
    try:
        dt_iso = _clamp_future_to_now(data_dt)
    except Exception:
        dt_iso = _now_utc_iso()

    safe_items = []
    for x in (materiais or []):
        if x and x.get("material_id"):
            safe_items.append({
                "material_id": int(x["material_id"]),
                "lote_id": int(x["lote_id"]) if (HAS_BATCHES and x.get("lote_id") not in (None, "", "null")) else None,
                "quantidade": float(x.get("quantidade") or 0.0),
            })

    # Segurança extra (frente): revalida estoque por lote/total quando houver batches
    if HAS_BATCHES and safe_items:
        agg = {}
        for it in safe_items:
            mid = int(it.get("material_id")); lid = it.get("lote_id"); q = float(it.get("quantidade") or 0.0)
            d = agg.setdefault(mid, {}); d[lid] = d.get(lid, 0.0) + q
        for mid, by_lote in agg.items():
            batches = list_material_batches(mid)
            saldo_tot = sum(float(b.get("saldo") or 0.0) for b in batches)
            for b in batches:
                lid = b.get("id"); req = by_lote.get(lid, 0.0)
                if req > float(b.get("saldo") or 0.0) + 1e-9:
                    return dbc.Alert("Saldo insuficiente (verifique lotes).", color="danger"), no_update, no_update, no_update, _dbg("SAVE_FAIL_STOCK")
            req_total = sum(v for k, v in by_lote.items() if k is not None) + by_lote.get(None, 0.0)
            if req_total > saldo_tot + 1e-9:
                return dbc.Alert("Saldo total insuficiente.", color="danger"), no_update, no_update, no_update, _dbg("SAVE_FAIL_STOCK")

    exam = {
        "id": None,
        "exam_id": exam_id,
        "modalidade": modalidade,
        "exame": f"{MOD_LABEL.get(modalidade, modalidade)} - {exame_nome}",
        "medico": (medico or "").strip(),
        "data_hora": dt_iso,
        "idade": int(idade) if idade not in (None, "") else None,
        "user_email": "",
        "materiais_usados": safe_items
    }

    try:
        # <<< AQUI É O PULO DO GATO: backend já consome estoque por lote/FIFO sem duplicar >>>
        ex_id = add_or_update_exam(exam)
        if medico:
            ensure_doctor(medico)

        msg = dbc.Alert(
            [
                html.I(className="fa-regular fa-circle-check me-2"),
                f"Exame salvo (ID interno {ex_id}). Estoque baixado automaticamente por lote/FIFO."
            ],
            color="success"
        )
        dbg = _dbg("SAVE_OK", itens=len(safe_items))
        # habilita intervalo para recarregar
        return msg, [], False, False, dbg

    except Exception as e:
        dbg = _dbg("SAVE_ERROR", err=str(e))
        return dbc.Alert(f"Erro ao salvar: {e}", color="danger"), no_update, no_update, no_update, dbg

# 13) Após intervalo, recarrega/realoca a página atual
@dash.callback(
    Output("page_redirect", "href", allow_duplicate=True),
    Output("after_save_interval", "disabled", allow_duplicate=True),
    Input("after_save_interval", "n_intervals"),
    State("_pages_location", "pathname"),
    prevent_initial_call=True
)
def _do_redirect(n, pathname):
    if not n or n < 1:
        raise dash.exceptions.PreventUpdate
    # Recarrega a própria rota (respeita prefixo do app)
    href = pathname or "/cadastro"
    return href, True
