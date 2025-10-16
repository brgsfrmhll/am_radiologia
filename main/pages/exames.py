# pages/exames.py
import csv
import io
from datetime import datetime, time

import dash
from dash import html, dcc, Input, Output, State, no_update, ctx
import dash_bootstrap_components as dbc
import dash_mantine_components as dmc  # mantido só para Autocomplete/Textarea

dash.register_page(__name__, path="/exames", name="Exames")

# ========= Backend =========
from core.backend import (
    list_exams, add_or_update_exam, ensure_doctor,
    MODALIDADES, MOD_LABEL, get_examtype_names, doctor_names,
    list_materials, material_price_map, add_stock_movement, format_dt_br
)

# Controle por lote (opcional)
HAS_BATCHES = False
try:
    from core.backend import list_material_batches
    HAS_BATCHES = True
except Exception:
    def list_material_batches(_material_id: int):
        return []

# ========= Helpers =========
def _fmt_money(v):
    return f"R$ {float(v or 0):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

def _parse_iso(s):
    if not s:
        return None
    try:
        return datetime.fromisoformat(str(s).replace("Z", ""))
    except Exception:
        return None

def _parse_date_or_iso(s, end_of_day=False):
    """Aceita 'YYYY-MM-DD' (date) ou ISO completo. Retorna datetime."""
    if not s:
        return None
    s = str(s).strip()
    # date apenas
    if len(s) == 10 and s[4] == "-" and s[7] == "-":
        try:
            d = datetime.fromisoformat(s)
            return datetime.combine(d.date(), time.max if end_of_day else time.min)
        except Exception:
            return None
    return _parse_iso(s)

def _iso_to_input_dt(dt_iso):
    """Converte ISO -> 'YYYY-MM-DDTHH:MM' para <input type=datetime-local>."""
    try:
        dt = _parse_iso(dt_iso)
        if not dt:
            return None
        return dt.strftime("%Y-%m-%dT%H:%M")
    except Exception:
        return None

def _clamp_future_to_now(dt_str_or_iso: str | None) -> str:
    """Aceita 'YYYY-MM-DDTHH:MM' ou ISO. Retorna ISO, nunca futuro (com base em UTC)."""
    now = datetime.utcnow()
    if not dt_str_or_iso:
        return now.isoformat()
    s = dt_str_or_iso.replace("Z", "")
    try:
        # suporta datetime-local sem segundos
        if "T" in s and len(s) == 16:
            dt = datetime.strptime(s, "%Y-%m-%dT%H:%M")
        else:
            dt = datetime.fromisoformat(s)
    except Exception:
        return now.isoformat()
    return dt.isoformat() if dt <= now else now.isoformat()

def _examname_only(full: str) -> str:
    if not full:
        return ""
    parts = str(full).split(" - ", 1)
    return parts[1] if len(parts) == 2 else full

def _doctor_suggestions():
    base = set(x for x in (doctor_names() or []) if x)
    for e in list_exams():
        m = (e.get("medico") or "").strip()
        if m:
            base.add(m)
    return sorted(base)

def _exam_suggestions_for_mod(mod_val):
    base = set(x for x in (get_examtype_names(mod_val) or []) if x)
    if mod_val:
        for e in list_exams():
            if e.get("modalidade") == mod_val:
                nm = _examname_only(e.get("exame"))
                if nm:
                    base.add(nm)
    return sorted(base)

def _filter_exams(data, mod, exam, doc, dt_ini, dt_fim, text):
    out = []
    dt_i = _parse_date_or_iso(dt_ini, end_of_day=False) if dt_ini else None
    dt_f = _parse_date_or_iso(dt_fim, end_of_day=True) if dt_fim else None
    text = (text or "").strip().lower()
    for e in data:
        if mod and e.get("modalidade") != mod:
            continue
        if exam:
            if exam.lower() not in (e.get("exame") or "").lower():
                continue
        if doc:
            if doc.lower() not in (e.get("medico") or "").lower():
                continue
        if dt_i or dt_f:
            ed = _parse_iso(e.get("data_hora"))
            if not ed:
                continue
            if dt_i and ed < dt_i:
                continue
            if dt_f and ed > dt_f:
                continue
        if text:
            blob = " ".join([
                str(e.get("id") or ""),
                str(e.get("exam_id") or ""),
                str(e.get("modalidade") or ""),
                str(e.get("exame") or ""),
                str(e.get("medico") or ""),
                str(e.get("observacao") or ""),  # inclui observação na busca livre
            ]).lower()
            if text not in blob:
                continue
        out.append(e)
    out.sort(key=lambda r: _parse_iso(r.get("data_hora")) or datetime.min, reverse=True)
    return out

def _row_actions(exid: int, cancelado: bool):
    if cancelado:
        return html.Div([
            dbc.Badge("Cancelado", color="danger", className="me-2"),
            html.Small("— sem ações", className="text-muted"),
        ])
    return html.Div(
        [
            dbc.Button(html.I(className="fa-solid fa-pen"),
                       id={"role": "edit", "exid": exid},
                       color="secondary", outline=True, size="sm",
                       className="me-1", title="Editar dados"),
            dbc.Button([html.I(className="fa-solid fa-flask me-2"), "Materiais"],
                       id={"role": "materials", "exid": exid},
                       color="info", size="sm", className="me-1", title="Gerenciar materiais"),
            dbc.Button([html.I(className="fa-solid fa-ban me-2"), "Cancelar"],
                       id={"role": "cancel_exam", "exid": exid},
                       color="danger", outline=True, size="sm", title="Cancelar exame"),
        ],
        className="d-flex"
    )

def _materials_table(items):
    header = html.Thead(html.Tr([
        html.Th("#"), html.Th("Material"),
        html.Th("Lote"), html.Th("Validade") if HAS_BATCHES else None,
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
                dbc.Button("Editar", id={"type": "mat_edit_btn_x", "idx": idx}, size="sm", className="me-1"),
                dbc.Button("Remover", id={"type": "mat_del_btn_x", "idx": idx}, size="sm", color="danger"),
            ]))
        ]
        body.append(html.Tr([c for c in row if c is not None]))
    return dbc.Table([header, html.Tbody(body)], bordered=True, hover=True, striped=True,
                     responsive=True, className="align-middle")

