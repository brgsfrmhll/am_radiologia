# pages/gerencial.py
import os, base64, pathlib, json, time
import dash
from dash import html, dcc, Input, Output, State, ALL, no_update
import dash_bootstrap_components as dbc
from flask import session as flask_session
from werkzeug.security import generate_password_hash

# ===== Backend imports (com fallback) =====
try:
    from core.backend import (
        MODALIDADES, MOD_LABEL,
        get_users, add_user, update_user, delete_user, find_user_by_email,
        list_doctors, add_doctor, update_doctor, delete_doctor,
        list_exam_types, add_exam_type, update_exam_type, delete_exam_type,
        THEMES, read_settings, write_settings,
        validate_text_input, validate_email_format,
        log_action, list_logs
    )
except Exception:
    from backend import (
        MODALIDADES, MOD_LABEL,
        get_users, add_user, update_user, delete_user, find_user_by_email,
        list_doctors, add_doctor, update_doctor, delete_doctor,
        list_exam_types, add_exam_type, update_exam_type, delete_exam_type,
        THEMES, read_settings, write_settings,
        validate_text_input, validate_email_format,
        log_action, list_logs
    )

dash.register_page(__name__, path="/gerencial", name="Gerencial")

# ===================== Helpers =====================
def current_user():
    if not flask_session.get("user_id"):
        return None
    return {
        "id": flask_session.get("user_id"),
        "email": flask_session.get("user_email"),
        "nome": flask_session.get("user_name"),
        "perfil": flask_session.get("perfil"),
    }

def get_triggered_component_id_from_context(prop_id: str):
    try:
        json_part = prop_id.split(".")[0]
        obj = json.loads(json_part)
        return obj.get("id")
    except Exception:
        return None

def _ensure_button_trigger(expected_button_id: str):
    ctx = dash.callback_context
    if not ctx.triggered:
        raise dash.exceptions.PreventUpdate
    prop = ctx.triggered[0].get("prop_id", "")
    val  = ctx.triggered[0].get("value", None)
    if prop != f"{expected_button_id}.n_clicks" or not val:
        raise dash.exceptions.PreventUpdate

def _ensure_pattern_click(expected_type: str):
    ctx = dash.callback_context
    if not ctx.triggered:
        raise dash.exceptions.PreventUpdate
    prop = ctx.triggered[0].get("prop_id", "")
    val  = ctx.triggered[0].get("value", None)
    if ".n_clicks" not in prop or not val:
        raise dash.exceptions.PreventUpdate
    try:
        obj = json.loads(prop.split(".")[0])
        if obj.get("type") != expected_type:
            raise dash.exceptions.PreventUpdate
    except Exception:
        raise dash.exceptions.PreventUpdate

def _assets_dir() -> pathlib.Path:
    # pasta assets (apenas para default logo/preview de tema)
    return pathlib.Path(__file__).resolve().parents[1] / "assets"

def _assets_url_prefix() -> str:
    try:
        app = dash.get_app()
        prefix = app.config.get("requests_pathname_prefix", "/") or "/"
    except Exception:
        prefix = "/"
    if not prefix.endswith("/"):
        prefix += "/"
    return f"{prefix.rstrip('/')}/assets".replace("//assets", "/assets")

def _uploads_dir() -> pathlib.Path:
    # onde o upload será salvo (NÃO provoca reload)
    return pathlib.Path(__file__).resolve().parents[1] / "data" / "uploads"

def _uploads_url(file_name: str) -> str:
    # servida por @server.route("/uploads/<path:filename>") no app.py
    return f"/uploads/{file_name}"

def _save_uploaded_logo_to_uploads(contents: str, filename: str):
    """
    Salva logo em data/uploads/ com nome único e retorna (url_limpa, url_cachebuster)
    NÃO usa assets/ para evitar reload em dev.
    """
    if not contents or "," not in contents:
        return None, None
    try:
        _, b64data = contents.split(",", 1)
        data = base64.b64decode(b64data)
    except Exception:
        return None, None

    _uploads_dir().mkdir(parents=True, exist_ok=True)

    base, ext = os.path.splitext(filename or "")
    ext = (ext or "").lower()
    if ext not in [".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg"]:
        ext = ".png"

    ts = int(time.time())
    save_name = f"logo_{ts}{ext}"
    save_path = _uploads_dir() / save_name
    with open(save_path, "wb") as f:
        f.write(data)

    clean = _uploads_url(save_name)
    cache = f"{clean}?v={ts}"
    return clean, cache

# ===================== Componentes: Tabelas =====================
def users_table_component():
    rows = []
    header = html.Thead(html.Tr([
        html.Th("ID"), html.Th("Nome"), html.Th("E-mail"),
        html.Th("Perfil"), html.Th("Modalidades"), html.Th("Ações")
    ]))
    for u in get_users():
        rows.append(html.Tr([
            html.Td(u.get("id")),
            html.Td(u.get("nome")),
            html.Td(u.get("email")),
            html.Td(u.get("perfil")),
            html.Td(u.get("modalidades_permitidas")),
            html.Td(html.Div([
                dbc.Button([html.I(className="fa-regular fa-pen-to-square me-1"), "Editar"],
                           id={"type":"user_edit_btn","id":u.get("id")},
                           size="sm", className="btn-soft me-1"),
                dbc.Button([html.I(className="fa-regular fa-trash-can me-1"), "Excluir"],
                           id={"type":"user_del_btn","id":u.get("id")},
                           size="sm", color="danger", outline=True)
            ], className="table-actions d-flex align-items-center")),
        ]))
    return dbc.Table([header, html.Tbody(rows)], bordered=False, hover=True, striped=True,
                     responsive=True, className="align-middle table-compact table-sticky shadow-soft rounded-2xl")

def doctors_table_component():
    rows=[]
    header = html.Thead(html.Tr([
        html.Th("ID"), html.Th("Nome"), html.Th("CRM"), html.Th("Ações")
    ]))
    for d in list_doctors():
        rows.append(html.Tr([
            html.Td(d.get("id")),
            html.Td(d.get("nome")),
            html.Td(d.get("crm") or "-"),
            html.Td(html.Div([
                dbc.Button([html.I(className="fa-regular fa-pen-to-square me-1"), "Editar"],
                           id={"type":"doc_edit_btn","id":d.get("id")},
                           size="sm", className="btn-soft me-1"),
                dbc.Button([html.I(className="fa-regular fa-trash-can me-1"), "Excluir"],
                           id={"type":"doc_del_btn","id":d.get("id")},
                           size="sm", color="danger", outline=True)
            ], className="table-actions d-flex align-items-center"))
        ]))
    return dbc.Table([header, html.Tbody(rows)], bordered=False, hover=True, striped=True,
                     responsive=True, className="align-middle table-compact table-sticky shadow-soft rounded-2xl")

def examtypes_table_component():
    rows=[]
    header = html.Thead(html.Tr([
        html.Th("ID"), html.Th("Modalidade"), html.Th("Nome"),
        html.Th("Código"), html.Th("Ações")
    ]))
    for t in list_exam_types():
        rows.append(html.Tr([
            html.Td(t.get("id")),
            html.Td(MOD_LABEL.get(t.get("modalidade"), t.get("modalidade"))),
            html.Td(t.get("nome")),
            html.Td(t.get("codigo") or "-"),
            html.Td(html.Div([
                dbc.Button([html.I(className="fa-regular fa-pen-to-square me-1"), "Editar"],
                           id={"type":"ext_edit_btn","id":t.get("id")},
                           size="sm", className="btn-soft me-1"),
                dbc.Button([html.I(className="fa-regular fa-trash-can me-1"), "Excluir"],
                           id={"type":"ext_del_btn","id":t.get("id")},
                           size="sm", color="danger", outline=True)
            ], className="table-actions d-flex align-items-center"))
        ]))
    return dbc.Table([header, html.Tbody(rows)], bordered=False, hover=True, striped=True,
                     responsive=True, className="align-middle table-compact table-sticky shadow-soft rounded-2xl")

