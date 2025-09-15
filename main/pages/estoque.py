# pages/estoque.py — gestão de estoque consolidada (lotes/validade + criação de lote inicial via movimento)
import json
import dash
from dash import html, dcc, Input, Output, State, ALL, no_update, ctx
import dash_bootstrap_components as dbc

from core.backend import (
    compute_stock_snapshot,
    list_materials, add_material, update_material, delete_material,
    add_stock_movement
)

# Controle opcional de lotes/validade em backend
HAS_BATCHES = False
try:
    from core.backend import list_material_batches  # retorna lista de lotes com saldo (quando existir)
    HAS_BATCHES = True
except Exception:
    def list_material_batches(_material_id: int):
        return []

dash.register_page(__name__, path="/estoque", name="Gestão de estoque")


# ===================== Helpers =====================
def _fmt_money(v):
    try:
        return f"R$ {float(v):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    except Exception:
        return "R$ 0,00"


def _kpi_card(title, comp_id):
    return dbc.Card(
        dbc.CardBody([
            html.H6(title, className="mb-1 text-muted"),
            html.H2(id=comp_id, className="mb-0")
        ]),
        className="shadow-sm"
    )


def _batch_ref(material_id):
    """
    Retorna (lote_ref, validade_ref) para exibição na tabela:
    - Primeiro tenta o próximo a vencer com saldo > 0
    - Se não houver, usa o primeiro lote da lista
    - Se não houver lotes, ('—', '—')
    """
    if not HAS_BATCHES or not material_id:
        return "—", "—"
    try:
        batches = list_material_batches(int(material_id)) or []
    except Exception:
        batches = []
    if not batches:
        return "—", "—"
    candidates = [b for b in batches if float(b.get("saldo") or 0.0) > 0]
    if not candidates:
        candidates = batches
    candidates.sort(key=lambda b: (b.get("validade") or "9999-99-99"))
    b = candidates[0]
    return (b.get("lote") or "—"), (b.get("validade") or "—")


def _clicked_index(triggered_id_dict, all_clicks, all_ids):
    """
    Retorna o índice do botão (na lista ALL) que de fato foi clicado (>0),
    comparando o id do trigger com a lista de ids, e confirmando n_clicks.
    """
    if not isinstance(triggered_id_dict, dict):
        return None
    if not isinstance(all_ids, list) or not isinstance(all_clicks, list):
        return None
    for i, _id in enumerate(all_ids):
        if _id == triggered_id_dict:
            if i < len(all_clicks) and (all_clicks[i] or 0) > 0:
                return i
    return None


def toolbar():
    return dbc.Row([
        dbc.Col(dbc.Button([html.I(className="fa-solid fa-plus me-2"), "Novo material"],
                           id="btn_new_material", color="primary"), md="auto"),
        dbc.Col(dbc.Button([html.I(className="fa-solid fa-arrow-right-arrow-left me-2"), "Movimentar estoque"],
                           id="btn_open_mov_generic", color="secondary"), md="auto"),
        dcc.Store(id="estoque_refresh", data=0),           # ping para recarregar KPIs/tabela
        dcc.Store(id="current_material_id"),               # id do material em foco (editar/movimentar/excluir)
    ], className="mb-3 g-2")


def kpis_row():
    return dbc.Row([
        dbc.Col(_kpi_card("Itens no catálogo", "kpi_itens"), md=4),
        dbc.Col(_kpi_card("Itens abaixo do mínimo", "kpi_abaixo"), md=4),
        dbc.Col(_kpi_card("Valor estimado", "kpi_valor"), md=4),
    ], className="mb-3")