def _materials_summary(items):
    items = items or []
    prices = material_price_map()
    total_cost = 0.0
    for it in items:
        mid = int(it.get("material_id"))
        qty = float(it.get("quantidade") or 0.0)
        unit_cost = float(prices.get(mid, 0.0))
        total_cost += unit_cost * qty
    return html.Div([
        html.Div(f"Itens: {len(items)}", className="small"),
        html.Div(f"Custo estimado: {_fmt_money(total_cost)}", className="small fw-semibold"),
    ])

def _truncate(text: str, max_chars=60) -> str:
    t = (text or "").strip()
    return t if len(t) <= max_chars else t[:max_chars - 1] + "…"

# ========= Layout =========
def filters_bar():
    # Filtros com inputs nativos (limpos): data (De/Até) usando type="date"
    return dbc.Card(
        dbc.CardBody([
            dbc.Row([
                dbc.Col(dcc.Dropdown(
                    id="ex_f_mod",
                    options=[{"label": MOD_LABEL.get(m, m), "value": m} for m in MODALIDADES],
                    placeholder="Modalidade",
                    clearable=True
                ), md=2),
                dbc.Col(dmc.Autocomplete(
                    id="ex_f_exam",
                    data=[],
                    placeholder="Exame (por modalidade)",
                    limit=100,
                    clearable=True,
                ), md=3),
                dbc.Col(dmc.Autocomplete(
                    id="ex_f_doc",
                    data=_doctor_suggestions(),
                    placeholder="Médico",
                    limit=100,
                    clearable=True,
                ), md=3),
                dbc.Col(dbc.Input(id="ex_f_text", placeholder="Busca livre (ID, Exam ID, exame, médico, observação)"), md=4),
            ], className="g-2 mb-2"),

            dbc.Row([
                dbc.Col(html.Div([
                    html.Small("De", className="text-muted d-block mb-1"),
                    dbc.Input(id="ex_dt_ini", type="date"),
                ]), md=2),
                dbc.Col(html.Div([
                    html.Small("Até", className="text-muted d-block mb-1"),
                    dbc.Input(id="ex_dt_fim", type="date"),
                ]), md=2),
                dbc.Col(dbc.Button([html.I(className="fa-solid fa-magnifying-glass me-2"), "Filtrar"],
                                   id="ex_btn_filter", color="primary", className="w-100"), md=2),
                dbc.Col(dbc.Button([html.I(className="fa-solid fa-eraser me-2"), "Limpar"],
                                   id="ex_btn_clear", color="secondary", outline=True, className="w-100"), md=2),
                dbc.Col(dbc.Button([html.I(className="fa-solid fa-file-csv me-2"), "Exportar CSV"],
                                   id="ex_btn_export", color="success", className="w-100"), md=2),
                dbc.Col(html.Div(id="ex_feedback"), md=2),
            ], className="g-2"),
            dcc.Download(id="ex_download"),
        ]),
        className="mb-3 shadow-sm"
    )

def table_card():
    return dbc.Card([
        dbc.CardHeader(html.Div([html.I(className="fa-regular fa-clipboard me-2"),
                                 html.Strong("Exames cadastrados")], className="d-flex align-items-center")),
        dbc.CardBody(html.Div(id="ex_table"))
    ], className="shadow-sm")

# ===== Modal único de Materiais (para o exame selecionado) =====
def materials_modal():
    hide_style = {"display": "none"} if not HAS_BATCHES else {}
    return dbc.Modal(
        id="ex_materials_modal", is_open=False, size="xl", centered=True,
        children=[
            dbc.ModalHeader(dbc.ModalTitle([html.I(className="fa-solid fa-vial me-2"),
                                            "Materiais do exame"])),
            dbc.ModalBody([
                dbc.Alert(id="ex_mat_summary", color="light", className="p-2"),
                dbc.Row([
                    dbc.Col([
                        html.Label("Material"),
                        dcc.Dropdown(id="ex_mat_sel_id", options=[], placeholder="Selecione um material", clearable=True),
                    ], md=4 if HAS_BATCHES else 6),
                    dbc.Col([
                        html.Label("Lote / Validade (Saldo)"),
                        dcc.Dropdown(
                            id="ex_mat_sel_lote",
                            options=[],
                            placeholder="Selecione um lote (opcional)" if HAS_BATCHES else "",
                            clearable=True,
                            style={"minWidth": "380px"},
                        ),
                    ], md=6, style=hide_style),
                    dbc.Col([
                        html.Label("Quantidade"),
                        dbc.Input(id="ex_mat_sel_qtd", type="number", step=0.01, min=0, placeholder="Ex.: 10 / 80.0"),
                    ], md=2 if HAS_BATCHES else 6),
                ], className="mb-2 g-2"),

                html.Div(className="d-flex align-items-center gap-2 mb-3", children=[
                    dbc.Badge(id="ex_mat_sel_un_badge", color="light", className="text-dark"),
                    dbc.Badge(id="ex_mat_sel_preco_badge", color="light", className="text-dark"),
                    dbc.Badge(id="ex_mat_sel_saldo_badge", color="light", className="text-dark", style=hide_style),
                    dbc.Button([html.I(className="fa-solid fa-plus me-2"), "Adicionar"], id="ex_mat_add_btn",
                               color="primary", className="ms-auto"),
                    dbc.Button([html.I(className="fa-solid fa-rotate me-2"), "Atualizar item"], id="ex_mat_update_btn",
                               color="success", disabled=True),
                    dbc.Button([html.I(className="fa-regular fa-circle-xmark me-2"), "Limpar seleção"],
                               id="ex_mat_clear_btn", color="secondary", outline=True),
                    html.Div(id="ex_mat_feedback", className="ms-2"),
                ]),

                dbc.Card([
                    dbc.CardHeader([html.I(className="fa-solid fa-list-check me-2"),
                                    "Itens do exame (modal)"]),
                    dbc.CardBody(html.Div(id="ex_materials_table", className="table-responsive"))
                ]),
            ]),
            dbc.ModalFooter([
                dbc.Button("Fechar", id="ex_materials_close_btn", className="me-2"),
                dbc.Button([html.I(className="fa-solid fa-check me-2"), "Concluir"],
                           id="ex_materials_done_btn", color="primary")
            ])
        ]
    )