def logs_table_component():
    logs = list_logs()
    header = html.Thead(html.Tr([
        html.Th("Data/Hora (UTC)"), html.Th("Usuário"), html.Th("Ação"),
        html.Th("Entidade"), html.Th("ID"), html.Th("Antes"), html.Th("Depois")
    ]))
    rows = []
    for l in reversed(logs):
        rows.append(html.Tr([
            html.Td(l.get("ts")),
            html.Td(l.get("user")),
            html.Td(l.get("action")),
            html.Td(l.get("entity")),
            html.Td(l.get("entity_id")),
            html.Td(json.dumps(l.get("before"), ensure_ascii=False)[:80] if l.get("before") else "-"),
            html.Td(json.dumps(l.get("after"), ensure_ascii=False)[:80] if l.get("after") else "-"),
        ]))
    return dbc.Table([header, html.Tbody(rows)], bordered=False, hover=True, striped=True,
                     responsive=True, className="align-middle table-compact table-sticky shadow-soft rounded-2xl")

# ===================== Layout de cada Tab =====================
def tab_users():
    novo_usuario_card = dbc.Card([
        dbc.CardHeader([html.I(className="fa-solid fa-user-plus me-2"), "Novo Usuário"]),
        dbc.CardBody([
            dbc.Row([
                dbc.Col(dbc.Input(id="nu_nome", placeholder="Nome completo", maxLength=100), md=3),
                dbc.Col(dbc.Input(id="nu_email", placeholder="E-mail", type="email", maxLength=100), md=3),
                dbc.Col(dcc.Dropdown(id="nu_perfil", options=[
                    {"label":"Administrador","value":"admin"},
                    {"label":"Usuário","value":"user"},
                ], placeholder="Perfil"), md=2),
                dbc.Col(dbc.Input(id="nu_modalidades", placeholder='Modalidades (ex: "*" ou RX,CT,MR)', maxLength=100), md=2),
                dbc.Col(dbc.Input(id="nu_senha", placeholder="Senha", type="password", minLength=6), md=2),
            ], className="g-2"),
            dbc.Button([html.I(className="fa-solid fa-user-plus me-2"), "Criar usuário"],
                       id="btn_nu_criar", color="primary", className="mt-2"),
            html.Div(id="nu_feedback", className="mt-2")
        ])
    ], className="g-card d-none")  # mantido oculto

    lista = dbc.Card([
        dbc.CardHeader([html.I(className="fa-solid fa-users-gear me-2"), "Usuários"]),
        dbc.CardBody(html.Div(id="users_table", children=users_table_component()))
    ], className="g-card")

    modais = [
        dcc.Store(id="edit_user_id"),
        dcc.Store(id="delete_user_id"),
        dbc.Modal(
            id="user_edit_modal", is_open=False, size="xl",
            fullscreen="md-down", centered=True, scrollable=True,
            keyboard=True, backdrop="static", className="modal-themed",
            children=[
                dbc.ModalHeader(dbc.ModalTitle("Editar Usuário")),
                dbc.ModalBody([
                    dbc.Row([
                        dbc.Col(dbc.Input(id="eu_nome", placeholder="Nome completo", maxLength=100), md=4),
                        dbc.Col(dbc.Input(id="eu_email", placeholder="E-mail", type="email", maxLength=100), md=4),
                        dbc.Col(dcc.Dropdown(id="eu_perfil", options=[
                            {"label":"Administrador","value":"admin"},
                            {"label":"Usuário","value":"user"}], placeholder="Perfil"), md=4),
                    ], className="mb-3"),
                    dbc.Row([
                        dbc.Col(dbc.Input(id="eu_modalidades",
                                          placeholder='Modalidades permitidas (ex: "*" ou RX,CT,MR)', maxLength=50), md=6),
                        dbc.Col(dbc.Input(id="eu_nova_senha", placeholder="Nova senha (opcional)",
                                          type="password", minLength=6), md=6),
                    ]),
                    html.Div(id="eu_feedback", className="mt-2")
                ]),
                dbc.ModalFooter([
                    dbc.Button("Cancelar", id="user_edit_cancel", className="me-2"),
                    dbc.Button("Salvar", id="user_edit_save", color="primary")
                ])
            ]
        ),
        dbc.Modal(
            id="user_confirm_delete_modal", is_open=False,
            size="xl", fullscreen="md-down", centered=True,
            scrollable=True, keyboard=True, backdrop="static",
            className="modal-themed",
            children=[
                dbc.ModalHeader(dbc.ModalTitle("Excluir usuário?")),
                dbc.ModalBody(html.Div(id="user_delete_info")),
                dbc.ModalFooter([
                    dbc.Button("Cancelar", id="user_delete_cancel", className="me-2"),
                    dbc.Button("Excluir", id="user_delete_confirm", color="danger")
                ])
            ]
        ),
    ]

    return dbc.Row([
        dbc.Col(novo_usuario_card, md=12, className="mb-3"),
        dbc.Col(lista, md=12),
        *modais
    ])

def tab_doctors():
    novo = dbc.Card([
        dbc.CardHeader([html.I(className="fa-solid fa-user-doctor me-2"), "Novo Médico"]),
        dbc.CardBody([
            dbc.Row([
                dbc.Col(dbc.Input(id="nd_nome", placeholder="Nome"), md=6),
                dbc.Col(dbc.Input(id="nd_crm", placeholder="CRM (opcional)"), md=6),
            ], className="g-2"),
            dbc.Button([html.I(className="fa-solid fa-user-plus me-2"), "Criar médico"],
                       id="btn_nd_criar", color="primary", className="mt-2"),
            html.Div(id="nd_feedback", className="mt-2")
        ])
    ], className="g-card d-none")  # oculto

    lista = dbc.Card([
        dbc.CardHeader([html.I(className="fa-solid fa-stethoscope me-2"), "Médicos"]),
        dbc.CardBody(html.Div(id="doctors_table", children=doctors_table_component()))
    ], className="g-card")

    modal_ed = dbc.Modal(
        id="doc_edit_modal", is_open=False, size="xl",
        fullscreen="md-down", centered=True, scrollable=True,
        keyboard=True, backdrop="static", className="modal-themed",
        children=[
            dbc.ModalHeader(dbc.ModalTitle("Editar Médico")),
            dbc.ModalBody([
                dcc.Store(id="edit_doc_id"),
                dbc.Row([
                    dbc.Col(dbc.Input(id="ed_nome", placeholder="Nome"), md=8),
                    dbc.Col(dbc.Input(id="ed_crm", placeholder="CRM (opcional)"), md=4),
                ], className="mb-2"),
                html.Div(id="ed_feedback")
            ]),
            dbc.ModalFooter([
                dbc.Button("Cancelar", id="doc_edit_cancel", className="me-2"),
                dbc.Button("Salvar", id="doc_edit_save", color="primary")
            ])
        ]
    )

    return dbc.Row([
        dbc.Col(novo, md=12, className="mb-3"),
        dbc.Col(lista, md=12),
        modal_ed
    ])

