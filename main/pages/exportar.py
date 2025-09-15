# pages/exportar.py — Exportação de dados (CSV/JSON/ZIP) com filtros e compatibilidade
import io
import os
import csv
import zipfile
from datetime import datetime
from typing import Iterable, List, Dict, Any

import dash
from dash import html, dcc, get_app
import dash_bootstrap_components as dbc
from flask import Response, request, send_file

# ===== Backend: usa os mesmos arquivos/funções do app =====
from core.backend import (
    read_json,
    DATA_DIR,
    MATERIALS_FILE, EXAMS_FILE, DOCTORS_FILE, EXAMTYPES_FILE,
    LOGS_FILE, SETTINGS_FILE, USERS_FILE, STOCK_MOV_FILE, ESTOQUE_FILE,
)

dash.register_page(__name__, path="/exportar", name="Exportar")

# Flag interna para evitar duplicação de rotas em hot-reload
_ROUTES_REGISTERED = False


# =============== Helpers de data/CSV ===============
def _parse_dt(s: str | None) -> datetime | None:
    """Aceita YYYY-MM-DD ou ISO; retorna naive."""
    if not s:
        return None
    s = s.strip()
    try:
        if len(s) == 10 and s[4] == "-" and s[7] == "-":
            return datetime.fromisoformat(s + "T00:00:00")
        return datetime.fromisoformat(s.replace("Z", ""))
    except Exception:
        return None


def _csv_response(filename: str, rows: Iterable[Dict[str, Any]], headers: List[str]) -> Response:
    """Gera CSV com BOM (para Excel) e separador configurável via ?sep=;"""
    sep = request.args.get("sep", ",")
    buf = io.StringIO()
    writer = csv.writer(buf, delimiter=sep, lineterminator="\n")
    writer.writerow(headers)
    for r in rows:
        writer.writerow([r.get(h, "") if r.get(h) is not None else "" for h in headers])
    data = buf.getvalue().encode("utf-8-sig")
    return Response(
        data,
        mimetype="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'}
    )