def confirm_delete_modal():
    return dbc.Modal(
        id="ex_confirm_del_modal", is_open=False, centered=True,
        children=[
            dbc.ModalHeader(dbc.ModalTitle("Remover item?")),
            dbc.ModalBody("Essa ação não pode ser desfeita."),
            dbc.ModalFooter([
                dbc.Button("Cancelar", id="ex_cancel_del_btn", className="me-2"),
                dbc.Button([html.I(className="fa-solid fa-trash-can me-2"), "Remover"],
                           id="ex_confirm_del_btn", color="danger"),
            ])
        ]
    )

def cancel_exam_modal():
    return dbc.Modal(
        id="ex_cancel_modal", is_open=False, centered=True,
        children=[
            dbc.ModalHeader(dbc.ModalTitle("Cancelar exame")),
            dbc.ModalBody([
                html.Div("Confirmar cancelamento do exame?"),
                html.Small("Todos os materiais serão estornados ao estoque e o exame ficará marcado como cancelado.",
                           className="text-muted d-block mt-1"),
            ]),
            dbc.ModalFooter([
                dbc.Button("Fechar", id="ex_cancel_close_btn", className="me-2"),
                dbc.Button([html.I(className="fa-solid fa-ban me-2"), "Cancelar exame"],
                           id="ex_cancel_confirm_btn", color="danger"),
            ])
        ]
    )

def observation_modal():
    return dbc.Modal(
        id="ex_obs_modal", is_open=False, centered=True, size="lg",
        children=[
            dbc.ModalHeader(dbc.ModalTitle([html.I(className="fa-regular fa-note-sticky me-2"),
                                            "Observação do Exame"])),
            dbc.ModalBody([
                html.Div(id="ex_obs_header", className="mb-2 text-muted"),
                dmc.Textarea(
                    id="ex_obs_textarea",
                    placeholder="Digite a observação...",
                    autosize=True,
                    minRows=4, maxRows=14
                )
            ]),
            dbc.ModalFooter([
                dbc.Button("Fechar", id="ex_obs_close_btn", className="me-2"),
                dbc.Button([html.I(className="fa-solid fa-check me-2"), "Salvar observação"],
                           id="ex_obs_save_btn", color="primary"),
            ])
        ]
    )

layout = dbc.Container(
    [
        filters_bar(),
        table_card(),
        materials_modal(),
        confirm_delete_modal(),
        cancel_exam_modal(),
        observation_modal(),
        # Stores de estado
        dcc.Store(id="ex_editing_id", data=None),            # linha em edição (id do exame)
        dcc.Store(id="ex_refresh", data=""),                 # sinal de recarregar tabela
        dcc.Store(id="ex_current_id", data=None),            # exame atual para modal de materiais
        dcc.Store(id="ex_mat_store", data=[]),               # itens no modal (buffer)
        dcc.Store(id="ex_mat_original", data=[]),            # itens originais do exame (para diff)
        dcc.Store(id="ex_mat_edit_index", data=None),        # índice em edição no modal
        dcc.Store(id="ex_del_index", data=None),             # índice aguardando confirmação de remoção
        dcc.Store(id="ex_cancel_id", data=None),             # exame que será cancelado
        dcc.Store(id="ex_obs_id", data=None),                # exame cujo obs está sendo editado
    ],
    fluid=True
)

# ========= Callbacks =========

# (1) Carrega opções do Autocomplete de exame conforme modalidade do filtro
@dash.callback(
    Output("ex_f_exam", "data"),
    Input("ex_f_mod", "value"),
)
def _fill_exam_filter(mod_val):
    return _exam_suggestions_for_mod(mod_val)

# (2) Limpar filtros
@dash.callback(
    Output("ex_f_mod", "value"),
    Output("ex_f_exam", "value"),
    Output("ex_f_doc", "value"),
    Output("ex_f_text", "value"),
    Output("ex_dt_ini", "value"),
    Output("ex_dt_fim", "value"),
    Input("ex_btn_clear", "n_clicks"),
    prevent_initial_call=True
)
def _clear_filters(n):
    if not n:
        raise dash.exceptions.PreventUpdate
    return None, None, None, "", None, None

# (3) Render da tabela
def _render_table(rows, editing_id):
    header = html.Thead(html.Tr([
        html.Th("ID"), html.Th("Exam ID"), html.Th("Modalidade"), html.Th("Exame"),
        html.Th("Médico"), html.Th("Data/Hora"), html.Th("Idade"), html.Th("Observação"), html.Th("Ações")
    ]))
    body = []
    for e in rows:
        exid = e.get("id")
        cancelado = bool(e.get("cancelado") or False)
        row_class = "table-danger" if cancelado else None

        if exid == editing_id and not cancelado:
            cur_mod = e.get("modalidade")
            cur_exam = _examname_only(e.get("exame"))
            cur_doc = e.get("medico")
            cur_dt = _iso_to_input_dt(e.get("data_hora"))
            cur_age = e.get("idade")
            obs_full = (e.get("observacao") or "").strip()
            obs_view = _truncate(obs_full, max_chars=60)

            row = html.Tr([
                html.Td(exid),
                html.Td(dbc.Input(
                    id={"type": "ex_field", "name": "examid", "exid": exid},
                    value=e.get("exam_id") or "", placeholder="EX-0001")),
                html.Td(dcc.Dropdown(
                    id={"type": "ex_field", "name": "mod", "exid": exid},
                    options=[{"label": MOD_LABEL.get(m, m), "value": m} for m in MODALIDADES],
                    value=cur_mod, clearable=False, style={"minWidth": "160px"}
                )),
                html.Td(dmc.Autocomplete(
                    id={"type": "ex_field", "name": "exam", "exid": exid},
                    data=_exam_suggestions_for_mod(cur_mod),
                    value=cur_exam,
                    placeholder="Exame",
                    limit=100, clearable=True,
                    style={"minWidth": "220px"}
                )),
                html.Td(dmc.Autocomplete(
                    id={"type": "ex_field", "name": "doc", "exid": exid},
                    data=_doctor_suggestions(),
                    value=cur_doc or "",
                    placeholder="Médico", limit=100, clearable=True,
                    style={"minWidth": "220px"}
                )),
                html.Td(dbc.Input(
                    id={"type": "ex_field", "name": "dt", "exid": exid},
                    type="datetime-local",
                    value=cur_dt
                )),
                html.Td(dbc.Input(
                    id={"type": "ex_field", "name": "age", "exid": exid},
                    type="number", min=0, max=120, value=cur_age)),
                html.Td(
                    html.Div(className="d-flex align-items-center gap-2", children=[
                        html.Span(obs_view, title=obs_full, className="text-truncate", style={"maxWidth": "220px"}),
                        dbc.Button("Obs.", id={"role": "obs", "exid": exid}, size="sm", color="secondary", outline=True)
                    ])
                ),
                html.Td(html.Div([
                    dbc.Button([html.I(className="fa-solid fa-check me-1"), "Salvar"],
                               id={"type": "ex_btn", "role": "save", "exid": exid},
                               color="success", size="sm", className="me-1"),
                    dbc.Button([html.I(className="fa-solid fa-xmark me-1"), "Cancelar"],
                               id={"type": "ex_btn", "role": "cancel", "exid": exid},
                               color="secondary", outline=True, size="sm"),
                ], className="d-flex"))
            ], className=row_class)
        else:
            obs_full = (e.get("observacao") or "").strip()
            obs_view = _truncate(obs_full, max_chars=60)
            row = html.Tr([
                html.Td(exid),
                html.Td(e.get("exam_id")),
                html.Td(MOD_LABEL.get(e.get("modalidade"), e.get("modalidade"))),
                html.Td([
                    e.get("exame"),
                    dbc.Badge(" Cancelado", color="danger", className="ms-2") if cancelado else None
                ]),
                html.Td(e.get("medico")),
                html.Td(format_dt_br(e.get("data_hora"))),
                html.Td(e.get("idade")),
                html.Td(
                    html.Div(className="d-flex align-items-center gap-2", children=[
                        html.Span(obs_view, title=obs_full, className="text-truncate", style={"maxWidth": "220px"}),
                        dbc.Button("Obs.", id={"role": "obs", "exid": exid}, size="sm", color="secondary", outline=True,
                                   disabled=bool(e.get("cancelado")))
                    ])
                ),
                html.Td(_row_actions(exid, cancelado))
            ], className=row_class)
        body.append(row)
    return dbc.Table([header, html.Tbody(body)], bordered=True, hover=True, striped=True,
                     responsive=True, className="align-middle w-100")