def tab_examtypes():
    novo = dbc.Card([
        dbc.CardHeader([html.I(className="fa-solid fa-clipboard-list me-2"), "Novo Tipo de Exame"]),
        dbc.CardBody([
            dbc.Row([
                dbc.Col(dcc.Dropdown(id="ext_modalidade_new",
                                     options=[{"label":MOD_LABEL.get(m,m),"value":m} for m in MODALIDADES],
                                     placeholder="Modalidade"), md=3),
                dbc.Col(dbc.Input(id="ext_nome_new", placeholder="Nome do exame"), md=6),
                dbc.Col(dbc.Input(id="ext_codigo_new", placeholder="Código (opcional)"), md=3),
            ], className="g-2"),
            dbc.Button([html.I(className="fa-solid fa-plus me-2"), "Criar tipo"],
                       id="ext_create_btn", color="primary", className="mt-2"),
            html.Div(id="ext_create_feedback", className="mt-2")
        ])
    ], className="g-card d-none")  # oculto

    lista = dbc.Card([
        dbc.CardHeader([html.I(className="fa-regular fa-rectangle-list me-2"), "Catálogo de Exames"]),
        dbc.CardBody(html.Div(id="examtypes_table", children=examtypes_table_component()))
    ], className="g-card")

    modal_ed = dbc.Modal(
        id="ext_edit_modal", is_open=False, size="xl",
        fullscreen="md-down", centered=True, scrollable=True,
        keyboard=True, backdrop="static", className="modal-themed",
        children=[
            dbc.ModalHeader(dbc.ModalTitle("Editar Tipo de Exame")),
            dbc.ModalBody([
                dcc.Store(id="edit_ext_id"),
                dbc.Row([
                    dbc.Col(dcc.Dropdown(id="ext_modalidade",
                                         options=[{"label":MOD_LABEL.get(m,m),"value":m} for m in MODALIDADES],
                                         placeholder="Modalidade"), md=3),
                    dbc.Col(dbc.Input(id="ext_nome", placeholder="Nome do exame"), md=6),
                    dbc.Col(dbc.Input(id="ext_codigo", placeholder="Código (opcional)"), md=3),
                ], className="mb-2"),
                html.Div(id="ext_feedback")
            ]),
            dbc.ModalFooter([
                dbc.Button("Cancelar", id="ext_edit_cancel", className="me-2"),
                dbc.Button("Salvar", id="ext_edit_save", color="primary")
            ])
        ]
    )

    modal_del = dbc.Modal(
        id="ext_confirm_delete_modal", is_open=False, size="xl",
        fullscreen="md-down", centered=True, scrollable=True,
        keyboard=True, backdrop="static", className="modal-themed",
        children=[
            dbc.ModalHeader(dbc.ModalTitle("Excluir tipo de exame?")),
            dbc.ModalBody(html.Div(id="ext_delete_info")),
            dbc.ModalFooter([
                dbc.Button("Cancelar", id="ext_delete_cancel", className="me-2"),
                dbc.Button("Excluir", id="ext_delete_confirm", color="danger")
            ])
        ]
    )

    return dbc.Row([
        dbc.Col(novo, md=12, className="mb-3"),
        dbc.Col(lista, md=12),
        modal_ed, modal_del
    ])

def tab_config():
    s = read_settings()
    portal_name = s.get("portal_name", "")
    current_theme = s.get("theme", "Flatly")
    logo_h = int(s.get("logo_height_px", 40))
    display_h = max(100, min(400, logo_h))

    # logo atual (pode ser /uploads/... salvo anteriormente)
    current_logo_url = s.get("logo_url") or f"{_assets_url_prefix()}/logo.png"

    theme_cards = []
    for name in THEMES.keys():
        theme_cards.append(
            dbc.Col(
                dbc.Button(
                    dbc.Card(
                        dbc.CardBody([
                            html.Div(name, className="fw-semibold mb-2"),
                            html.Div([
                                html.Span(className="badge bg-primary me-1", children="Primary"),
                                html.Span(className="badge bg-secondary me-1", children="Secondary"),
                                html.Span(className="badge bg-info", children="Info"),
                            ]),
                            html.Div("Clique para selecionar e pré-visualizar", className="small text-muted mt-2")
                        ]),
                        className="g-card h-100"
                    ),
                    id={"type":"theme_pick","name":name},
                    color="light", className="w-100 text-start p-0 border-0"
                ),
                md=3, sm=4, xs=6, className="mb-3"
            )
        )

    return dbc.Card([
        dbc.CardHeader([html.I(className="fa-solid fa-gear me-2"), "Configurações do Portal"]),
        dbc.CardBody([
            dcc.Store(id="theme_css_href"),
            dcc.Store(id="cfg_theme_store", data=current_theme),
            dcc.Store(id="cfg_logo_url_store", data=current_logo_url),  # <- mantém a URL até salvar

            dbc.Row([
                dbc.Col([
                    html.Label("Nome do Portal"),
                    dbc.Input(id="cfg_portal_name", value=portal_name, placeholder="Ex.: Portal Radiológico")
                ], md=4),
                dbc.Col([
                    html.Label("Tema selecionado"),
                    html.Div(id="cfg_theme_label", className="form-control border-0 p-0 fw-semibold", children=current_theme),
                    html.Small("Selecione um tema clicando em um dos cards abaixo.", className="text-muted")
                ], md=4),
                dbc.Col([
                    html.Label("Altura do Logo"),
                    dcc.Slider(
                        id="cfg_logo_height",
                        min=100, max=400, step=2, value=display_h,
                        marks={100:"100px", 200:"200px", 300:"300px", 400:"400px"}
                    ),
                    dbc.Input(
                        id="cfg_logo_height_num",
                        type="number", min=100, max=400, step=1, value=display_h,
                        className="mt-2"
                    ),
                ], md=4),
            ], className="g-2 mb-3"),

            dbc.Row([
                dbc.Col([
                    html.Label("Logo do Portal"),
                    dcc.Upload(
                        id="cfg_logo_upload",
                        children=html.Div([
                            html.I(className="fa-regular fa-image me-2"),
                            "Arraste uma imagem aqui ou ",
                            html.Span("clique para enviar", className="text-decoration-underline")
                        ]),
                        accept="image/*",
                        multiple=False,
                        className="border rounded p-3 text-center"
                    ),
                    dbc.Button("Usar logo padrão", id="cfg_logo_reset", color="secondary", outline=True, className="mt-2"),
                ], md=6),
                dbc.Col([
                    html.Label("Preview do Logo"),
                    html.Div(
                        html.Img(
                            id="cfg_logo_preview",
                            src=f"{current_logo_url}?v={int(time.time())}",
                            style={"maxWidth":"100%", "height": f"{display_h}px"}
                        ),
                        className="border rounded p-3 d-flex align-items-center justify-content-center"
                    ),
                ], md=6),
            ], className="g-2 mb-3"),

            html.H6("Pré-visualização de Temas"),
            dbc.Row(theme_cards, className="g-2"),
            html.Div("A mini prévia abaixo aplica o CSS do tema selecionado em um sandbox isolado (iframe).",
                     className="text-muted small mb-3"),

            html.Div(
                html.Iframe(id="cfg_theme_iframe",
                            style={"width":"100%","height":"280px","border":"1px solid var(--bdr)","borderRadius":"12px"}),
                className="mb-3"
            ),

            dbc.Button("Salvar Configurações", id="btn_save_cfg", color="primary", className="me-2"),
            dbc.Button([html.I(className="fa-solid fa-rotate me-2"), "Recarregar tema agora"],
                       id="btn_reload_theme_now", color="secondary", outline=True),
            html.Div(id="cfg_feedback", className="mt-2"),
        ])
    ], className="g-card")