def _table(snap):
    cols = [
        html.Th("ID"), html.Th("Material"), html.Th("Tipo"), html.Th("Un."),
        html.Th("Preço ref."), html.Th("Inicial"),
        html.Th("Entradas"), html.Th("Saídas"), html.Th("Ajustes"), html.Th("Consumo Exames"),
        html.Th("Atual"), html.Th("Mínimo"), html.Th("Status"),
    ]
    if HAS_BATCHES:
        cols += [html.Th("Lote ref."), html.Th("Validade ref.")]
    cols.append(html.Th("Ações"))

    header = html.Thead(html.Tr(cols))

    body = []
    for x in snap:
        status = ("Abaixo", "danger") if x.get("abaixo_minimo") else ("OK", "success")
        lote, validade = _batch_ref(x.get("id"))
        actions = html.Div([
            dbc.Button("Mov.", id={"type": "btn_mov", "id": x["id"]}, size="sm",
                       color="secondary", className="me-1"),
            dbc.Button("Editar", id={"type": "btn_edit_mat", "id": x["id"]}, size="sm",
                       color="info", className="me-1"),
            dbc.Button("Excluir", id={"type": "btn_del_mat", "id": x["id"]}, size="sm",
                       color="danger"),
        ], className="d-flex")
        row = [
            html.Td(x.get("id")), html.Td(x.get("nome")), html.Td(x.get("tipo")), html.Td(x.get("unidade")),
            html.Td(_fmt_money(x.get("valor_unitario"))),
            html.Td(f"{float(x.get('estoque_inicial') or 0):.2f}"),
            html.Td(f"{float(x.get('entradas') or 0):.2f}"),
            html.Td(f"{float(x.get('saidas') or 0):.2f}"),
            html.Td(f"{float(x.get('ajustes') or 0):.2f}"),
            html.Td(f"{float(x.get('consumo_exames') or 0):.2f}"),
            html.Td(html.B(f"{float(x.get('estoque_atual') or 0):.2f}")),
            html.Td(f"{float(x.get('estoque_minimo') or 0):.2f}"),
            html.Td(dbc.Badge(status[0], color=status[1])),
        ]
        if HAS_BATCHES:
            row += [html.Td(lote), html.Td(validade)]
        row.append(html.Td(actions))
        body.append(html.Tr(row))

    return dbc.Table([header, html.Tbody(body)], bordered=True, hover=True, striped=True,
                     responsive=True, className="align-middle shadow-sm")


def table_card():
    return dbc.Card([
        dbc.CardHeader([html.I(className="fa-solid fa-boxes-stacked me-2"), "Materiais em estoque"]),
        dbc.CardBody(html.Div(id="stock_table"))
    ], className="shadow-sm")


# ===================== Modais =====================
def material_modal():
    return dbc.Modal(
        id="material_modal",
        is_open=False,
        size="lg",
        backdrop=True,
        centered=True,
        children=[
            dbc.ModalHeader(dbc.ModalTitle([html.I(className="fa-solid fa-box me-2"), "Material"])),
            dbc.ModalBody([
                dbc.Alert(id="material_feedback", color="light"),
                dbc.Row([
                    dbc.Col([dbc.Label("Nome do material"), dbc.Input(id="mat_nome", placeholder="Ex.: Seringa 10ml")], md=6),
                    dbc.Col([dbc.Label("Tipo"), dbc.Input(id="mat_tipo", placeholder="Ex.: Insumo / Medicamento / Contraste")], md=6),
                ], className="g-2"),
                dbc.Row([
                    dbc.Col([dbc.Label("Unidade"), dbc.Input(id="mat_unidade", placeholder="Ex.: un / ml / mg")], md=3),
                    dbc.Col([dbc.Label("Preço ref. (R$)"), dbc.Input(id="mat_valor", type="number", step="0.01", min=0)], md=3),
                    dbc.Col([dbc.Label("Estoque inicial"), dbc.Input(id="mat_inicial", type="number", step="0.01", min=0)], md=3),
                    dbc.Col([dbc.Label("Estoque mínimo"), dbc.Input(id="mat_minimo", type="number", step="0.01", min=0)], md=3),
                ], className="g-2 mt-1"),
                html.Hr(className="my-2"),
                html.Div(className="text-muted small mb-1",
                         children="Opcional: se o estoque inicial > 0, será lançada uma ENTRADA com as informações abaixo (lote/validade/custo)."),
                dbc.Row([
                    dbc.Col([dbc.Label("Lote inicial (opcional)"), dbc.Input(id="mat_first_lote", placeholder="Ex.: L2025-01")], md=4),
                    dbc.Col([dbc.Label("Validade (opcional)"), dbc.Input(id="mat_first_validade", type="date", placeholder="YYYY-MM-DD")], md=4),
                    dbc.Col([dbc.Label("Custo unitário inicial (R$)"), dbc.Input(id="mat_first_custo", type="number", step="0.01", min=0)], md=4),
                ], className="g-2"),
            ]),
            dbc.ModalFooter([
                dbc.Button("Cancelar", id="material_cancel", className="me-2"),
                dbc.Button([html.I(className="fa-solid fa-floppy-disk me-2"), "Salvar"], id="material_save",
                           color="primary")
            ])
        ]
    )