@dash.callback(
    Output("ex_table", "children"),
    Input("ex_btn_filter", "n_clicks"),
    Input("ex_refresh", "data"),
    Input("ex_editing_id", "data"),
    State("ex_f_mod", "value"),
    State("ex_f_exam", "value"),
    State("ex_f_doc", "value"),
    State("ex_dt_ini", "value"),
    State("ex_dt_fim", "value"),
    State("ex_f_text", "value"),
    prevent_initial_call=False
)
def _build_table(_n, _refresh, editing_id, mod, exam, doc, dt_ini, dt_fim, text):
    data = list_exams()
    rows = _filter_exams(data, mod, exam, doc, dt_ini, dt_fim, text)
    return _render_table(rows, editing_id)

# (4) Sugestões de exame quando muda modalidade NA LINHA EM EDIÇÃO (pattern/MATCH)
@dash.callback(
    Output({"type": "ex_field", "name": "exam", "exid": dash.MATCH}, "data"),
    Input({"type": "ex_field", "name": "mod",  "exid": dash.MATCH}, "value"),
    prevent_initial_call=True
)
def _update_exam_suggestions_row(mod_val):
    return _exam_suggestions_for_mod(mod_val)

# (5) Botões ✏️ (editar) e Cancelar
@dash.callback(
    Output("ex_editing_id", "data", allow_duplicate=True),
    Input({"role": "edit", "exid": dash.ALL}, "n_clicks"),
    Input({"type": "ex_btn", "role": "cancel", "exid": dash.ALL}, "n_clicks"),
    State("ex_editing_id", "data"),
    State({"role": "edit", "exid": dash.ALL}, "id"),
    State({"type": "ex_btn", "role": "cancel", "exid": dash.ALL}, "id"),
    prevent_initial_call=True
)
def _toggle_edit(n_edit_list, n_cancel_list, cur_editing, edit_ids, cancel_ids):
    trg = ctx.triggered_id
    # valida clique real do botão correspondente
    if isinstance(trg, dict) and trg.get("role") == "edit":
        pos = None
        for i, bid in enumerate(edit_ids or []):
            if bid.get("exid") == trg.get("exid"):
                pos = i
                break
        if pos is None or not n_edit_list or pos >= len(n_edit_list) or (n_edit_list[pos] or 0) <= 0:
            raise dash.exceptions.PreventUpdate
        return trg.get("exid")
    elif isinstance(trg, dict) and trg.get("role") == "cancel":
        pos = None
        for i, bid in enumerate(cancel_ids or []):
            if bid.get("exid") == trg.get("exid"):
                pos = i
                break
        if pos is None or not n_cancel_list or pos >= len(n_cancel_list) or (n_cancel_list[pos] or 0) <= 0:
            raise dash.exceptions.PreventUpdate
        return None
    raise dash.exceptions.PreventUpdate