def tab_logs():
    return dbc.Card([
        dbc.CardHeader([html.I(className="fa-solid fa-clipboard me-2"), "Logs de Alterações"]),
        dbc.CardBody(html.Div(id="logs_table", children=logs_table_component()))
    ], className="g-card")

# ===================== FAB (Cadastro Rápido) =====================
def fab_modal():
    return dbc.Modal(
        id="fab_modal", is_open=False, size="xl",
        fullscreen="md-down", centered=True, scrollable=True,
        keyboard=True, backdrop="static",
        children=[
            dbc.ModalHeader(dbc.ModalTitle([html.I(className="fa-solid fa-bolt me-2"), "Cadastro rápido"])),
            dbc.ModalBody([
                dcc.Tabs(id="fab_tabs", value="u", className="dash-tabs", children=[
                    dcc.Tab(label="Usuário", value="u"),
                    dcc.Tab(label="Médico", value="d"),
                    dcc.Tab(label="Exame", value="e"),
                ]),
                html.Div(id="fab_tabcontent")
            ]),
            dbc.ModalFooter([
                dbc.Button("Cancelar", id="fab_cancel", className="me-2"),
                dbc.Button([html.I(className="fa-solid fa-floppy-disk me-2"), "Salvar"], id="fab_save", color="primary")
            ])
        ],
        className="modal-themed modal-lg-plus"
    )

# >>> Render das 3 sub-abas SEMPRE (visibilidade por CSS)
@dash.callback(Output("fab_tabcontent","children"),
               Input("fab_tabs","value"))
def render_fab_tab(tab):
    show = {"display": "block"}
    hide = {"display": "none"}

    form_u = html.Div(
        [
            dbc.Row([
                dbc.Col([html.Label("Nome"), dbc.Input(id="fab_u_nome", placeholder="Nome completo")], md=6),
                dbc.Col([html.Label("E-mail"), dbc.Input(id="fab_u_email", type="email", placeholder="email@dominio.com")], md=6),
            ], className="g-2"),
            dbc.Row([
                dbc.Col([html.Label("Perfil"),
                         dcc.Dropdown(id="fab_u_perfil",
                                      options=[{"label":"Administrador","value":"admin"},{"label":"Usuário","value":"user"}],
                                      placeholder="Escolha o perfil")], md=4),
                dbc.Col([html.Label("Modalidades"),
                         dbc.Input(id="fab_u_modalidades", placeholder='Ex.: "*" ou RX,CT,MR')], md=4),
                dbc.Col([html.Label("Senha"),
                         dbc.Input(id="fab_u_senha", type="password", placeholder="Mínimo 6 caracteres")], md=4),
            ], className="g-2 mt-1"),
            html.Div(id="fab_feedback_u", className="mt-2")
        ],
        id="fab_tab_u",
        style=(show if tab == "u" else hide),
    )

    form_d = html.Div(
        [
            dbc.Row([
                dbc.Col([html.Label("Nome"), dbc.Input(id="fab_d_nome", placeholder="Nome do médico")], md=8),
                dbc.Col([html.Label("CRM (opcional)"), dbc.Input(id="fab_d_crm", placeholder="CRM")], md=4),
            ], className="g-2"),
            html.Div(id="fab_feedback_d", className="mt-2")
        ],
        id="fab_tab_d",
        style=(show if tab == "d" else hide),
    )

    form_e = html.Div(
        [
            dbc.Row([
                dbc.Col([html.Label("Modalidade"),
                         dcc.Dropdown(id="fab_e_modalidade",
                                      options=[{"label": MOD_LABEL.get(m, m), "value": m} for m in MODALIDADES],
                                      placeholder="Selecione")], md=4),
                dbc.Col([html.Label("Nome do exame"), dbc.Input(id="fab_e_nome")], md=6),
                dbc.Col([html.Label("Código (opcional)"), dbc.Input(id="fab_e_codigo")], md=2),
            ], className="g-2"),
            html.Div(id="fab_feedback_e", className="mt-2")
        ],
        id="fab_tab_e",
        style=(show if tab == "e" else hide),
    )

    return html.Div([form_u, form_d, form_e])

# ===================== Layout principal =====================
layout = dbc.Container([
    html.Div([
        html.H3([html.I(className="fa-solid fa-screwdriver-wrench me-2"), "Gerencial"], className="m-0"),
        html.Div(className="toolbar rounded-2xl")
    ], className="page-title"),
    dcc.Tabs(id="tabs_gerencial", value="g_users", children=[
        dcc.Tab(label="Usuários", value="g_users"),
        dcc.Tab(label="Médicos", value="g_doctors"),
        dcc.Tab(label="Catálogo de Exames", value="g_examtypes"),
        dcc.Tab(label="Configurações", value="g_config"),
        dcc.Tab(label="Logs", value="g_logs"),
    ], className="mb-3 dash-tabs"),

    # Conteúdo da Aba
    html.Div(id="tab_content", children=tab_users()),

    # Sinais de refresh (sempre presentes)
    dcc.Store(id="refresh_users"),
    dcc.Store(id="refresh_doctors"),
    dcc.Store(id="refresh_examtypes"),

    # FAB + Tooltip + Stores + Modal
    html.Div([
        dbc.Button(html.I(className="fa-solid fa-plus"), id="fab_open",
                   color="primary", className="fab-main", n_clicks=0),
        dbc.Tooltip("Cadastro rápido", target="fab_open", placement="left")
    ], className="fab"),
    dcc.Store(id="fab_close_u"),
    dcc.Store(id="fab_close_d"),
    dcc.Store(id="fab_close_e"),
    fab_modal()
], fluid=True, className="page-gerencial", style={"scrollBehavior":"smooth"})

# ============== Navegação/Refresh por Tabs (único escritor de tab_content) ==============
@dash.callback(
    Output("tab_content","children"),
    Input("tabs_gerencial","value"),
    Input("refresh_users","data"),
    Input("refresh_doctors","data"),
    Input("refresh_examtypes","data"),
)
def _render_tab(tab, _ru, _rd, _re):
    if tab == "g_users": return tab_users()
    if tab == "g_doctors": return tab_doctors()
    if tab == "g_examtypes": return tab_examtypes()
    if tab == "g_config": return tab_config()
    if tab == "g_logs": return tab_logs()
    return html.Div()