def _zip_response(filename: str, files: Dict[str, bytes]) -> Response:
    bio = io.BytesIO()
    with zipfile.ZipFile(bio, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
        for path, content in files.items():
            zf.writestr(path, content)
    bio.seek(0)
    return send_file(
        bio,
        mimetype="application/zip",
        as_attachment=True,
        download_name=filename
    )


def _bytes_csv(rows: List[Dict[str, Any]], headers: List[str], sep: str = ",") -> bytes:
    sio = io.StringIO()
    w = csv.writer(sio, delimiter=sep, lineterminator="\n")
    w.writerow(headers)
    for r in rows:
        w.writerow([r.get(h, "") if r.get(h) is not None else "" for h in headers])
    return sio.getvalue().encode("utf-8-sig")


# =============== Normalizadores por dataset ===============
def _rows_materials() -> List[Dict[str, Any]]:
    mats = read_json(MATERIALS_FILE, {"materials": []})["materials"]
    out = []
    for m in mats:
        out.append({
            "id": m.get("id"),
            "nome": m.get("nome"),
            "tipo": m.get("tipo"),
            "unidade": m.get("unidade"),
            "valor_unitario": m.get("valor_unitario"),
            "estoque_inicial": m.get("estoque_inicial"),
            "estoque_minimo": m.get("estoque_minimo"),
        })
    return out


def _rows_estoque() -> List[Dict[str, Any]]:
    """
    Flattens estoque.json:
      {"<material_id>":[{"id":int,"lote":str,"validade":str,"saldo":float},...]}
    -> linhas: material_id, lote_id, lote, validade, saldo
    """
    est = read_json(ESTOQUE_FILE, {})
    out = []
    for k, lst in (est or {}).items():
        try:
            mid = int(k)
        except Exception:
            continue
        for b in lst or []:
            out.append({
                "material_id": mid,
                "lote_id": b.get("id"),
                "lote": b.get("lote"),
                "validade": b.get("validade"),
                "saldo": b.get("saldo"),
            })
    return out


def _rows_stock_movements() -> List[Dict[str, Any]]:
    rows = read_json(STOCK_MOV_FILE, {"movements": []})["movements"]
    # Filtros por ?from & ?to no campo ts
    dt_from = _parse_dt(request.args.get("from"))
    dt_to = _parse_dt(request.args.get("to"))
    out = []
    for m in rows:
        ts = m.get("ts")
        ok = True
        if dt_from:
            try:
                ok = ok and (datetime.fromisoformat((ts or "").replace("Z", "")) >= dt_from)
            except Exception:
                ok = False
        if dt_to:
            try:
                ok = ok and (datetime.fromisoformat((ts or "").replace("Z", "")) <= dt_to.replace(hour=23, minute=59, second=59))
            except Exception:
                ok = False
        if ok:
            out.append({
                "id": m.get("id"),
                "material_id": m.get("material_id"),
                "tipo": m.get("tipo"),
                "quantidade": m.get("quantidade"),
                "lote": m.get("lote"),
                "validade": m.get("validade"),
                "valor_unitario": m.get("valor_unitario"),
                "obs": m.get("obs"),
                "ts": ts,
            })
    return out


def _rows_exams() -> List[Dict[str, Any]]:
    rows = read_json(EXAMS_FILE, {"exams": []})["exams"]
    dt_from = _parse_dt(request.args.get("from"))
    dt_to = _parse_dt(request.args.get("to"))
    out = []
    for e in rows:
        dh = e.get("data_hora")
        ok = True
        if dt_from:
            try:
                ok = ok and (datetime.fromisoformat((dh or "").replace("Z", "")) >= dt_from)
            except Exception:
                ok = False
        if dt_to:
            try:
                ok = ok and (datetime.fromisoformat((dh or "").replace("Z", "")) <= dt_to.replace(hour=23, minute=59, second=59))
            except Exception:
                ok = False
        if ok:
            out.append({
                "id": e.get("id"),
                "exam_id": e.get("exam_id"),
                "modalidade": e.get("modalidade"),
                "exame": e.get("exame"),
                "medico": e.get("medico"),
                "data_hora": dh,
                "idade": e.get("idade"),
                "user_email": e.get("user_email"),
                "custo_estimado_total": e.get("custo_estimado_total"),
            })
    return out


def _rows_exam_items() -> List[Dict[str, Any]]:
    rows = read_json(EXAMS_FILE, {"exams": []})["exams"]
    dt_from = _parse_dt(request.args.get("from"))
    dt_to = _parse_dt(request.args.get("to"))
    out = []
    for e in rows:
        dh = e.get("data_hora")
        ok_ex = True
        if dt_from:
            try:
                ok_ex = ok_ex and (datetime.fromisoformat((dh or "").replace("Z", "")) >= dt_from)
            except Exception:
                ok_ex = False
        if dt_to:
            try:
                ok_ex = ok_ex and (datetime.fromisoformat((dh or "").replace("Z", "")) <= dt_to.replace(hour=23, minute=59, second=59))
            except Exception:
                ok_ex = False
        if not ok_ex:
            continue
        for it in (e.get("materiais_usados") or []):
            out.append({
                "exam_id": e.get("id"),
                "exam_code": e.get("exam_id"),
                "material_id": it.get("material_id"),
                "lote_id": it.get("lote_id"),
                "quantidade": it.get("quantidade"),
                "valor_unitario": it.get("valor_unitario"),
                "subtotal": it.get("subtotal"),
            })
    return out


def _rows_exam_types() -> List[Dict[str, Any]]:
    rows = read_json(EXAMTYPES_FILE, {"exam_types": []})["exam_types"]
    return [{"id": r.get("id"), "modalidade": r.get("modalidade"), "nome": r.get("nome"), "codigo": r.get("codigo")} for r in rows]


def _rows_doctors() -> List[Dict[str, Any]]:
    rows = read_json(DOCTORS_FILE, {"doctors": []})["doctors"]
    return [{"id": r.get("id"), "nome": r.get("nome")} for r in rows]


def _rows_users() -> List[Dict[str, Any]]:
    rows = read_json(USERS_FILE, {"users": []})["users"]
    out = []
    for u in rows:
        out.append({
            "id": u.get("id"),
            "nome": u.get("nome"),
            "email": u.get("email"),
            "modalidades_permitidas": u.get("modalidades_permitidas"),
            "perfil": u.get("perfil"),
        })
    return out


def _rows_logs() -> List[Dict[str, Any]]:
    rows = read_json(LOGS_FILE, {"logs": []})["logs"]
    return [{
        "ts": r.get("ts"),
        "user": r.get("user"),
        "action": r.get("action"),
        "entity": r.get("entity"),
        "entity_id": r.get("entity_id"),
    } for r in rows]


# =============== Rotas Flask (registradas no import do módulo) ===============
def _ensure_routes():
    global _ROUTES_REGISTERED
    if _ROUTES_REGISTERED:
        return
    app = get_app()
    server = app.server
    if getattr(server, "_export_routes_registered", False):
        _ROUTES_REGISTERED = True
        return

    @server.route("/export/materials.csv")
    def export_materials():
        rows = _rows_materials()
        headers = ["id", "nome", "tipo", "unidade", "valor_unitario", "estoque_inicial", "estoque_minimo"]
        return _csv_response("materials.csv", rows, headers)

    @server.route("/export/estoque.csv")
    @server.route("/export_estoque.csv")  # compat com link antigo
    def export_estoque():
        rows = _rows_estoque()
        headers = ["material_id", "lote_id", "lote", "validade", "saldo"]
        return _csv_response("estoque.csv", rows, headers)

    @server.route("/export/stock_movements.csv")
    def export_stock_mov():
        rows = _rows_stock_movements()
        headers = ["id", "material_id", "tipo", "quantidade", "lote", "validade", "valor_unitario", "obs", "ts"]
        return _csv_response("stock_movements.csv", rows, headers)

    @server.route("/export/exams.csv")
    def export_exams():
        rows = _rows_exams()
        headers = ["id", "exam_id", "modalidade", "exame", "medico", "data_hora", "idade", "user_email", "custo_estimado_total"]
        return _csv_response("exams.csv", rows, headers)

    @server.route("/export/exam_items.csv")
    def export_exam_items():
        rows = _rows_exam_items()
        headers = ["exam_id", "exam_code", "material_id", "lote_id", "quantidade", "valor_unitario", "subtotal"]
        return _csv_response("exam_items.csv", rows, headers)

    @server.route("/export/exam_types.csv")
    def export_examtypes():
        rows = _rows_exam_types()
        headers = ["id", "modalidade", "nome", "codigo"]
        return _csv_response("exam_types.csv", rows, headers)

    @server.route("/export/doctors.csv")
    def export_doctors():
        rows = _rows_doctors()
        headers = ["id", "nome"]
        return _csv_response("doctors.csv", rows, headers)

    @server.route("/export/users.csv")
    def export_users():
        rows = _rows_users()
        headers = ["id", "nome", "email", "modalidades_permitidas", "perfil"]
        return _csv_response("users.csv", rows, headers)

    @server.route("/export/logs.csv")
    def export_logs():
        rows = _rows_logs()
        headers = ["ts", "user", "action", "entity", "entity_id"]
        return _csv_response("logs.csv", rows, headers)

    @server.route("/export/settings.json")
    def export_settings_json():
        return send_file(SETTINGS_FILE, mimetype="application/json", as_attachment=True, download_name="settings.json")

    @server.route("/export/notifications.csv")
    def export_notifications():
        # notifications.json é opcional
        path = os.path.join(DATA_DIR, "notifications.json")
        rows = read_json(path, {"notifications": []}).get("notifications", [])
        norm = []
        for n in rows:
            base = {
                "id": n.get("id"),
                "ts": n.get("ts") or n.get("created_at"),
                "type": n.get("type") or n.get("categoria"),
                "title": n.get("title") or n.get("titulo"),
                "message": n.get("message") or n.get("mensagem"),
                "user": n.get("user") or n.get("email"),
            }
            for k, v in (n or {}).items():
                if k not in base:
                    base[k] = v
            norm.append(base)
        headers = []
        for r in norm:
            for k in r.keys():
                if k not in headers:
                    headers.append(k)
        return _csv_response("notifications.csv", norm, headers or ["id", "ts", "type", "title", "message", "user"])

    @server.route("/export/all.zip")
    def export_all_zip():
        sep = request.args.get("sep", ",")
        files: Dict[str, bytes] = {
            "materials.csv": _bytes_csv(_rows_materials(), ["id", "nome", "tipo", "unidade", "valor_unitario", "estoque_inicial", "estoque_minimo"], sep),
            "estoque.csv": _bytes_csv(_rows_estoque(), ["material_id", "lote_id", "lote", "validade", "saldo"], sep),
            "stock_movements.csv": _bytes_csv(_rows_stock_movements(), ["id", "material_id", "tipo", "quantidade", "lote", "validade", "valor_unitario", "obs", "ts"], sep),
            "exams.csv": _bytes_csv(_rows_exams(), ["id", "exam_id", "modalidade", "exame", "medico", "data_hora", "idade", "user_email", "custo_estimado_total"], sep),
            "exam_items.csv": _bytes_csv(_rows_exam_items(), ["exam_id", "exam_code", "material_id", "lote_id", "quantidade", "valor_unitario", "subtotal"], sep),
            "exam_types.csv": _bytes_csv(_rows_exam_types(), ["id", "modalidade", "nome", "codigo"], sep),
            "doctors.csv": _bytes_csv(_rows_doctors(), ["id", "nome"], sep),
            "users.csv": _bytes_csv(_rows_users(), ["id", "nome", "email", "modalidades_permitidas", "perfil"], sep),
            "logs.csv": _bytes_csv(_rows_logs(), ["ts", "user", "action", "entity", "entity_id"], sep),
        }
        try:
            with open(SETTINGS_FILE, "rb") as f:
                files["settings.json"] = f.read()
        except Exception:
            pass
        notif_path = os.path.join(DATA_DIR, "notifications.json")
        if os.path.exists(notif_path):
            with open(notif_path, "rb") as f:
                files["notifications.json"] = f.read()
        return _zip_response("export_all.zip", files)

    server._export_routes_registered = True
    _ROUTES_REGISTERED = True


# >>> Registra as rotas AGORA (no import do módulo), antes do 1º request
#     Isso evita o erro de “setup method 'route' … already handled its first request”.
_ensure_routes()


# =============== Layout ===============
def layout():
    base = "/export"
    hint = html.Small("Dica: use ?from=YYYY-MM-DD&to=YYYY-MM-DD e/ou ?sep=; nos links.", className="text-muted")

    return dbc.Container([
        dbc.Card([
            dbc.CardHeader([html.I(className="fa-solid fa-file-export me-2"), "Exportação de Dados"]),
            dbc.CardBody([
                html.P("Baixe os dados em CSV/JSON. Filtros de data valem para movimentações e exames."),
                hint,
                html.Hr(),
                dbc.Row([
                    dbc.Col(dbc.ListGroup([
                        dbc.ListGroupItem(html.A("Estoque (lotes) — estoque.csv", href=f"{base}/estoque.csv", className="text-decoration-none")),
                        dbc.ListGroupItem(html.A("Movimentações — stock_movements.csv", href=f"{base}/stock_movements.csv", className="text-decoration-none")),
                        dbc.ListGroupItem(html.A("Materiais — materials.csv", href=f"{base}/materials.csv", className="text-decoration-none")),
                        dbc.ListGroupItem(html.A("Tipos de Exame — exam_types.csv", href=f"{base}/exam_types.csv", className="text-decoration-none")),
                    ]), md=6),
                    dbc.Col(dbc.ListGroup([
                        dbc.ListGroupItem(html.A("Exames — exams.csv", href=f"{base}/exams.csv", className="text-decoration-none")),
                        dbc.ListGroupItem(html.A("Itens dos Exames — exam_items.csv", href=f"{base}/exam_items.csv", className="text-decoration-none")),
                        dbc.ListGroupItem(html.A("Médicos — doctors.csv", href=f"{base}/doctors.csv", className="text-decoration-none")),
                        dbc.ListGroupItem(html.A("Usuários — users.csv", href=f"{base}/users.csv", className="text-decoration-none")),
                        dbc.ListGroupItem(html.A("Logs — logs.csv", href=f"{base}/logs.csv", className="text-decoration-none")),
                    ]), md=6),
                ], className="g-3"),
                html.Hr(),
                html.Div(className="d-flex align-items-center gap-2", children=[
                    html.A("Baixar tudo (ZIP)", href=f"{base}/all.zip", className="btn btn-primary"),
                    html.A("Baixar settings.json", href=f"{base}/settings.json", className="btn btn-outline-secondary"),
                    html.A("Baixar notifications.csv", href=f"{base}/notifications.csv", className="btn btn-outline-secondary"),
                    html.Small("Compat.: /export_estoque.csv continua válido.", className="text-muted ms-auto"),
                ]),
            ])
        ], className="shadow-sm")
    ], fluid=True)