# (6) Salvar linha editada (sem observação; observação é salva no modal próprio)
@dash.callback(
    Output("ex_feedback", "children", allow_duplicate=True),
    Output("ex_editing_id", "data", allow_duplicate=True),
    Output("ex_refresh", "data", allow_duplicate=True),
    Input({"type": "ex_btn", "role": "save", "exid": dash.ALL}, "n_clicks"),
    State({"type": "ex_field", "name": "mod",    "exid": dash.ALL}, "value"),
    State({"type": "ex_field", "name": "mod",    "exid": dash.ALL}, "id"),
    State({"type": "ex_field", "name": "exam",   "exid": dash.ALL}, "value"),
    State({"type": "ex_field", "name": "exam",   "exid": dash.ALL}, "id"),
    State({"type": "ex_field", "name": "doc",    "exid": dash.ALL}, "value"),
    State({"type": "ex_field", "name": "doc",    "exid": dash.ALL}, "id"),
    State({"type": "ex_field", "name": "dt",     "exid": dash.ALL}, "value"),
    State({"type": "ex_field", "name": "dt",     "exid": dash.ALL}, "id"),
    State({"type": "ex_field", "name": "age",    "exid": dash.ALL}, "value"),
    State({"type": "ex_field", "name": "age",    "exid": dash.ALL}, "id"),
    State({"type": "ex_field", "name": "examid", "exid": dash.ALL}, "value"),
    State({"type": "ex_field", "name": "examid", "exid": dash.ALL}, "id"),
    prevent_initial_call=True
)
def _save_row(n_list,
              mods, mod_ids, exams, exam_ids, docs, doc_ids, dts, dt_ids, ages, age_ids, exids, exid_ids):
    trg = ctx.triggered_id
    if not isinstance(trg, dict) or trg.get("role") != "save":
        raise dash.exceptions.PreventUpdate
    # garante clique real no botão save correspondente
    pos = None
    for i, bid in enumerate(exid_ids or []):
        if bid.get("exid") == trg.get("exid"):
            pos = i
            break
    if pos is None or not n_list or pos >= len(n_list) or (n_list[pos] or 0) <= 0:
        raise dash.exceptions.PreventUpdate

    exid = trg.get("exid")

    def pick(vals, ids):
        for v, i in zip(vals or [], ids or []):
            if i and i.get("exid") == exid:
                return v
        return None

    mod   = pick(mods,   mod_ids)
    examn = pick(exams,  exam_ids)
    medico= pick(docs,   doc_ids)
    dtval = pick(dts,    dt_ids)
    idade = pick(ages,   age_ids)
    exid_txt = pick(exids, exid_ids)

    cur = next((x for x in list_exams() if x.get("id") == exid), None)
    if not cur:
        return dbc.Alert("Exame não encontrado.", color="danger"), None, ""

    dt_iso = _clamp_future_to_now(dtval)

    new_exam = dict(cur)
    new_exam.update({
        "id": exid,
        "exam_id": exid_txt or cur.get("exam_id"),
        "modalidade": mod or cur.get("modalidade"),
        "exame": f"{MOD_LABEL.get(mod, mod)} - {examn}" if examn else cur.get("exame"),
        "medico": (medico or "").strip(),
        "data_hora": dt_iso,
        "idade": int(idade) if idade not in (None, "") else None,
        # observacao fica como está; é atualizada via modal próprio
    })

    add_or_update_exam(new_exam)
    if medico:
        ensure_doctor(medico)

    return dbc.Alert("Exame atualizado com sucesso!", color="success"), None, f"refresh@{datetime.utcnow().isoformat()}"

# (7) Abrir modal Materiais (com validação de clique real)
@dash.callback(
    Output("ex_current_id", "data", allow_duplicate=True),
    Output("ex_materials_modal", "is_open", allow_duplicate=True),
    Output("ex_mat_store", "data", allow_duplicate=True),
    Output("ex_mat_original", "data", allow_duplicate=True),
    Output("ex_mat_sel_id", "options", allow_duplicate=True),
    Input({"role": "materials", "exid": dash.ALL}, "n_clicks"),
    State({"role": "materials", "exid": dash.ALL}, "id"),
    prevent_initial_call=True
)
def _open_mat_modal(n_list, btn_ids):
    trg = ctx.triggered_id
    if not isinstance(trg, dict) or trg.get("role") != "materials":
        raise dash.exceptions.PreventUpdate
    # valida clique real no botão de materiais correspondente
    pos = None
    for i, bid in enumerate(btn_ids or []):
        if bid.get("exid") == trg.get("exid"):
            pos = i
            break
    if pos is None or not n_list or pos >= len(n_list) or (n_list[pos] or 0) <= 0:
        raise dash.exceptions.PreventUpdate

    exid = trg.get("exid")
    ex = next((x for x in list_exams() if x.get("id") == exid), None)
    # se cancelado, não abre
    if ex and ex.get("cancelado"):
        raise dash.exceptions.PreventUpdate

    items = list(ex.get("materiais_usados") or []) if ex else []
    mats = list_materials()
    mat_opts = [{"label": f"{m['nome']} (R$ {float(m.get('valor_unitario') or 0):.2f}/{m.get('unidade')})", "value": m["id"]} for m in mats]
    return exid, True, items, items, mat_opts

# (8) Lotes e badges ao escolher material no modal
@dash.callback(
    Output("ex_mat_sel_lote", "options"),
    Output("ex_mat_sel_un_badge", "children"),
    Output("ex_mat_sel_preco_badge", "children"),
    Output("ex_mat_sel_saldo_badge", "children"),
    Input("ex_mat_sel_id", "value"),
    prevent_initial_call=True
)
def _load_batches_for_modal(mat_id):
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
        saldo_total = sum(float(b.get("saldo") or 0.0) for b in batches)
        return opt, f"Unidade: {unidade}", f"Preço: {_fmt_money(preco)}/{unidade}", f"Saldo total: {saldo_total:g}"
    else:
        return [], f"Unidade: {unidade}", f"Preço: {_fmt_money(preco)}/{unidade}", ""

# (9) Render tabela e resumo do modal ao alterar store
@dash.callback(
    Output("ex_materials_table", "children"),
    Output("ex_mat_summary", "children"),
    Input("ex_mat_store", "data"),
)
def _refresh_modal_table(items):
    items = items or []
    return _materials_table(items), _materials_summary(items)

def _parse_qty(q):
    if q is None:
        raise ValueError("Quantidade não informada.")
    if isinstance(q, str):
        q = q.replace(",", ".").strip()
    return float(q)

# (10) Adicionar item no modal
@dash.callback(
    Output("ex_mat_store", "data", allow_duplicate=True),
    Output("ex_mat_feedback", "children", allow_duplicate=True),
    Output("ex_mat_sel_id", "value", allow_duplicate=True),
    Output("ex_mat_sel_lote", "value", allow_duplicate=True),
    Output("ex_mat_sel_qtd", "value", allow_duplicate=True),
    Output("ex_mat_edit_index", "data", allow_duplicate=True),
    Output("ex_mat_update_btn", "disabled", allow_duplicate=True),
    Input("ex_mat_add_btn", "n_clicks"),
    State("ex_mat_store", "data"),
    State("ex_mat_sel_id", "value"),
    State("ex_mat_sel_lote", "value"),
    State("ex_mat_sel_qtd", "value"),
    prevent_initial_call=True
)
def _add_mat_item(n, items, mat_id, lote_id, qtd):
    if not n:
        raise dash.exceptions.PreventUpdate
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
            current = 0.0
            for it in (items or []):
                if int(it.get("material_id")) == int(mat_id) and (it.get("lote_id") or None) == lote_norm:
                    current += float(it.get("quantidade") or 0.0)
            if current + q > float(b.get("saldo") or 0.0) + 1e-9:
                errors.append(f"Saldo insuficiente no lote. Disponível: {b.get('saldo')}.")

    if errors:
        return no_update, dbc.Alert(html.Ul([html.Li(e) for e in errors]), color="danger"), no_update, no_update, no_update, no_update, no_update

    items = list(items or [])
    merged = False
    for it in items:
        if int(it.get("material_id")) == int(mat_id) and (it.get("lote_id") or None) == lote_norm:
            it["quantidade"] = float(it.get("quantidade") or 0.0) + q
            merged = True
            break
    if not merged:
        items.append({"material_id": int(mat_id), "lote_id": lote_norm, "quantidade": q})
    return items, dbc.Alert("Item adicionado.", color="success"), None, None, None, None, True