# ===================== Usuários =====================
@dash.callback(
    Output("nu_feedback","children"),
    Output("refresh_users","data", allow_duplicate=True),
    Input("btn_nu_criar","n_clicks"),
    State("nu_nome","value"), State("nu_email","value"), State("nu_perfil","value"),
    State("nu_modalidades","value"), State("nu_senha","value"),
    prevent_initial_call=True
)
def criar_usuario(n, nome, email, perfil, modalidades, senha):
    _ensure_button_trigger("btn_nu_criar")
    cu = current_user()
    if not cu or cu.get("perfil")!="admin":
        return dbc.Alert("Acesso negado.", color="danger"), no_update

    msgs = []
    ok, nome = validate_text_input(nome, "Nome"); msgs += ([] if ok else [nome])
    ok, email = validate_text_input(email, "E-mail"); msgs += ([] if ok else [email])
    if ok and not validate_email_format(email): msgs.append("Formato de e-mail inválido.")
    elif find_user_by_email(email or ""): msgs.append("E-mail já cadastrado.")
    ok, perfil = validate_text_input(perfil, "Perfil"); msgs += ([] if ok else [perfil])
    if ok and perfil not in ["admin","user"]: msgs.append("Perfil inválido.")
    ok, senha = validate_text_input(senha, "Senha"); msgs += ([] if ok else [senha])
    if ok and len((senha or "")) < 6: msgs.append("A senha deve ter pelo menos 6 caracteres.")
    modalidades = (modalidades or "*").strip()

    if msgs:
        return dbc.Alert(html.Ul([html.Li(m) for m in msgs]), color="danger"), no_update

    rec = {"nome": nome.strip(), "email": email.strip().lower(),
           "senha_hash": generate_password_hash(senha.strip()),
           "modalidades_permitidas": modalidades, "perfil": perfil, "id": 0}
    uid = add_user(rec)
    log_action(cu.get("email"), "create", "user", uid, before=None,
               after={k:v for k,v in rec.items() if k!="senha_hash"})
    return dbc.Alert(f"Usuário criado (ID {uid}).", color="success", duration=3000), time.time()

@dash.callback(
    Output("user_edit_modal","is_open", allow_duplicate=True),
    Output("edit_user_id","data"),
    Output("eu_nome","value"),
    Output("eu_email","value"),
    Output("eu_perfil","value"),
    Output("eu_modalidades","value"),
    Input({"type":"user_edit_btn","id":ALL},"n_clicks"),
    Input("user_edit_cancel","n_clicks"),
    prevent_initial_call=True
)
def open_user_edit(edit_clicks, cancel_click):
    from dash import callback_context as ctx
    if not ctx.triggered: raise dash.exceptions.PreventUpdate
    prop_id = ctx.triggered[0]["prop_id"]; val = ctx.triggered[0]["value"]
    if prop_id == "user_edit_cancel.n_clicks": return False, None, None, None, None, None
    if val in (None, 0): raise dash.exceptions.PreventUpdate
    user_id_to_edit = get_triggered_component_id_from_context(prop_id)
    if not user_id_to_edit: raise dash.exceptions.PreventUpdate
    u = next((x for x in get_users() if x.get("id")==user_id_to_edit), None)
    if not u: raise dash.exceptions.PreventUpdate
    return True, user_id_to_edit, u.get("nome"), u.get("email"), u.get("perfil"), u.get("modalidades_permitidas")

@dash.callback(
    Output("user_edit_modal","is_open", allow_duplicate=True),
    Output("eu_feedback","children", allow_duplicate=True),
    Output("refresh_users","data", allow_duplicate=True),
    Input("user_edit_save","n_clicks"),
    State("edit_user_id","data"),
    State("eu_nome","value"), State("eu_email","value"),
    State("eu_perfil","value"), State("eu_modalidades","value"),
    State("eu_nova_senha","value"),
    prevent_initial_call=True
)
def save_user_edit(n, uid, nome, email, perfil, modalidades, nova_senha):
    _ensure_button_trigger("user_edit_save")
    cu = current_user()
    if not cu or cu.get("perfil")!="admin": raise dash.exceptions.PreventUpdate
    if not uid: raise dash.exceptions.PreventUpdate

    msgs=[]
    ok, nome = validate_text_input(nome,"Nome"); msgs += ([] if ok else [nome])
    ok, email = validate_text_input(email,"E-mail"); msgs += ([] if ok else [email])
    if ok and not validate_email_format(email): msgs.append("Formato de e-mail inválido.")
    ok, perfil = validate_text_input(perfil,"Perfil"); msgs += ([] if ok else [perfil])
    if ok and perfil not in ["admin","user"]: msgs.append("Perfil inválido.")
    if msgs:
        return True, dbc.Alert(html.Ul([html.Li(m) for m in msgs]), color="danger"), no_update

    fields = {"nome":nome, "email":email.lower(), "perfil":perfil, "modalidades_permitidas": (modalidades or "*").strip()}
    if (nova_senha or "").strip():
        fields["senha_hash"] = generate_password_hash(nova_senha.strip())
    before = next((x for x in get_users() if x.get("id")==int(uid)), None)
    ok = update_user(int(uid), fields)
    if ok:
        after = next((x for x in get_users() if x.get("id")==int(uid)), None)
        log_action(cu.get("email"), "update", "user", int(uid),
                   before={k:v for k,v in (before or {}).items() if k!="senha_hash"},
                   after={k:v for k,v in (after or {}).items() if k!="senha_hash"})
        return False, dbc.Alert("Usuário atualizado!", color="success", duration=3000), time.time()
    return True, dbc.Alert("Nenhuma alteração aplicada.", color="warning"), no_update

@dash.callback(
    Output("user_confirm_delete_modal","is_open", allow_duplicate=True),
    Output("delete_user_id","data"),
    Output("user_delete_info","children"),
    Input({"type":"user_del_btn","id":ALL},"n_clicks"),
    prevent_initial_call=True
)
def open_user_delete(edit_clicks):
    _ensure_pattern_click("user_del_btn")
    ctx = dash.callback_context
    uid = get_triggered_component_id_from_context(ctx.triggered[0]["prop_id"])
    if not uid: raise dash.exceptions.PreventUpdate
    u = next((x for x in get_users() if x.get("id")==uid), None)
    if not u: raise dash.exceptions.PreventUpdate
    info = html.Div([html.P("Tem certeza que deseja excluir este usuário?"),
                     html.Ul([html.Li(f"ID: {u.get('id')}"),
                              html.Li(f"Nome: {u.get('nome')}"),
                              html.Li(f"E-mail: {u.get('email')}")])])
    return True, uid, info

@dash.callback(
    Output("user_confirm_delete_modal","is_open", allow_duplicate=True),
    Output("refresh_users","data", allow_duplicate=True),
    Input("user_delete_confirm","n_clicks"),
    State("delete_user_id","data"),
    prevent_initial_call=True
)
def confirm_user_delete(n, uid):
    _ensure_button_trigger("user_delete_confirm")
    cu = current_user()
    if not cu or cu.get("perfil")!="admin" or not uid:
        return dash.no_update, no_update
    before = next((x for x in get_users() if x.get("id")==int(uid)), None)
    ok = delete_user(int(uid))
    if ok:
        log_action(cu.get("email"), "delete", "user", int(uid),
                   before={k:v for k,v in (before or {}).items() if k!="senha_hash"}, after=None)
    return False, time.time()

@dash.callback(
    Output("user_confirm_delete_modal","is_open", allow_duplicate=True),
    Input("user_delete_cancel","n_clicks"),
    prevent_initial_call=True
)
def close_user_delete_modal(n):
    _ensure_button_trigger("user_delete_cancel")
    return False

# ===================== Médicos =====================
@dash.callback(
    Output("nd_feedback","children"),
    Output("refresh_doctors","data", allow_duplicate=True),
    Input("btn_nd_criar","n_clicks"),
    State("nd_nome","value"), State("nd_crm","value"),
    prevent_initial_call=True
)
def criar_medico(n, nome, crm):
    _ensure_button_trigger("btn_nd_criar")
    cu = current_user()
    if not cu or cu.get("perfil")!="admin":
        return dbc.Alert("Acesso negado.", color="danger"), no_update
    ok, nome = validate_text_input(nome, "Nome")
    if not ok: return dbc.Alert(nome, color="danger"), no_update
    rec = {"nome": nome, "crm": (crm or "").strip() or None, "id":0}
    did = add_doctor(rec)
    log_action(cu.get("email"), "create", "doctor", did, before=None, after=rec)
    return dbc.Alert(f"Médico criado (ID {did}).", color="success", duration=3000), time.time()