def movement_modal():
    # Dropdowns ganham opções ao abrir (e quando material muda)
    return dbc.Modal(
        id="mov_modal",
        is_open=False,
        size="lg",
        backdrop=True,
        centered=True,
        children=[
            dbc.ModalHeader(dbc.ModalTitle([html.I(className="fa-solid fa-right-left me-2"), "Movimentação de estoque"])),
            dbc.ModalBody([
                dbc.Alert(id="mov_feedback", color="light"),
                dbc.Row([
                    dbc.Col([dbc.Label("Material"), dcc.Dropdown(id="mov_mat_id", options=[], placeholder="Material")], md=6),
                    dbc.Col([dbc.Label("Tipo"), dcc.Dropdown(
                        id="mov_tipo",
                        options=[{"label": "Entrada", "value": "entrada"},
                                 {"label": "Saída", "value": "saida"},
                                 {"label": "Ajuste", "value": "ajuste"}],
                        placeholder="Tipo"
                    )], md=6),
                ], className="g-2"),
                dbc.Row([
                    dbc.Col([dbc.Label("Quantidade"), dbc.Input(id="mov_qtd", type="number", step="0.01", min=0)], md=4),
                    dbc.Col([dbc.Label("Custo unit. (opcional)"), dbc.Input(id="mov_valor", type="number", step="0.01", min=0)], md=4),
                    (dbc.Col([dbc.Label("Lote (opcional)"),
                              dcc.Dropdown(id="mov_lote", options=[], placeholder="Escolha um lote existente")], md=4)
                     if HAS_BATCHES else
                     dbc.Col([dbc.Label("Lote (opcional)"), dbc.Input(id="mov_lote", placeholder="Ex.: L2025-01")], md=4)),
                ], className="g-2 mt-1"),
                dbc.Row([
                    dbc.Col([dbc.Label("Validade (YYYY-MM-DD)"), dbc.Input(id="mov_validade", type="date", placeholder="YYYY-MM-DD")], md=4),
                    dbc.Col([dbc.Label("Observação"), dbc.Input(id="mov_obs", placeholder="Obs.")], md=8)
                ], className="g-2 mt-1"),
            ]),
            dbc.ModalFooter([
                dbc.Button("Cancelar", id="mov_cancel", className="me-2"),
                dbc.Button([html.I(className="fa-solid fa-check me-2"), "Registrar"], id="mov_save", color="primary")
            ])
        ]
    )


def delete_modal():
    return dbc.Modal(
        id="mat_del_modal",
        is_open=False,
        centered=True,
        children=[
            dbc.ModalHeader(dbc.ModalTitle("Remover material")),
            dbc.ModalBody(html.Div(id="mat_del_info")),
            dbc.ModalFooter([
                dbc.Button("Cancelar", id="mat_del_cancel", className="me-2"),
                dbc.Button([html.I(className="fa-solid fa-trash-can me-2"), "Excluir"], id="mat_del_confirm", color="danger")
            ])
        ]
    )


# ===================== Layout =====================
layout = dbc.Container([
    toolbar(),
    kpis_row(),
    table_card(),
    material_modal(),
    movement_modal(),
    delete_modal(),
], fluid=True)


# ===================== Callbacks =====================

# KPIs + Tabela (carrega ao entrar e a cada refresh ping)
@dash.callback(
    Output("kpi_itens", "children"),
    Output("kpi_abaixo", "children"),
    Output("kpi_valor", "children"),
    Output("stock_table", "children"),
    Input("_pages_location", "pathname"),
    Input("estoque_refresh", "data"),
    prevent_initial_call=False
)
def refresh_kpis_table(pathname, _ping):
    # Aceita carregamento inicial sempre que a rota for /estoque
    if not (pathname or "").endswith("/estoque"):
        raise dash.exceptions.PreventUpdate

    snap = compute_stock_snapshot() or []
    # KPIs
    total = len(snap)
    abaixo = sum(1 for s in snap if s.get("abaixo_minimo"))
    # Valor estimado = estoque_atual * valor_unitario (soma)
    val = 0.0
    for s in snap:
        try:
            val += float(s.get("estoque_atual") or 0.0) * float(s.get("valor_unitario") or 0.0)
        except Exception:
            pass

    return (
        str(total),
        str(abaixo),
        _fmt_money(val),
        _table(snap),
    )