# (11) Preparar edição de um item no modal
@dash.callback(
    Output("ex_mat_sel_id", "value", allow_duplicate=True),
    Output("ex_mat_sel_lote", "value", allow_duplicate=True),
    Output("ex_mat_sel_qtd", "value", allow_duplicate=True),
    Output("ex_mat_edit_index", "data", allow_duplicate=True),
    Output("ex_mat_update_btn", "disabled", allow_duplicate=True),
    Input({"type": "mat_edit_btn_x", "idx": dash.ALL}, "n_clicks"),
    State("ex_mat_store", "data"),
    State({"type": "mat_edit_btn_x", "idx": dash.ALL}, "id"),
    prevent_initial_call=True
)
def _load_item_for_edit(_clicks, items, btn_ids):
    if not ctx.triggered_id or not isinstance(ctx.triggered_id, dict):
        raise dash.exceptions.PreventUpdate
    trg = ctx.triggered_id
    # valida clique real do botão editar
    pos = None
    for i, _id in enumerate(btn_ids or []):
        if _id.get("idx") == trg.get("idx"):
            pos = i
            break
    if pos is None or not _clicks or pos >= len(_clicks) or (_clicks[pos] or 0) <= 0:
        raise dash.exceptions.PreventUpdate

    items = items or []
    if pos < 0 or pos >= len(items):
        raise dash.exceptions.PreventUpdate
    it = items[pos]
    return it.get("material_id"), it.get("lote_id"), it.get("quantidade"), pos, False

# (12) Atualizar item no modal
@dash.callback(
    Output("ex_mat_store", "data", allow_duplicate=True),
    Output("ex_mat_feedback", "children", allow_duplicate=True),
    Output("ex_mat_sel_id", "value", allow_duplicate=True),
    Output("ex_mat_sel_lote", "value", allow_duplicate=True),
    Output("ex_mat_sel_qtd", "value", allow_duplicate=True),
    Output("ex_mat_edit_index", "data", allow_duplicate=True),
    Output("ex_mat_update_btn", "disabled", allow_duplicate=True),
    Input("ex_mat_update_btn", "n_clicks"),
    State("ex_mat_edit_index", "data"),
    State("ex_mat_store", "data"),
    State("ex_mat_sel_id", "value"),
    State("ex_mat_sel_lote", "value"),
    State("ex_mat_sel_qtd", "value"),
    prevent_initial_call=True
)
def _update_mat_item(n, edit_idx, items, mat_id, lote_id, qtd):
    if not n or edit_idx is None:
        raise dash.exceptions.PreventUpdate

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
            current = 0.0
            for i, it in enumerate(items or []):
                if i == int(edit_idx):
                    continue
                if int(it.get("material_id")) == int(mat_id) and (it.get("lote_id") or None) == lote_norm:
                    current += float(it.get("quantidade") or 0.0)
            if current + q > float(b.get("saldo") or 0.0) + 1e-9:
                errors.append(f"Saldo insuficiente no lote. Disponível: {b.get('saldo')}.")

    if errors:
        return no_update, dbc.Alert(html.Ul([html.Li(e) for e in errors]), color="danger"), no_update, no_update, no_update, no_update, no_update

    items = list(items or [])
    if edit_idx < 0 or edit_idx >= len(items):
        raise dash.exceptions.PreventUpdate
    items[int(edit_idx)] = {"material_id": int(mat_id), "lote_id": lote_norm, "quantidade": q}
    return items, dbc.Alert("Item atualizado.", color="success"), None, None, None, None, True

# (13) Remoção com confirmação (validação de clique real)
@dash.callback(
    Output("ex_confirm_del_modal", "is_open", allow_duplicate=True),
    Output("ex_del_index", "data", allow_duplicate=True),
    Input({"type": "mat_del_btn_x", "idx": dash.ALL}, "n_clicks"),
    State({"type": "mat_del_btn_x", "idx": dash.ALL}, "id"),
    prevent_initial_call=True
)
def _open_confirm_delete(_clicks, btn_ids):
    if not ctx.triggered_id or not isinstance(ctx.triggered_id, dict):
        raise dash.exceptions.PreventUpdate
    trg = ctx.triggered_id
    # encontra a posição do botão no array e valida n_clicks>0
    pos = None
    for i, _id in enumerate(btn_ids or []):
        if _id.get("idx") == trg.get("idx"):
            pos = i
            break
    if pos is None or not _clicks or pos >= len(_clicks) or (_clicks[pos] or 0) <= 0:
        raise dash.exceptions.PreventUpdate
    return True, trg.get("idx")

@dash.callback(
    Output("ex_mat_store", "data", allow_duplicate=True),
    Output("ex_confirm_del_modal", "is_open", allow_duplicate=True),
    Output("ex_del_index", "data", allow_duplicate=True),
    Input("ex_confirm_del_btn", "n_clicks"),
    State("ex_del_index", "data"),
    State("ex_mat_store", "data"),
    prevent_initial_call=True
)
def _confirm_delete(n, idx, items):
    if not n:
        raise dash.exceptions.PreventUpdate
    items = list(items or [])
    if idx is None or idx < 0 or idx >= len(items):
        raise dash.exceptions.PreventUpdate
    del items[int(idx)]
    return items, False, None

@dash.callback(
    Output("ex_confirm_del_modal", "is_open", allow_duplicate=True),
    Output("ex_del_index", "data", allow_duplicate=True),
    Input("ex_cancel_del_btn", "n_clicks"),
    prevent_initial_call=True
)
def _cancel_delete(n):
    if not n:
        raise dash.exceptions.PreventUpdate
    return False, None