@dash.callback(
    Output("doc_edit_modal","is_open", allow_duplicate=True),
    Output("edit_doc_id","data"),
    Output("ed_nome","value"),
    Output("ed_crm","value"),
    Input({"type":"doc_edit_btn","id":ALL},"n_clicks"),
    Input("doc_edit_cancel","n_clicks"),
    prevent_initial_call=True
)
def open_doc_edit(edit_clicks, cancel_click):
    from dash import callback_context as ctx
    if not ctx.triggered: raise dash.exceptions.PreventUpdate
    prop = ctx.triggered[0]["prop_id"]; val = ctx.triggered[0]["value"]
    if prop == "doc_edit_cancel.n_clicks": return False, None, None, None
    if val in (None, 0): raise dash.exceptions.PreventUpdate
    did = get_triggered_component_id_from_context(prop)
    if not did: raise dash.exceptions.PreventUpdate
    d = next((x for x in list_doctors() if x.get("id")==did), None)
    if not d: raise dash.exceptions.PreventUpdate
    return True, did, d.get("nome"), d.get("crm")

@dash.callback(
    Output("doc_edit_modal","is_open", allow_duplicate=True),
    Output("ed_feedback","children", allow_duplicate=True),
    Output("refresh_doctors","data", allow_duplicate=True),
    Input("doc_edit_save","n_clicks"),
    State("edit_doc_id","data"),
    State("ed_nome","value"), State("ed_crm","value"),
    prevent_initial_call=True
)
def save_doc_edit(n, did, nome, crm):
    _ensure_button_trigger("doc_edit_save")
    cu = current_user()
    if not cu or cu.get("perfil")!="admin": raise dash.exceptions.PreventUpdate
    if not did: raise dash.exceptions.PreventUpdate
    ok, nome = validate_text_input(nome, "Nome")
    if not ok: return True, dbc.Alert(nome, color="danger"), no_update
    clean_crm = (crm or "").strip() or None
    before = next((x for x in list_doctors() if x.get("id")==int(did)), None)
    ok = update_doctor(int(did), {"nome": nome, "crm": clean_crm})
    if ok:
        after = next((x for x in list_doctors() if x.get("id")==int(did)), None)
        log_action(cu.get("email"), "update", "doctor", int(did), before=before, after=after)
        return False, dbc.Alert("Médico atualizado com sucesso!", color="success", duration=3000), time.time()
    return True, dbc.Alert("Nenhuma alteração aplicada.", color="warning"), no_update

@dash.callback(
    Output("refresh_doctors","data", allow_duplicate=True),
    Input({"type":"doc_del_btn","id":ALL},"n_clicks"),
    prevent_initial_call=True
)
def del_doctor(n_clicks):
    _ensure_pattern_click("doc_del_btn")
    ctx = dash.callback_context
    did = get_triggered_component_id_from_context(ctx.triggered[0]["prop_id"])
    if not did: raise dash.exceptions.PreventUpdate
    cu = current_user()
    before = next((x for x in list_doctors() if x.get("id")==int(did)), None)
    ok = delete_doctor(int(did))
    if ok:
        log_action(cu.get("email") if cu else None, "delete", "doctor", int(did), before=before, after=None)
    return time.time()

# ===================== Tipos de Exame =====================
@dash.callback(
    Output("ext_create_feedback","children"),
    Output("refresh_examtypes","data", allow_duplicate=True),
    Input("ext_create_btn","n_clicks"),
    State("ext_modalidade_new","value"),
    State("ext_nome_new","value"),
    State("ext_codigo_new","value"),
    prevent_initial_call=True
)
def criar_tipo_exame(n, modalidade, nome, codigo):
    _ensure_button_trigger("ext_create_btn")
    cu = current_user()
    if not cu or cu.get("perfil")!="admin":
        return dbc.Alert("Acesso negado.", color="danger"), no_update
    msgs=[]
    ok, modalidade = validate_text_input(modalidade,"Modalidade"); msgs += ([] if ok else [modalidade])
    if ok and modalidade not in MODALIDADES: msgs.append("Modalidade inválida.")
    ok, nome = validate_text_input(nome,"Nome"); msgs += ([] if ok else [nome])
    if msgs:
        return dbc.Alert(html.Ul([html.Li(m) for m in msgs]), color="danger"), no_update
    rec = {"modalidade": modalidade, "nome": nome, "codigo": (codigo or None), "id":0}
    tid = add_exam_type(rec)
    log_action(cu.get("email"), "create", "exam_type", tid, before=None, after=rec)
    return dbc.Alert(f"Tipo de exame adicionado (ID {tid}).", color="success", duration=3000), time.time()

@dash.callback(
    Output("ext_edit_modal","is_open", allow_duplicate=True),
    Output("edit_ext_id","data"),
    Output("ext_modalidade","value"),
    Output("ext_nome","value"),
    Output("ext_codigo","value"),
    Input({"type":"ext_edit_btn","id":ALL},"n_clicks"),
    Input("ext_edit_cancel","n_clicks"),
    prevent_initial_call=True
)
def open_ext_edit(edit_clicks, cancel_click):
    from dash import callback_context as ctx
    if not ctx.triggered: raise dash.exceptions.PreventUpdate
    prop = ctx.triggered[0]["prop_id"]; val = ctx.triggered[0]["value"]
    if prop == "ext_edit_cancel.n_clicks": return False, None, None, None, None
    if val in (None, 0): raise dash.exceptions.PreventUpdate
    tid = get_triggered_component_id_from_context(prop)
    if not tid: raise dash.exceptions.PreventUpdate
    t = next((x for x in list_exam_types() if x.get("id")==tid), None)
    if not t: raise dash.exceptions.PreventUpdate
    return True, tid, t.get("modalidade"), t.get("nome"), t.get("codigo")

@dash.callback(
    Output("ext_edit_modal","is_open", allow_duplicate=True),
    Output("ext_feedback","children", allow_duplicate=True),
    Output("refresh_examtypes","data", allow_duplicate=True),
    Input("ext_edit_save","n_clicks"),
    State("edit_ext_id","data"),
    State("ext_modalidade","value"),
    State("ext_nome","value"),
    State("ext_codigo","value"),
    prevent_initial_call=True
)
def save_ext_edit(n, tid, modalidade, nome, codigo):
    _ensure_button_trigger("ext_edit_save")
    cu = current_user()
    if not cu or cu.get("perfil")!="admin": raise dash.exceptions.PreventUpdate
    if not tid: raise dash.exceptions.PreventUpdate
    msgs=[]
    ok, modalidade = validate_text_input(modalidade,"Modalidade"); msgs += ([] if ok else [modalidade])
    if ok and modalidade not in MODALIDADES: msgs.append("Modalidade inválida.")
    ok, nome = validate_text_input(nome,"Nome"); msgs += ([] if ok else [nome])
    if msgs:
        return True, dbc.Alert(html.Ul([html.Li(m) for m in msgs]), color="danger"), no_update
    before = next((x for x in list_exam_types() if x.get("id")==int(tid)), None)
    ok = update_exam_type(int(tid), {"modalidade": modalidade, "nome": nome, "codigo": (codigo or None)})
    if ok:
        after = next((x for x in list_exam_types() if x.get("id")==int(tid)), None)
        log_action(cu.get("email"), "update", "exam_type", int(tid), before=before, after=after)
        return False, dbc.Alert("Tipo atualizado!", color="success", duration=3000), time.time()
    return True, dbc.Alert("Nenhuma alteração aplicada.", color="warning"), no_update