# Abrir/fechar MODAL de material (novo/editar)
@dash.callback(
    Output("material_modal", "is_open"),
    Output("material_feedback", "children"),
    Output("current_material_id", "data"),
    Output("mat_nome", "value"),
    Output("mat_tipo", "value"),
    Output("mat_unidade", "value"),
    Output("mat_valor", "value"),
    Output("mat_inicial", "value"),
    Output("mat_minimo", "value"),
    Output("mat_first_lote", "value"),
    Output("mat_first_validade", "value"),
    Output("mat_first_custo", "value"),
    Input("btn_new_material", "n_clicks"),
    Input({"type": "btn_edit_mat", "id": ALL}, "n_clicks"),
    State({"type": "btn_edit_mat", "id": ALL}, "id"),
    Input("material_cancel", "n_clicks"),
    prevent_initial_call=True
)
def open_material_modal(n_new, n_edit_clicks, n_edit_ids, n_cancel):
    trig = ctx.triggered_id

    # Cancelar => fecha (só se clique real)
    if trig == "material_cancel" and (n_cancel or 0) > 0:
        return False, "", no_update, None, None, None, None, None, None, None, None, None

    # Novo material (clique real)
    if trig == "btn_new_material" and (n_new or 0) > 0:
        return True, "", None, "", "", "", "", 0, 0, "", None, ""

    # Edição a partir da linha — verificar índice realmente clicado
    idx = _clicked_index(trig, n_edit_clicks or [], n_edit_ids or [])
    if idx is not None and isinstance(trig, dict) and trig.get("type") == "btn_edit_mat":
        # localizar id do material
        mat_id = trig.get("id")
        mats = list_materials()
        mat = next((m for m in mats if int(m.get("id")) == int(mat_id)), None)
        if not mat:
            raise dash.exceptions.PreventUpdate
        return (
            True, "", int(mat["id"]),
            mat.get("nome") or "", mat.get("tipo") or "", mat.get("unidade") or "",
            float(mat.get("valor_unitario") or 0.0),
            float(mat.get("estoque_inicial") or 0.0),
            float(mat.get("estoque_minimo") or 0.0),
            "", None, ""   # campos de entrada inicial zerados na edição
        )

    raise dash.exceptions.PreventUpdate


# Salvar material (novo/editar) — entrada inicial como movimentação
@dash.callback(
    Output("material_modal", "is_open", allow_duplicate=True),
    Output("material_feedback", "children", allow_duplicate=True),
    Output("estoque_refresh", "data", allow_duplicate=True),
    Input("material_save", "n_clicks"),
    State("current_material_id", "data"),
    State("mat_nome", "value"),
    State("mat_tipo", "value"),
    State("mat_unidade", "value"),
    State("mat_valor", "value"),
    State("mat_inicial", "value"),
    State("mat_minimo", "value"),
    State("mat_first_lote", "value"),
    State("mat_first_validade", "value"),
    State("mat_first_custo", "value"),
    State("estoque_refresh", "data"),
    prevent_initial_call=True
)
def save_material(n, mid, nome, tipo, unidade, valor, inicial, minimo, first_lote, first_validade, first_custo, ping):
    if not n:
        raise dash.exceptions.PreventUpdate

    msgs = []
    nome = (nome or "").strip()
    if not nome:
        msgs.append("Informe o nome do material.")
    tipo = (tipo or "").strip() or "Material"
    unidade = (unidade or "").strip()

    def to_float(x, label):
        try:
            return float(x or 0)
        except Exception:
            msgs.append(f"{label} inválido.")
            return 0.0

    valor = to_float(valor, "Preço de referência")
    inicial = to_float(inicial, "Estoque inicial")
    minimo = to_float(minimo, "Estoque mínimo")

    # Se criando e informou estoque inicial, custo unitário inicial é opcional (valida formato)
    if mid is None and (first_custo not in (None, "")):
        try:
            float(first_custo)
        except Exception:
            msgs.append("Custo unitário inicial inválido.")

    if msgs:
        return True, dbc.Alert(html.Ul([html.Li(m) for m in msgs]), color="danger"), no_update

    if mid is None:
        # novo material: cadastra… e, se estoque inicial > 0, lança ENTRADA (com lote/validade/custo)
        rec = {
            "nome": nome, "tipo": tipo, "unidade": unidade,
            "valor_unitario": valor,
            # zera o estoque_inicial; contamos a entrada via movimento
            "estoque_inicial": 0.0,
            "estoque_minimo": minimo
        }
        new_id = add_material(rec)
        if inicial > 0:
            # registra ENTRADA — backend deve aplicar no estoque + batches (quando suportado)
            add_stock_movement({
                "material_id": int(new_id),
                "tipo": "entrada",
                "quantidade": float(inicial),
                "lote": (first_lote or "").strip() or None,
                "validade": (first_validade or "").strip() or None,
                "valor_unitario": (float(first_custo) if first_custo not in (None, "") else None),
                "obs": "Estoque inicial (cadastro)"
            })
        return False, dbc.Alert(f"Material criado (ID {new_id}).", color="success"), (ping or 0) + 1

    else:
        # edição: não mexe em entrada inicial (use o modal de movimentação)
        rec = {
            "nome": nome, "tipo": tipo, "unidade": unidade,
            "valor_unitario": valor,
            "estoque_inicial": float(inicial),
            "estoque_minimo": minimo
        }
        ok = update_material(int(mid), rec)
        if ok:
            return False, dbc.Alert("Material atualizado com sucesso!", color="success"), (ping or 0) + 1
        return True, dbc.Alert("Nenhuma alteração aplicada.", color="warning"), no_update