# (14) Limpar seleção de campos do modal
@dash.callback(
    Output("ex_mat_sel_id", "value", allow_duplicate=True),
    Output("ex_mat_sel_lote", "value", allow_duplicate=True),
    Output("ex_mat_sel_qtd", "value", allow_duplicate=True),
    Output("ex_mat_edit_index", "data", allow_duplicate=True),
    Output("ex_mat_update_btn", "disabled", allow_duplicate=True),
    Input("ex_mat_clear_btn", "n_clicks"),
    prevent_initial_call=True
)
def _clear_mat_fields(n):
    if not n:
        raise dash.exceptions.PreventUpdate
    return None, None, None, None, True

# (15) Concluir no modal -> salva alterações e aplica baixa/estorno no estoque (FIFO)
@dash.callback(
    Output("ex_materials_modal", "is_open", allow_duplicate=True),
    Output("ex_feedback", "children", allow_duplicate=True),
    Output("ex_refresh", "data", allow_duplicate=True),
    Input("ex_materials_done_btn", "n_clicks"),
    State("ex_current_id", "data"),
    State("ex_mat_store", "data"),
    State("ex_mat_original", "data"),
    prevent_initial_call=True
)
def _apply_materials(n, exid, new_items, old_items):
    if not n or not exid:
        raise dash.exceptions.PreventUpdate
    ex = next((x for x in list_exams() if x.get("id") == exid), None)
    if not ex:
        return False, dbc.Alert("Exame não encontrado.", color="danger"), no_update
    if ex.get("cancelado"):
        return False, dbc.Alert("Exame cancelado não pode alterar materiais.", color="warning"), no_update

    new_items = list(new_items or [])
    old_items = list(old_items or [])

    def key(it): return (int(it.get("material_id")), it.get("lote_id") if it.get("lote_id") is not None else None)
    agg_new = {}
    for it in new_items:
        k = key(it)
        agg_new[k] = agg_new.get(k, 0.0) + float(it.get("quantidade") or 0.0)
    agg_old = {}
    for it in old_items:
        k = key(it)
        agg_old[k] = agg_old.get(k, 0.0) + float(it.get("quantidade") or 0.0)

    deltas = {}
    for k in set(list(agg_new.keys()) + list(agg_old.keys())):
        deltas[k] = float(agg_new.get(k, 0.0) - agg_old.get(k, 0.0))

    for (mid, lid), diff in deltas.items():
        if abs(diff) <= 1e-12:
            continue
        if lid is not None:
            if diff > 0:
                b = next((x for x in list_material_batches(mid) if x.get("id") == lid), {})
                add_stock_movement({
                    "material_id": mid, "tipo": "saida", "quantidade": diff,
                    "lote": b.get("lote"), "validade": b.get("validade"),
                    "obs": f"Ajuste materiais exame {ex.get('exam_id')}"
                })
            else:
                b = next((x for x in list_material_batches(mid) if x.get("id") == lid), {})
                add_stock_movement({
                    "material_id": mid, "tipo": "entrada", "quantidade": abs(diff),
                    "lote": b.get("lote"), "validade": b.get("validade"),
                    "obs": f"Estorno materiais exame {ex.get('exam_id')}"
                })
        else:
            if diff > 0 and HAS_BATCHES:
                batches = list(list_material_batches(mid))
                batches.sort(key=lambda b: (b.get("validade") or ""))  # FIFO
                need = diff
                for b in batches:
                    if need <= 0:
                        break
                    take = min(need, float(b.get("saldo") or 0.0))
                    if take > 0:
                        add_stock_movement({
                            "material_id": mid, "tipo": "saida", "quantidade": take,
                            "lote": b.get("lote"), "validade": b.get("validade"),
                            "obs": f"Ajuste materiais exame {ex.get('exam_id')} (FIFO)"
                        })
                        need -= take
                if need > 1e-9:
                    add_stock_movement({
                        "material_id": mid, "tipo": "saida", "quantidade": need,
                        "obs": f"Ajuste materiais exame {ex.get('exam_id')} (residual)"
                    })
            elif diff > 0:
                add_stock_movement({
                    "material_id": mid, "tipo": "saida", "quantidade": diff,
                    "obs": f"Ajuste materiais exame {ex.get('exam_id')}"
                })
            else:
                add_stock_movement({
                    "material_id": mid, "tipo": "entrada", "quantidade": abs(diff),
                    "obs": f"Estorno materiais exame {ex.get('exam_id')}"
                })

    new_exam = dict(ex)
    new_exam["materiais_usados"] = new_items
    add_or_update_exam(new_exam)

    return False, dbc.Alert("Materiais atualizados e estoque ajustado.", color="success"), f"refresh@{datetime.utcnow().isoformat()}"

# (16) Fechar modal sem salvar (materiais)
@dash.callback(
    Output("ex_materials_modal", "is_open", allow_duplicate=True),
    Input("ex_materials_close_btn", "n_clicks"),
    prevent_initial_call=True
)
def _close_modal(n):
    if not n:
        raise dash.exceptions.PreventUpdate
    return False

# (17) Exportação CSV (inclui Observação)
@dash.callback(
    Output("ex_download", "data"),
    Input("ex_btn_export", "n_clicks"),
    State("ex_f_mod", "value"),
    State("ex_f_exam", "value"),
    State("ex_f_doc", "value"),
    State("ex_dt_ini", "value"),
    State("ex_dt_fim", "value"),
    State("ex_f_text", "value"),
    prevent_initial_call=True
)
def _export_csv(n, mod, exam, doc, dt_ini, dt_fim, text):
    if not n:
        raise dash.exceptions.PreventUpdate
    data = _filter_exams(list_exams(), mod, exam, doc, dt_ini, dt_fim, text)
    output = io.StringIO()
    writer = csv.writer(output, delimiter=";")
    writer.writerow(["ID", "Exam ID", "Modalidade", "Exame", "Médico", "Data/Hora", "Idade", "Cancelado", "Observação"])
    for e in data:
        writer.writerow([
            e.get("id"), e.get("exam_id"),
            MOD_LABEL.get(e.get("modalidade"), e.get("modalidade")),
            e.get("exame"), e.get("medico"),
            format_dt_br(e.get("data_hora")), e.get("idade"),
            "Sim" if e.get("cancelado") else "Não",
            (e.get("observacao") or "").replace("\n", " ").strip()
        ])
    return dict(content=output.getvalue(), filename="exames.csv")