@dash.callback(
    Output("ext_confirm_delete_modal","is_open", allow_duplicate=True),
    Output("ext_delete_info","children"),
    Input({"type":"ext_del_btn","id":ALL},"n_clicks"),
    prevent_initial_call=True
)
def open_ext_delete(n_clicks):
    _ensure_pattern_click("ext_del_btn")
    ctx = dash.callback_context
    tid = get_triggered_component_id_from_context(ctx.triggered[0]["prop_id"])
    if not tid: raise dash.exceptions.PreventUpdate
    t = next((x for x in list_exam_types() if x.get("id")==tid), None)
    if not t: raise dash.exceptions.PreventUpdate
    info = html.Div([html.P("Tem certeza que deseja excluir este tipo?"),
                     html.Ul([html.Li(f"ID: {t.get('id')}"),
                              html.Li(f"Modalidade: {t.get('modalidade')}"),
                              html.Li(f"Nome: {t.get('nome')}"),
                              html.Li(f"Código: {t.get('codigo') or '-'}")])])
    return True, info

@dash.callback(
    Output("ext_confirm_delete_modal","is_open", allow_duplicate=True),
    Output("refresh_examtypes","data", allow_duplicate=True),
    Input("ext_delete_confirm","n_clicks"),
    State("edit_ext_id","data"),
    prevent_initial_call=True
)
def confirm_ext_delete(n, tid):
    _ensure_button_trigger("ext_delete_confirm")
    cu = current_user()
    if not cu or cu.get("perfil")!="admin" or not tid:
        return dash.no_update, no_update
    before = next((x for x in list_exam_types() if x.get("id")==int(tid)), None)
    ok = delete_exam_type(int(tid))
    if ok:
        log_action(cu.get("email"), "delete", "exam_type", int(tid), before=before, after=None)
    return False, time.time()

@dash.callback(
    Output("ext_confirm_delete_modal","is_open", allow_duplicate=True),
    Input("ext_delete_cancel","n_clicks"),
    prevent_initial_call=True
)
def cancel_ext_delete(n):
    _ensure_button_trigger("ext_delete_cancel")
    return False

# ===================== Configurações (logo/tema) =====================
@dash.callback(
    Output("cfg_theme_store","data", allow_duplicate=True),
    Output("cfg_theme_label","children", allow_duplicate=True),
    Input({"type":"theme_pick","name":ALL}, "n_clicks"),
    State("cfg_theme_store","data"),
    prevent_initial_call=True
)
def pick_theme_from_card(clicks, current_value):
    from dash import callback_context as ctx
    if not ctx.triggered:
        raise dash.exceptions.PreventUpdate
    prop = ctx.triggered[0]["prop_id"]
    try:
        obj = json.loads(prop.split(".")[0])
        chosen = obj.get("name") or current_value
        return chosen, chosen
    except Exception:
        return current_value, current_value

@dash.callback(
    Output("cfg_logo_preview","src", allow_duplicate=True),
    Output("cfg_logo_url_store","data", allow_duplicate=True),
    Input("cfg_logo_upload","contents"),
    State("cfg_logo_upload","filename"),
    prevent_initial_call=True
)
def handle_logo_upload(contents, filename):
    if not contents:
        raise dash.exceptions.PreventUpdate
    url_clean, url_cache = _save_uploaded_logo_to_uploads(contents, filename)
    if not url_clean:
        raise dash.exceptions.PreventUpdate
    return url_cache, url_clean  # preview com cache-buster / store com URL limpa

@dash.callback(
    Output("cfg_logo_preview","src", allow_duplicate=True),
    Output("cfg_logo_url_store","data", allow_duplicate=True),
    Input("cfg_logo_reset","n_clicks"),
    prevent_initial_call=True
)
def reset_logo(n):
    _ensure_button_trigger("cfg_logo_reset")
    base = f"{_assets_url_prefix()}/logo.png"
    return f"{base}?v={int(time.time())}", base

@dash.callback(
    Output("cfg_logo_height_num","value", allow_duplicate=True),
    Input("cfg_logo_height","value"),
    prevent_initial_call=True
)
def sync_num_from_slider(v): return v

@dash.callback(
    Output("cfg_logo_height","value", allow_duplicate=True),
    Input("cfg_logo_height_num","value"),
    prevent_initial_call=True
)
def sync_slider_from_num(v):
    if v is None: raise dash.exceptions.PreventUpdate
    v = max(100, min(400, int(v)))
    return v

@dash.callback(
    Output("cfg_logo_preview","style", allow_duplicate=True),
    Input("cfg_logo_height","value"),
    prevent_initial_call=True
)
def apply_logo_height(h):
    return {"maxWidth":"100%", "height": f"{int(h or 100)}px"}

@dash.callback(
    Output("cfg_theme_iframe","srcDoc"),
    Input("cfg_theme_store","data"),
    Input("cfg_logo_height","value"),
    Input("cfg_portal_name","value"),
    Input("cfg_logo_url_store","data"),
)
def render_theme_iframe(theme, h, portal_name, logo_url):
    css_url = THEMES.get(theme) if isinstance(THEMES.get(theme), str) else None
    if not css_url and isinstance(THEMES.get(theme), dict):
        css_url = THEMES.get(theme, {}).get("url") or THEMES.get(theme, {}).get("href")
    portal_name = (portal_name or "").strip() or "Seu Portal"
    h = int(h or 100)
    logo_src = (logo_url or f"{_assets_url_prefix()}/logo.png") + f"?v={int(time.time())}"
    head_links = f'<link rel="stylesheet" href="{css_url}">' if css_url else ""
    doc = f"""<!doctype html>
<html lang="pt-br">
<head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">{head_links}
<style>body{{padding:12px}}.navbar-brand img{{height:{h}px;margin-right:.5rem}}</style>
</head>
<body>
<nav class="navbar navbar-expand-lg bg-body-tertiary navbar-light">
  <div class="container-fluid">
    <a class="navbar-brand" href="#"><img src="{logo_src}" alt="logo">{portal_name}</a>
    <div class="ms-auto"><a class="btn btn-primary btn-sm" href="#">Ação</a></div>
  </div>
</nav>
<div class="card mt-3">
  <div class="card-header">Card de Exemplo</div>
  <div class="card-body">
    <p class="card-text">Este é um preview rápido do seu tema.</p>
    <a href="#" class="btn btn-primary me-2">Primário</a>
    <a href="#" class="btn btn-outline-primary">Outline</a>
  </div>
</div>
</body></html>"""
    return doc

@dash.callback(
    Output("theme_css_href","data"),
    Input("cfg_theme_store","data"),
)
def compute_theme_href(theme):
    url = THEMES.get(theme) if isinstance(THEMES.get(theme), str) else None
    if not url and isinstance(THEMES.get(theme), dict):
        url = THEMES.get(theme, {}).get("url") or THEMES.get(theme, {}).get("href")
    return url