# Abrir/fechar MODAL de movimentação (por botão geral ou por linha)
@dash.callback(
    Output("mov_modal", "is_open"),
    Output("mov_feedback", "children"),
    Output("current_material_id", "data", allow_duplicate=True),
    Output("mov_mat_id", "options"),
    Output("mov_mat_id", "value"),
    Output("mov_tipo", "value"),
    Output("mov_qtd", "value"),
    Output("mov_valor", "value"),
    Output("mov_lote", "options") if HAS_BATCHES else Output("mov_lote", "value"),
    Output("mov_lote", "value"),
    Output("mov_validade", "value"),
    Output("mov_obs", "value"),
    Input("btn_open_mov_generic", "n_clicks"),
    Input({"type": "btn_mov", "id": ALL}, "n_clicks"),
    State({"type": "btn_mov", "id": ALL}, "id"),
    Input("mov_cancel", "n_clicks"),
    State("current_material_id", "data"),
    prevent_initial_call=True
)
def open_mov_modal(n_generic, n_row_clicks, n_row_ids, n_cancel, cur_mid):
    trig = ctx.triggered_id

    # cancelar
    if trig == "mov_cancel" and (n_cancel or 0) > 0:
        # limpa campos e fecha
        return False, "", no_update, no_update, no_update, None, None, None, ([] if HAS_BATCHES else None), None, None, None

    mats = list_materials()
    mat_options = [{"label": m.get("nome"), "value": int(m.get("id"))} for m in mats]

    # botão geral
    if trig == "btn_open_mov_generic" and (n_generic or 0) > 0:
        if HAS_BATCHES:
            return True, "", None, mat_options, None, None, None, None, [], None, None, ""
        else:
            return True, "", None, mat_options, None, None, None, None, None, None, None, ""

    # clique em uma linha específica
    idx = _clicked_index(trig, n_row_clicks or [], n_row_ids or [])
    if idx is not None and isinstance(trig, dict) and trig.get("type") == "btn_mov":
        mid = int(trig.get("id"))
        if HAS_BATCHES:
            batches = list_material_batches(mid) or []
            lot_opts = [{"label": f"{b.get('lote','-')} • Val: {b.get('validade','-')} • Saldo: {b.get('saldo',0)}",
                         "value": b.get("id")} for b in batches]
            return True, "", mid, mat_options, mid, None, None, None, lot_opts, None, None, ""
        else:
            return True, "", mid, mat_options, mid, None, None, None, None, None, None, ""

    raise dash.exceptions.PreventUpdate


# Atualiza lista de lotes quando escolhe material no modal de movimento
if HAS_BATCHES:
    @dash.callback(
        Output("mov_lote", "options", allow_duplicate=True),
        Input("mov_mat_id", "value"),
        prevent_initial_call=True
    )
    def refresh_lotes_dropdown(mid):
        if not mid:
            return []
        batches = list_material_batches(int(mid)) or []
        return [{"label": f"{b.get('lote','-')} • Val: {b.get('validade','-')} • Saldo: {b.get('saldo',0)}",
                 "value": b.get("id")} for b in batches]