# (18) Abrir modal de cancelar exame (com validação de clique real)
@dash.callback(
    Output("ex_cancel_modal", "is_open", allow_duplicate=True),
    Output("ex_cancel_id", "data", allow_duplicate=True),
    Input({"role": "cancel_exam", "exid": dash.ALL}, "n_clicks"),
    State({"role": "cancel_exam", "exid": dash.ALL}, "id"),
    prevent_initial_call=True
)
def _open_cancel_modal(n_list, btn_ids):
    trg = ctx.triggered_id
    if not isinstance(trg, dict) or trg.get("role") != "cancel_exam":
        raise dash.exceptions.PreventUpdate
    pos = None
    for i, bid in enumerate(btn_ids or []):
        if bid.get("exid") == trg.get("exid"):
            pos = i
            break
    if pos is None or not n_list or pos >= len(n_list) or (n_list[pos] or 0) <= 0:
        raise dash.exceptions.PreventUpdate

    exid = trg.get("exid")
    ex = next((x for x in list_exams() if x.get("id") == exid), None)
    if not ex or ex.get("cancelado"):
        raise dash.exceptions.PreventUpdate
    return True, exid

@dash.callback(
    Output("ex_cancel_modal", "is_open", allow_duplicate=True),
    Input("ex_cancel_close_btn", "n_clicks"),
    prevent_initial_call=True
)
def _close_cancel_modal(n):
    if not n:
        raise dash.exceptions.PreventUpdate
    return False

# (19) Confirmar cancelamento: estorna tudo e marca cancelado
@dash.callback(
    Output("ex_feedback", "children", allow_duplicate=True),
    Output("ex_refresh", "data", allow_duplicate=True),
    Output("ex_cancel_modal", "is_open", allow_duplicate=True),
    Input("ex_cancel_confirm_btn", "n_clicks"),
    State("ex_cancel_id", "data"),
    prevent_initial_call=True
)
def _confirm_cancel_exam(n, exid):
    if not n or not exid:
        raise dash.exceptions.PreventUpdate
    ex = next((x for x in list_exams() if x.get("id") == exid), None)
    if not ex:
        return dbc.Alert("Exame não encontrado.", color="danger"), "", False
    if ex.get("cancelado"):
        return dbc.Alert("Exame já está cancelado.", color="warning"), "", False

    used = list(ex.get("materiais_usados") or [])

    # Estorno total
    for it in used:
        mid = int(it.get("material_id"))
        qty = float(it.get("quantidade") or 0.0)
        lid = it.get("lote_id")
        if lid is not None:
            b = next((x for x in list_material_batches(mid) if x.get("id") == lid), {})
            add_stock_movement({
                "material_id": mid, "tipo": "entrada", "quantidade": qty,
                "lote": b.get("lote"), "validade": b.get("validade"),
                "obs": f"Cancelamento exame {ex.get('exam_id')}"
            })
        else:
            # Sem lote: entrada “geral”
            add_stock_movement({
                "material_id": mid, "tipo": "entrada", "quantidade": qty,
                "obs": f"Cancelamento exame {ex.get('exam_id')}"
            })

    new_exam = dict(ex)
    new_exam["materiais_usados"] = []
    new_exam["cancelado"] = True
    add_or_update_exam(new_exam)

    return dbc.Alert("Exame cancelado. Materiais estornados ao estoque.", color="success"), f"refresh@{datetime.utcnow().isoformat()}", False

# (20) Abrir modal de Observação (via botão "Obs.")
@dash.callback(
    Output("ex_obs_modal", "is_open", allow_duplicate=True),
    Output("ex_obs_id", "data", allow_duplicate=True),
    Output("ex_obs_textarea", "value", allow_duplicate=True),
    Output("ex_obs_header", "children", allow_duplicate=True),
    Input({"role": "obs", "exid": dash.ALL}, "n_clicks"),
    State({"role": "obs", "exid": dash.ALL}, "id"),
    prevent_initial_call=True
)
def _open_obs_modal(n_list, btn_ids):
    trg = ctx.triggered_id
    if not isinstance(trg, dict) or trg.get("role") != "obs":
        raise dash.exceptions.PreventUpdate
    pos = None
    for i, bid in enumerate(btn_ids or []):
        if bid.get("exid") == trg.get("exid"):
            pos = i
            break
    if pos is None or not n_list or pos >= len(n_list) or (n_list[pos] or 0) <= 0:
        raise dash.exceptions.PreventUpdate

    exid = trg.get("exid")
    ex = next((x for x in list_exams() if x.get("id") == exid), None)
    if not ex:
        raise dash.exceptions.PreventUpdate
    header = html.Small(f"Exame: {ex.get('exam_id') or exid} • {ex.get('exame') or ''}", className="text-muted")
    return True, exid, (ex.get("observacao") or ""), header

# (21) Fechar modal de Observação (sem salvar)
@dash.callback(
    Output("ex_obs_modal", "is_open", allow_duplicate=True),
    Input("ex_obs_close_btn", "n_clicks"),
    prevent_initial_call=True
)
def _close_obs_modal(n):
    if not n:
        raise dash.exceptions.PreventUpdate
    return False

# (22) Salvar Observação
@dash.callback(
    Output("ex_feedback", "children", allow_duplicate=True),
    Output("ex_obs_modal", "is_open", allow_duplicate=True),
    Output("ex_refresh", "data", allow_duplicate=True),
    Input("ex_obs_save_btn", "n_clicks"),
    State("ex_obs_id", "data"),
    State("ex_obs_textarea", "value"),
    prevent_initial_call=True
)
def _save_observation(n, exid, text):
    if not n or not exid:
        raise dash.exceptions.PreventUpdate
    ex = next((x for x in list_exams() if x.get("id") == exid), None)
    if not ex:
        return dbc.Alert("Exame não encontrado.", color="danger"), False, ""
    new_exam = dict(ex)
    new_exam["observacao"] = (text or "").strip()
    add_or_update_exam(new_exam)
    return dbc.Alert("Observação atualizada com sucesso!", color="success"), False, f"refresh@{datetime.utcnow().isoformat()}"