@dash.callback(
    Output("cfg_feedback","children", allow_duplicate=True),
    Input("btn_save_cfg","n_clicks"),
    State("cfg_portal_name","value"),
    State("cfg_theme_store","data"),
    State("cfg_logo_height","value"),
    State("cfg_logo_url_store","data"),
    prevent_initial_call=True
)
def save_cfg(n, name, theme, logo_h, logo_url_store):
    _ensure_button_trigger("btn_save_cfg")
    cu = current_user()
    if not cu or cu.get("perfil")!="admin":
        return dbc.Alert("Acesso negado.", color="danger")
    cur = read_settings()
    new = {
        "portal_name": (name or "").strip(),
        "theme": theme,
        "logo_height_px": int(max(100, min(400, (logo_h or 100)))),
        "logo_url": (logo_url_store or cur.get("logo_url") or f"{_assets_url_prefix()}/logo.png")
    }
    write_settings(new)
    log_action(cu.get("email"), "update", "settings", "theme", before=cur, after=new)
    return dbc.Alert("Configurações salvas. O novo logo e tema já estão prontos para uso (atualize a página para aplicar globalmente).", color="success")

# Injeção dinâmica do CSS do tema no <head>
dash.clientside_callback(
    """
    function(cssHref, clickReload) {
        if (!clickReload || !cssHref) { return window.dash_clientside.no_update; }
        try {
            var id = 'dynamic-theme-css';
            var link = document.getElementById(id);
            if (!link) {
                link = document.createElement('link');
                link.id = id;
                link.rel = 'stylesheet';
                link.type = 'text/css';
                document.getElementsByTagName('head')[0].appendChild(link);
            }
            link.href = cssHref;
            return "Tema aplicado sem recarregar (temporário).";
        } catch (e) {
            return "Não foi possível aplicar o tema dinamicamente.";
        }
    }
    """,
    Output("cfg_feedback","children", allow_duplicate=True),
    Input("theme_css_href","data"),
    Input("btn_reload_theme_now","n_clicks"),
    prevent_initial_call=True
)

# ===================== FAB: controle is_open =====================
@dash.callback(
    Output("fab_modal","is_open"),
    Input("fab_open","n_clicks"),
    Input("fab_cancel","n_clicks"),
    Input("fab_close_u","data"),
    Input("fab_close_d","data"),
    Input("fab_close_e","data"),
    State("fab_modal","is_open"),
    prevent_initial_call=True
)
def toggle_fab_modal(open_clicks, cancel_clicks, close_u, close_d, close_e, is_open):
    ctx = dash.callback_context
    if not ctx.triggered: raise dash.exceptions.PreventUpdate
    prop = ctx.triggered[0]["prop_id"]
    if prop.startswith("fab_open."):
        return True
    return False

# ===================== FAB: Salvar (gatilho único por Store) =====================
@dash.callback(
    Output("fab_feedback_u","children"),
    Output("fab_close_u","data"),
    Output("refresh_users","data", allow_duplicate=True),
    Input("fab_save","n_clicks"),
    State("fab_tabs","value"),
    State("fab_u_nome","value"),
    State("fab_u_email","value"),
    State("fab_u_perfil","value"),
    State("fab_u_modalidades","value"),
    State("fab_u_senha","value"),
    prevent_initial_call=True
)
def fab_save_user(n, tab_fab, nome, email, perfil, modalidades, senha):
    _ensure_button_trigger("fab_save")
    if tab_fab != "u":
        raise dash.exceptions.PreventUpdate
    cu = current_user()
    if not cu or cu.get("perfil") != "admin":
        return dbc.Alert("Acesso negado.", color="danger"), dash.no_update, dash.no_update

    msgs = []
    ok, nome = validate_text_input(nome, "Nome"); msgs += ([] if ok else [nome])
    ok, email = validate_text_input(email, "E-mail"); msgs += ([] if ok else [email])
    if ok and not validate_email_format(email): msgs.append("Formato de e-mail inválido.")
    elif find_user_by_email(email or ""): msgs.append("E-mail já cadastrado.")
    ok, perfil = validate_text_input(perfil, "Perfil"); msgs += ([] if ok else [perfil])
    if ok and perfil not in ["admin", "user"]: msgs.append("Perfil inválido.")
    ok, senha = validate_text_input(senha, "Senha"); msgs += ([] if ok else [senha])
    if ok and len((senha or "")) < 6: msgs.append("A senha deve ter pelo menos 6 caracteres.")

    if msgs:
        return dbc.Alert(html.Ul([html.Li(m) for m in msgs]), color="danger"), dash.no_update, dash.no_update

    rec = {
        "nome": (nome or "").strip(),
        "email": (email or "").strip().lower(),
        "senha_hash": generate_password_hash((senha or "").strip()),
        "modalidades_permitidas": (modalidades or "*").strip(),
        "perfil": perfil,
        "id": 0
    }
    uid = add_user(rec)
    log_action(cu.get("email"), "create", "user", uid, before=None,
               after={k:v for k,v in rec.items() if k != "senha_hash"})

    return dbc.Alert(f"Usuário criado (ID {uid}).", color="success", duration=3000), time.time(), time.time()

@dash.callback(
    Output("fab_feedback_d","children"),
    Output("fab_close_d","data"),
    Output("refresh_doctors","data", allow_duplicate=True),
    Input("fab_save","n_clicks"),
    State("fab_tabs","value"),
    State("fab_d_nome","value"),
    State("fab_d_crm","value"),
    prevent_initial_call=True
)
def fab_save_doctor(n, tab_fab, nome, crm):
    _ensure_button_trigger("fab_save")
    if tab_fab != "d":
        raise dash.exceptions.PreventUpdate
    cu = current_user()
    if not cu or cu.get("perfil") != "admin":
        return dbc.Alert("Acesso negado.", color="danger"), dash.no_update, dash.no_update

    ok, nome = validate_text_input(nome, "Nome")
    if not ok:
        return dbc.Alert(nome, color="danger"), dash.no_update, dash.no_update

    rec = {"nome": nome, "crm": (crm or "").strip() or None, "id": 0}
    did = add_doctor(rec)
    log_action(cu.get("email"), "create", "doctor", did, before=None, after=rec)

    return dbc.Alert(f"Médico criado (ID {did}).", color="success", duration=3000), time.time(), time.time()

@dash.callback(
    Output("fab_feedback_e","children"),
    Output("fab_close_e","data"),
    Output("refresh_examtypes","data", allow_duplicate=True),
    Input("fab_save","n_clicks"),
    State("fab_tabs","value"),
    State("fab_e_modalidade","value"),
    State("fab_e_nome","value"),
    State("fab_e_codigo","value"),
    prevent_initial_call=True
)
def fab_save_examtype(n, tab_fab, modalidade, nome, codigo):
    _ensure_button_trigger("fab_save")
    if tab_fab != "e":
        raise dash.exceptions.PreventUpdate
    cu = current_user()
    if not cu or cu.get("perfil") != "admin":
        return dbc.Alert("Acesso negado.", color="danger"), dash.no_update, dash.no_update

    msgs = []
    ok, modalidade = validate_text_input(modalidade, "Modalidade"); msgs += ([] if ok else [modalidade])
    if ok and modalidade not in MODALIDADES: msgs.append("Modalidade inválida.")
    ok, nome = validate_text_input(nome, "Nome"); msgs += ([] if ok else [nome])

    if msgs:
        return dbc.Alert(html.Ul([html.Li(m) for m in msgs]), color="danger"), dash.no_update, dash.no_update

    rec = {"modalidade": modalidade, "nome": nome, "codigo": (codigo or None), "id": 0}
    tid = add_exam_type(rec)
    log_action(cu.get("email"), "create", "exam_type", tid, before=None, after=rec)

    return dbc.Alert(f"Tipo de exame adicionado (ID {tid}).", color="success", duration=3000), time.time(), time.time()