# Salvar movimentação
@dash.callback(
    Output("mov_modal", "is_open", allow_duplicate=True),
    Output("mov_feedback", "children", allow_duplicate=True),
    Output("estoque_refresh", "data", allow_duplicate=True),
    Input("mov_save", "n_clicks"),
    State("current_material_id", "data"),
    State("mov_mat_id", "value"),
    State("mov_tipo", "value"),
    State("mov_qtd", "value"),
    State("mov_valor", "value"),
    State("mov_lote", "value"),
    State("mov_validade", "value"),
    State("mov_obs", "value"),
    State("estoque_refresh", "data"),
    prevent_initial_call=True
)
def save_movement(n, mid_from_row, mat_from_dd, tipo, qtd, valor, lote_val, validade, obs, ping):
    if not n:
        raise dash.exceptions.PreventUpdate

    # material pode vir do botão da linha (current_material_id) ou do dropdown
    mid = mid_from_row or mat_from_dd

    msgs = []
    if not mid:
        msgs.append("Selecione um material.")
    if (tipo or "") not in ("entrada", "saida", "ajuste"):
        msgs.append("Tipo de movimentação inválido.")
    try:
        qtdf = float(qtd or 0.0)
        if qtdf <= 0:
            msgs.append("Quantidade deve ser maior que zero.")
    except Exception:
        msgs.append("Quantidade inválida.")
        qtdf = 0.0

    if msgs:
        return True, dbc.Alert(html.Ul([html.Li(m) for m in msgs]), color="danger"), no_update

    rec = {
        "material_id": int(mid),
        "tipo": tipo,
        "quantidade": qtdf,
        "obs": (obs or "").strip() or None
    }

    # Lote/Validade
    if HAS_BATCHES:
        # mov_lote = id do lote (ou None)
        if lote_val not in (None, "", "null"):
            try:
                bid = int(lote_val)
                b = next((x for x in list_material_batches(int(mid)) if x.get("id") == bid), None)
                if b:
                    rec["lote"] = b.get("lote")
                    rec["validade"] = b.get("validade")
            except Exception:
                pass
        if validade:
            rec["validade"] = (validade or "").strip() or rec.get("validade")
    else:
        if lote_val:
            rec["lote"] = (lote_val or "").strip() or None
        if validade:
            rec["validade"] = (validade or "").strip() or None

    # custo unitário só faz sentido para entrada/ajuste (opcional no backend)
    try:
        vu = float(valor) if valor not in (None, "") else None
    except Exception:
        vu = None
    if tipo in ("entrada", "ajuste") and vu is not None:
        rec["valor_unitario"] = vu

    try:
        add_stock_movement(rec)
    except Exception as e:
        return True, dbc.Alert(f"Erro ao registrar movimentação: {e}", color="danger"), no_update

    return False, dbc.Alert("Movimentação registrado!", color="success"), (ping or 0) + 1


# Abrir modal de exclusão (com verificação de clique real)
@dash.callback(
    Output("mat_del_modal", "is_open"),
    Output("current_material_id", "data", allow_duplicate=True),
    Output("mat_del_info", "children"),
    Input({"type": "btn_del_mat", "id": ALL}, "n_clicks"),
    State({"type": "btn_del_mat", "id": ALL}, "id"),
    Input("mat_del_cancel", "n_clicks"),
    prevent_initial_call=True
)
def open_delete_modal(n_list, id_list, n_cancel):
    trig = ctx.triggered_id

    # cancelar
    if trig == "mat_del_cancel" and (n_cancel or 0) > 0:
        return False, no_update, no_update

    # clique real em Excluir
    idx = _clicked_index(trig, n_list or [], id_list or [])
    if idx is not None and isinstance(trig, dict) and trig.get("type") == "btn_del_mat":
        mid = trig.get("id")
        mat = next((m for m in list_materials() if int(m.get("id")) == int(mid)), None)
        if not mat:
            raise dash.exceptions.PreventUpdate
        info = html.Ul([
            html.Li(f"ID: {mat.get('id')}"),
            html.Li(f"Nome: {mat.get('nome')}"),
            html.Li(f"Tipo: {mat.get('tipo')}"),
            html.Li(f"Unidade: {mat.get('unidade')}"),
        ], className="mb-0")
        return True, int(mid), info

    raise dash.exceptions.PreventUpdate


# Confirmar exclusão
@dash.callback(
    Output("mat_del_modal", "is_open", allow_duplicate=True),
    Output("estoque_refresh", "data", allow_duplicate=True),
    Input("mat_del_confirm", "n_clicks"),
    State("current_material_id", "data"),
    State("estoque_refresh", "data"),
    prevent_initial_call=True
)
def confirm_delete_material(n, mid, ping):
    if not n or not mid:
        raise dash.exceptions.PreventUpdate
    delete_material(int(mid))
    return False, (ping or 0) + 1
