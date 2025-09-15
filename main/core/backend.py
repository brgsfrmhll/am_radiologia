# core/backend.py
import os, json, threading, re
from datetime import datetime, timedelta
from werkzeug.security import generate_password_hash

# ================== Paths / Arquivos ==================
DATA_DIR = os.getenv("DATA_DIR", "data")
UPLOAD_DIR = os.path.join(DATA_DIR, "uploads")

USERS_FILE      = os.getenv("USERS_FILE",      os.path.join(DATA_DIR, "users.json"))
EXAMS_FILE      = os.getenv("EXAMS_FILE",      os.path.join(DATA_DIR, "exams.json"))
DOCTORS_FILE    = os.getenv("DOCTORS_FILE",    os.path.join(DATA_DIR, "doctors.json"))
EXAMTYPES_FILE  = os.getenv("EXAMTYPES_FILE",  os.path.join(DATA_DIR, "exam_types.json"))
LOGS_FILE       = os.getenv("LOGS_FILE",       os.path.join(DATA_DIR, "logs.json"))
SETTINGS_FILE   = os.getenv("SETTINGS_FILE",   os.path.join(DATA_DIR, "settings.json"))
MATERIALS_FILE  = os.getenv("MATERIALS_FILE",  os.path.join(DATA_DIR, "materials.json"))
STOCK_MOV_FILE  = os.getenv("STOCK_MOV_FILE",  os.path.join(DATA_DIR, "stock_movements.json"))

# >>> Arquivo de lotes/validade/saldo (fonte-verdade do saldo atual por material)
ESTOQUE_FILE    = os.getenv("ESTOQUE_FILE",    os.path.join(DATA_DIR, "estoque.json"))

THEMES = {
    "Flatly":"https://cdn.jsdelivr.net/npm/bootswatch@5.3.3/dist/flatly/bootstrap.min.css",
    "Lux":"https://cdn.jsdelivr.net/npm/bootswatch@5.3.3/dist/lux/bootstrap.min.css",
    "Materia":"https://cdn.jsdelivr.net/npm/bootswatch@5.3.3/dist/materia/bootstrap.min.css",
    "Yeti":"https://cdn.jsdelivr.net/npm/bootswatch@5.3.3/dist/yeti/bootstrap.min.css",
    "Morph":"https://cdn.jsdelivr.net/npm/bootswatch@5.3.3/dist/morph/bootstrap.min.css",
    "Quartz":"https://cdn.jsdelivr.net/npm/bootswatch@5.3.3/dist/quartz/bootstrap.min.css",
    "Cyborg (escuro)":"https://cdn.jsdelivr.net/npm/bootswatch@5.3.3/dist/cyborg/bootstrap.min.css",
}
DEFAULT_SETTINGS = {"portal_name":"Portal Radiológico","theme":"Flatly","logo_file":None,"logo_height_px":40}

MODALIDADES = ["RX","CT","US","MR","MG","NM"]
MOD_LABEL = {"RX":"Raio-X","CT":"Tomografia","US":"Ultrassom","MR":"Ressonância","MG":"Mamografia","NM":"Medicina Nuclear"}
def mod_label(m): return MOD_LABEL.get(m, m or "")

MATERIAL_TYPES = ["Material","Contraste"]

# ================== Locks ==================
_users_lock = threading.Lock()
_exams_lock = threading.Lock()
_doctors_lock = threading.Lock()
_examtypes_lock = threading.Lock()
_logs_lock = threading.Lock()
_settings_lock = threading.Lock()
_materials_lock = threading.Lock()
_stockmov_lock = threading.Lock()
_estoque_lock = threading.Lock()

# ================== Utilitários I/O ==================
def ensure_dirs():
    os.makedirs(DATA_DIR, exist_ok=True)
    os.makedirs(UPLOAD_DIR, exist_ok=True)

def read_json(path, default):
    if not os.path.exists(path): 
        return default
    try:
        with open(path,"r",encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default

def write_json(path, data, lock):
    tmp = path + ".tmp"
    with lock:
        with open(tmp,"w",encoding="utf-8") as f:
            json.dump(data,f,ensure_ascii=False,indent=2)
        os.replace(tmp, path)

# ================== Settings ==================
def read_settings():
    s = read_json(SETTINGS_FILE, DEFAULT_SETTINGS.copy())
    if s.get("theme") not in THEMES: 
        s["theme"] = "Flatly"
    if "logo_height_px" not in s: 
        s["logo_height_px"] = DEFAULT_SETTINGS["logo_height_px"]
    return s

def write_settings(s):
    cur = read_settings(); cur.update(s or {})
    write_json(SETTINGS_FILE, cur, _settings_lock); 
    return cur

SEED_USER = {
    "nome":"Administrador","email":"admin@local",
    "senha_hash":generate_password_hash("admin123"),
    "modalidades_permitidas":"*","perfil":"admin","id":1
}

# ================== Seed básico ==================
def init_files():
    ensure_dirs()
    users = read_json(USERS_FILE, {"users":[]})
    if not users["users"]:
        write_json(USERS_FILE, {"users":[SEED_USER]}, _users_lock)

    if not os.path.exists(SETTINGS_FILE):
        write_json(SETTINGS_FILE, DEFAULT_SETTINGS.copy(), _settings_lock)

    et = read_json(EXAMTYPES_FILE, {"exam_types":[]})
    if not et["exam_types"]:
        seed_types = [
            {"id":1,"modalidade":"RX","nome":"Tórax PA/L","codigo":"RX001"},
            {"id":2,"modalidade":"CT","nome":"Crânio","codigo":"CT001"},
            {"id":3,"modalidade":"US","nome":"Abdômen total","codigo":"US001"},
        ]
        write_json(EXAMTYPES_FILE, {"exam_types":seed_types}, _examtypes_lock)

    ex = read_json(EXAMS_FILE, {"exams":[]})
    if not ex["exams"]:
        now = datetime.utcnow()
        seed_exams = [
            {"id":1,"exam_id":"E-0001","idade":45,"modalidade":"CT","exame":f"{mod_label('CT')} - Crânio",
             "medico":"Dr. João","data_hora":(now-timedelta(days=2)).isoformat(),"user_email":"admin@local",
             "materiais_usados":[{"material_id":1,"quantidade":80.0}]},
        ]
        write_json(EXAMS_FILE, {"exams":seed_exams}, _exams_lock)

    if "doctors" not in read_json(DOCTORS_FILE, {"doctors":[]}):
        write_json(DOCTORS_FILE, {"doctors":[]}, _doctors_lock)
    if "logs" not in read_json(LOGS_FILE, {"logs":[]}):
        write_json(LOGS_FILE, {"logs":[]}, _logs_lock)

    mats = read_json(MATERIALS_FILE, {"materials":[]})
    if not mats["materials"]:
        seed_materials = [
            {"id":1,"nome":"Gadolinio","tipo":"Contraste","unidade":"mL","valor_unitario":1.50,"estoque_inicial":2000.0,"estoque_minimo":500.0},
            {"id":2,"nome":"Luva Estéril","tipo":"Material","unidade":"par","valor_unitario":2.00,"estoque_inicial":500.0,"estoque_minimo":100.0},
            {"id":3,"nome":"Soro Fisiológico 0,9%","tipo":"Material","unidade":"mL","valor_unitario":0.02,"estoque_inicial":5000.0,"estoque_minimo":500.0},
        ]
        write_json(MATERIALS_FILE, {"materials":seed_materials}, _materials_lock)

    stock = read_json(STOCK_MOV_FILE, {"movements":[]})
    if "movements" not in stock:
        write_json(STOCK_MOV_FILE, {"movements":[]}, _stockmov_lock)

    # Seed de lotes (somente se estoque.json não existir/estiver vazio)
    est = read_json(ESTOQUE_FILE, {})
    if not est:
        est = {
            "1": [
                {"id": 101, "lote": "GAD-A123", "validade": "2026-12-31", "saldo": 1200.0},
                {"id": 102, "lote": "GAD-B456", "validade": "2027-06-30", "saldo": 800.0},
            ],
            "2": [
                {"id": 201, "lote": "LUV-2025-01", "validade": "2025-01-31", "saldo": 300.0},
                {"id": 202, "lote": "LUV-2025-10", "validade": "2025-10-31", "saldo": 200.0},
            ],
            "3": [
                {"id": 301, "lote": "SOR-2026-02", "validade": "2026-02-28", "saldo": 5000.0}
            ]
        }
        write_json(ESTOQUE_FILE, est, _estoque_lock)

# criar arquivos na importação
init_files()

# ================== Repositórios simples ==================
def get_users(): return read_json(USERS_FILE, {"users":[]})["users"]
def save_users(users): write_json(USERS_FILE, {"users":users}, _users_lock)
def find_user_by_email(email):
    email = (email or "").strip().lower()
    return next((u for u in get_users() if (u.get("email","") or "").lower()==email), None)

def list_exam_types(): return read_json(EXAMTYPES_FILE, {"exam_types":[]})["exam_types"]
def list_materials(): return read_json(MATERIALS_FILE, {"materials":[]})["materials"]
def list_stock_movements(): return read_json(STOCK_MOV_FILE, {"movements":[]})["movements"]
def list_exams(): return read_json(EXAMS_FILE, {"exams":[]})["exams"]
def list_doctors(): return read_json(DOCTORS_FILE, {"doctors":[]})["doctors"]
def save_doctors(docs): write_json(DOCTORS_FILE, {"doctors":docs}, _doctors_lock)

# ================== Agregações ==================
def aggregate_exam_material_usage():
    usage = {}
    for e in list_exams():
        for item in e.get("materiais_usados", []) or []:
            mid = item.get("material_id"); qty = float(item.get("quantidade") or 0)
            if mid: usage[mid] = usage.get(mid, 0.0) + qty
    return usage

def aggregate_manual_movements():
    """
    Soma somente movimentações manuais (entrada/saida/ajuste) por material, a partir de stock_movements.json.
    NÃO inclui consumo de exame (que não gera movimento aqui).
    """
    acc = {}
    for m in list_stock_movements():
        mid = m.get("material_id")
        if not mid: 
            continue
        d = acc.setdefault(mid, {"entrada":0.0,"saida":0.0,"ajuste":0.0})
        t = (m.get("tipo") or "").lower()  # entrada|saida|ajuste
        q = float(m.get("quantidade") or 0)
        if t in d: 
            d[t] += q
    return acc

# ================== Estoque (lotes) — helpers ==================
def _read_estoque():
    return read_json(ESTOQUE_FILE, {})

def _write_estoque(e):
    write_json(ESTOQUE_FILE, e, _estoque_lock)

def _all_batch_max_id(est):
    mx = 0
    for rows in est.values():
        for r in rows:
            try:
                mx = max(mx, int(r.get("id") or 0))
            except Exception:
                pass
    return mx

def _find_batch(est, mid: int, lote: str | None, validade: str | None):
    rows = est.get(str(mid), []) or []
    for r in rows:
        if (r.get("lote") or None) == (lote or None) and (r.get("validade") or None) == (validade or None):
            return r
    return None

def _ensure_batch(est, mid: int, lote: str | None, validade: str | None):
    """
    Garante a existência de um lote (por par lote+validade). 
    Se não existir, cria com novo id e saldo 0.
    Retorna o dicionário do lote.
    """
    rows = est.setdefault(str(mid), [])
    b = _find_batch(est, mid, lote, validade)
    if b:
        return b
    nid = _all_batch_max_id(est) + 1
    b = {"id": nid, "lote": lote or None, "validade": validade or None, "saldo": 0.0}
    rows.append(b)
    return b

def _fifo_batches(est, mid: int):
    rows = [r for r in est.get(str(mid), []) or [] if float(r.get("saldo") or 0.0) > 0.0]
    rows.sort(key=lambda x: (x.get("validade") or "9999-99-99"))
    return rows

def _sum_batches(est, mid: int):
    return sum(float(r.get("saldo") or 0.0) for r in est.get(str(mid), []) or [])

# ================== Snapshot ==================
def compute_stock_snapshot():
    """
    Monta o snapshot gerencial:
    - 'estoque_atual' PRIORITÁRIO do estoque.json (soma de saldos por lotes).
    - Fallback para fórmula quando não há lotes cadastrados para o material.
    """
    mats  = list_materials()
    usage = aggregate_exam_material_usage()
    moves = aggregate_manual_movements()
    est   = _read_estoque()

    snap = []
    for m in mats:
        mid = m["id"]
        ini = float(m.get("estoque_inicial") or 0.0)
        minimo = float(m.get("estoque_minimo") or 0.0)
        mm = moves.get(mid, {"entrada":0.0,"saida":0.0,"ajuste":0.0})
        cons = float(usage.get(mid, 0.0))

        # saldo atual: prefere estoque.json
        if str(mid) in est and len(est[str(mid)] or []) > 0:
            atual = _sum_batches(est, mid)
        else:
            # sem lotes: usa fórmula (compatibilidade com dados antigos)
            atual = ini + mm["entrada"] - mm["saida"] + mm["ajuste"] - cons

        abaixo = atual < minimo if minimo > 0 else False
        snap.append({
            "id": mid, "nome": m.get("nome"), "tipo": m.get("tipo"), "unidade": m.get("unidade"),
            "valor_unitario": float(m.get("valor_unitario") or 0.0),
            "estoque_inicial": ini, "estoque_minimo": minimo,
            "consumo_exames": cons, "entradas": mm["entrada"], "saidas": mm["saida"], "ajustes": mm["ajuste"],
            "estoque_atual": atual, "abaixo_minimo": abaixo
        })
    snap.sort(key=lambda x: (x["nome"] or "").lower())
    return snap

def format_dt_br(iso_str):
    try: 
        return datetime.fromisoformat(iso_str).strftime("%d/%m/%Y %H:%M")
    except Exception: 
        return iso_str

# ================== IDs ==================
def _next_id(items):
    maxid = 0
    for it in items:
        try: maxid = max(maxid, int(it.get("id") or 0))
        except Exception: pass
    return maxid + 1

def _nx_id(items):
    return _next_id(items)

# ================== CUSTOS ==================
def material_price_map():
    return {m["id"]: float(m.get("valor_unitario") or 0.0) for m in list_materials()}

def estimate_items_cost(items: list):
    """
    Enriquecimento com preço e subtotal.
    Entrada: [{"material_id":int,"quantidade":float,"lote_id":int|None}, ...]
    Saída: (itens_enriquecidos, total)
    """
    pm = material_price_map()
    enriched = []
    total = 0.0
    for it in (items or []):
        if not it or "material_id" not in it:
            continue
        mid = int(it["material_id"])
        qtd = float(it.get("quantidade") or 0.0)
        if qtd <= 0:
            continue
        vu = float(pm.get(mid, 0.0))
        sub = round(vu * qtd, 6)
        enriched.append({
            "material_id": mid,
            "quantidade": qtd,
            "lote_id": int(it["lote_id"]) if it.get("lote_id") not in (None, "", "null") else None,
            "valor_unitario": vu,
            "subtotal": sub,
        })
        total += sub
    return enriched, round(total, 6)

def preview_exam_cost(items: list) -> dict:
    its, tot = estimate_items_cost(items)
    return {"total": tot, "itens": its}

# ================== Exames ==================
def add_or_update_exam(exam: dict):
    data = read_json(EXAMS_FILE, {"exams":[]})
    exams = data["exams"]

    # UPDATE simples (não mexe em estoque)
    if exam.get("id"):
        for i, e in enumerate(exams):
            if e.get("id") == exam["id"]:
                exams[i] = exam
                write_json(EXAMS_FILE, {"exams":exams}, _exams_lock)
                return exam["id"]

    # INSERT: calcula custo e baixa nos lotes/FIFO (APENAS estoque.json)
    itens_raw = list(exam.get("materiais_usados") or [])
    itens_enriq, total = estimate_items_cost(itens_raw)

    # 1) Baixa efetiva no estoque por lotes/FIFO
    consume_stock_by_batches(itens_enriq)

    # 2) NÃO registrar 'saida' em stock_movements.json para exames (evita saída em dobro)
    #    Se desejar log, use log_action(...).

    # grava exame
    exam = exam.copy()
    exam["materiais_usados"] = itens_enriq
    exam["custo_estimado_total"] = total
    exam["id"] = _next_id(exams)
    exams.append(exam)
    write_json(EXAMS_FILE, {"exams":exams}, _exams_lock)
    return exam["id"]

def ensure_doctor(name: str):
    if not name: 
        return
    docs = list_doctors()
    if not any(d.get("nome","").strip().lower()==name.strip().lower() for d in docs):
        docs.append({"id": _next_id(docs), "nome": name})
        save_doctors(docs)

def get_examtype_names(modalidade=None):
    lst = list_exam_types()
    if modalidade:
        lst = [x for x in lst if (x.get("modalidade")==modalidade)]
    names = []
    for x in lst:
        nm = x.get("nome") or ""
        if nm and nm not in names:
            names.append(nm)
    return names

def doctor_names():
    names = [d.get("nome") for d in list_doctors() if d.get("nome")]
    for e in list_exams():
        nm = e.get("medico")
        if nm and nm not in names:
            names.append(nm)
    return names

# ================== Logs / Validations / CRUDs Gerenciais ==================
def list_logs():
    return read_json(LOGS_FILE, {"logs":[]})["logs"]

def save_logs(rows):
    write_json(LOGS_FILE, {"logs":rows}, _logs_lock)

def log_action(user_email, action, entity, entity_id, before=None, after=None):
    rows = list_logs()
    rows.append({
        "ts": datetime.utcnow().isoformat(),
        "user": user_email,
        "action": action,           # create|update|delete
        "entity": entity,           # user|doctor|exam_type|...
        "entity_id": entity_id,
        "before": before,
        "after": after,
    })
    save_logs(rows)

def validate_text_input(value, label):
    val = (value or "").strip()
    if not val:
        return False, f"{label} é obrigatório."
    return True, val

def validate_positive_int(value, label, min_v=0, max_v=None):
    try:
        iv = int(value)
        if iv < min_v or (max_v is not None and iv > max_v):
            return False, f"{label} deve estar entre {min_v} e {max_v}."
        return True, iv
    except Exception:
        return False, f"{label} inválido."

def validate_positive_float(value, label, min_v=0.0, max_v=None):
    try:
        fv = float(value)
        if fv < min_v or (max_v is not None and fv > max_v):
            return False, f"{label} deve estar entre {min_v} e {max_v}."
        return True, fv
    except Exception:
        return False, f"{label} inválido."

def validate_email_format(email):
    return bool(re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", (email or "").strip()))

# ---------- Users ----------
def add_user(rec):
    data = read_json(USERS_FILE, {"users":[]})
    users = data["users"]
    rec = rec.copy()
    rec["id"] = _next_id(users)
    users.append(rec)
    write_json(USERS_FILE, {"users":users}, _users_lock)
    return rec["id"]

def update_user(uid, fields):
    data = read_json(USERS_FILE, {"users":[]})
    users = data["users"]
    ok = False
    for i,u in enumerate(users):
        if u.get("id")==uid:
            before = users[i].copy()
            users[i].update(fields or {})
            ok = True
            break
    if ok:
        write_json(USERS_FILE, {"users":users}, _users_lock)
    return ok

def delete_user(uid):
    data = read_json(USERS_FILE, {"users":[]})
    users = data["users"]
    n = len(users)
    users = [u for u in users if u.get("id")!=uid]
    write_json(USERS_FILE, {"users":users}, _users_lock)
    return len(users) < n

# ---------- Doctors ----------
def add_doctor(rec):
    data = read_json(DOCTORS_FILE, {"doctors":[]})
    docs = data["doctors"]
    rec = rec.copy(); rec["id"] = _next_id(docs)
    docs.append(rec)
    write_json(DOCTORS_FILE, {"doctors":docs}, _doctors_lock)
    return rec["id"]

def update_doctor(did, fields):
    data = read_json(DOCTORS_FILE, {"doctors":[]})
    docs = data["doctors"]
    ok = False
    for i,d in enumerate(docs):
        if d.get("id")==did:
            docs[i].update(fields or {})
            ok = True
            break
    if ok:
        write_json(DOCTORS_FILE, {"doctors":docs}, _doctors_lock)
    return ok

def delete_doctor(did):
    data = read_json(DOCTORS_FILE, {"doctors":[]})
    docs = data["doctors"]
    n = len(docs)
    docs = [d for d in docs if d.get("id")!=did]
    write_json(DOCTORS_FILE, {"doctors":docs}, _doctors_lock)
    return len(docs) < n

# ---------- Exam Types ----------
def add_exam_type(rec):
    data = read_json(EXAMTYPES_FILE, {"exam_types":[]})
    rows = data["exam_types"]
    rec = rec.copy(); rec["id"] = _next_id(rows)
    rows.append(rec)
    write_json(EXAMTYPES_FILE, {"exam_types":rows}, _examtypes_lock)
    return rec["id"]

def update_exam_type(tid, fields):
    data = read_json(EXAMTYPES_FILE, {"exam_types":[]})
    rows = data["exam_types"]
    ok=False
    for i,t in enumerate(rows):
        if t.get("id")==tid:
            rows[i].update(fields or {})
            ok=True; break
    if ok:
        write_json(EXAMTYPES_FILE, {"exam_types":rows}, _examtypes_lock)
    return ok

def delete_exam_type(tid):
    data = read_json(EXAMTYPES_FILE, {"exam_types":[]})
    rows = data["exam_types"]
    n=len(rows)
    rows = [t for t in rows if t.get("id")!=tid]
    write_json(EXAMTYPES_FILE, {"exam_types":rows}, _examtypes_lock)
    return len(rows) < n

# ================== Materiais ==================
def add_material(rec: dict) -> int:
    data = read_json(MATERIALS_FILE, {"materials":[]})
    rows = data["materials"]
    nrec = rec.copy()
    nrec["id"] = _nx_id(rows)
    # sane defaults
    nrec.setdefault("tipo", "Material")
    nrec.setdefault("unidade", "")
    nrec["valor_unitario"]  = float(nrec.get("valor_unitario") or 0.0)
    nrec["estoque_inicial"] = float(nrec.get("estoque_inicial") or 0.0)
    nrec["estoque_minimo"]  = float(nrec.get("estoque_minimo") or 0.0)

    rows.append(nrec)
    write_json(MATERIALS_FILE, {"materials": rows}, _materials_lock)
    return nrec["id"]

def update_material(mid: int, fields: dict) -> bool:
    data = read_json(MATERIALS_FILE, {"materials":[]})
    rows = data["materials"]
    ok = False
    for i, m in enumerate(rows):
        if m.get("id") == int(mid):
            upd = fields.copy() if fields else {}
            for k in ("valor_unitario","estoque_inicial","estoque_minimo"):
                if k in upd and upd[k] not in (None, ""):
                    try: upd[k] = float(upd[k])
                    except Exception: pass
            rows[i].update(upd)
            ok = True
            break
    if ok:
        write_json(MATERIALS_FILE, {"materials": rows}, _materials_lock)
    return ok

def delete_material(mid: int) -> bool:
    data = read_json(MATERIALS_FILE, {"materials":[]})
    rows = data["materials"]
    n0 = len(rows)
    rows = [m for m in rows if m.get("id") != int(mid)]
    write_json(MATERIALS_FILE, {"materials": rows}, _materials_lock)

    # também remove lotes do estoque.json daquele material
    est = _read_estoque()
    if str(int(mid)) in est:
        del est[str(int(mid))]
        _write_estoque(est)

    return len(rows) < n0

# ================== Movimentações manuais (sincroniza estoque.json) ==================
def _to_float_or_none(x):
    try:
        if x in (None, ""): 
            return None
        return float(x)
    except Exception:
        return None

def list_stock_movements_by_material(mid: int):
    rows = list_stock_movements()
    return [r for r in rows if int(r.get("material_id") or 0) == int(mid)]

def add_stock_movement(rec: dict) -> int:
    """
    Registra uma movimentação manual em stock_movements.json e
    SINCRONIZA no estoque.json (lotes).
    Use APENAS para entradas/saídas/ajustes fora do exame.
    Exames já consomem do estoque via consume_stock_by_batches() e
    NÃO devem ser registrados aqui como 'saida'.
    """
    # --- valida e persiste movimento ---
    data = read_json(STOCK_MOV_FILE, {"movements":[]})
    rows = data["movements"]

    mov = {
        "id": _nx_id(rows),
        "material_id": int(rec.get("material_id")),
        "tipo": (rec.get("tipo") or "").lower().strip(),  # entrada|saida|ajuste
        "quantidade": float(rec.get("quantidade") or 0.0),
        "lote": (rec.get("lote") or "").strip() or None,
        "validade": (rec.get("validade") or "").strip() or None,      # ISO 'YYYY-MM-DD' preferível
        "valor_unitario": _to_float_or_none(rec.get("valor_unitario")),
        "obs": (rec.get("obs") or "").strip() or None,
        "ts": datetime.utcnow().isoformat()
    }
    if mov["tipo"] not in ("entrada", "saida", "ajuste"):
        raise ValueError("Tipo de movimentação inválido.")
    if mov["quantidade"] <= 0:
        raise ValueError("Quantidade deve ser maior que zero.")

    rows.append(mov)
    write_json(STOCK_MOV_FILE, {"movements": rows}, _stockmov_lock)

    # --- refletir no estoque.json ---
    est = _read_estoque()
    mid = mov["material_id"]
    qtd = mov["quantidade"]
    lote = mov["lote"]
    validade = mov["validade"]

    if mov["tipo"] == "entrada":
        b = _ensure_batch(est, mid, lote, validade)
        b["saldo"] = float(b.get("saldo") or 0.0) + qtd

    elif mov["tipo"] == "saida":
        if lote or validade:
            b = _find_batch(est, mid, lote, validade)
            if not b:
                raise ValueError("Lote/validade não encontrado para saída.")
            cur = float(b.get("saldo") or 0.0)
            if cur + 1e-9 < qtd:
                raise ValueError("Saldo insuficiente no lote para saída.")
            b["saldo"] = round(cur - qtd, 6)
        else:
            resto = qtd
            for r in _fifo_batches(est, mid):
                if resto <= 0:
                    break
                cur = float(r.get("saldo") or 0.0)
                if cur <= 0:
                    continue
                take = min(cur, resto)
                r["saldo"] = round(cur - take, 6)
                resto -= take
            if resto > 1e-9:
                raise ValueError("Saldo insuficiente para saída (FIFO).")

    elif mov["tipo"] == "ajuste":
        # Ajuste positivo: como entrada no lote (ou cria sem info)
        # Ajuste negativo: como saída (FIFO ou lote/validade)
        # Aqui usamos a mesma interface: 'quantidade' é POSITIVA; sinal é implícito pela intenção:
        # Se quiser ajuste negativo em lote específico, preencha lote/validade e 'quantidade' = valor a retirar.
        # Se quiser ajustar positivo em lote/validade, idem.
        # Para manter simples: usamos 'lote/validade' se fornecidos; caso contrário, FIFO (para retirar) ou cria/usa lote None para adicionar.
        # Como não há sinal explícito, seguimos a convenção:
        # - Se valor_unitario presente ou obs mencionar "ajuste +" podemos considerar entrada, mas isso é heurístico.
        # Melhor: usuário escolhe no front "AJUSTE" e informa lote + e/ou usa campo quantidade e sentido via obs.
        # Para robustez, trataremos sempre como ajuste *positivo* quando há valor_unitario explícito OU quando obs contém "+",
        # e como ajuste *negativo* quando obs contém "-" (fallback FIFO).
        obs = (mov.get("obs") or "").strip()
        ajuste_positivo = False
        if mov["valor_unitario"] is not None or ("+" in obs and "-" not in obs):
            ajuste_positivo = True
        if "-" in obs and "+" not in obs:
            ajuste_positivo = False

        if ajuste_positivo:
            b = _ensure_batch(est, mid, lote, validade)
            b["saldo"] = float(b.get("saldo") or 0.0) + qtd
        else:
            if lote or validade:
                b = _find_batch(est, mid, lote, validade)
                if not b:
                    raise ValueError("Lote/validade não encontrado para ajuste negativo.")
                cur = float(b.get("saldo") or 0.0)
                if cur + 1e-9 < qtd:
                    raise ValueError("Saldo insuficiente no lote para ajuste negativo.")
                b["saldo"] = round(cur - qtd, 6)
            else:
                resto = qtd
                for r in _fifo_batches(est, mid):
                    if resto <= 0:
                        break
                    cur = float(r.get("saldo") or 0.0)
                    if cur <= 0:
                        continue
                    take = min(cur, resto)
                    r["saldo"] = round(cur - take, 6)
                    resto -= take
                if resto > 1e-9:
                    raise ValueError("Saldo insuficiente para ajuste negativo (FIFO).")

    _write_estoque(est)
    return mov["id"]

# ================== Lotes para UI ==================
def list_material_batches(material_id: int):
    """
    Retorna lista de lotes ATIVOS (saldo > 0) para um material:
    [{id, material_id, lote, validade, saldo}]
    """
    try:
        estoque = _read_estoque()
        rows = estoque.get(str(int(material_id)), []) or []
        out = []
        for b in rows:
            try:
                saldo = float(b.get("saldo") or 0.0)
            except Exception:
                saldo = 0.0
            if saldo <= 0:
                continue
            out.append({
                "id": int(b.get("id")),
                "material_id": int(material_id),
                "lote": b.get("lote") or "-",
                "validade": b.get("validade") or "-",
                "saldo": saldo
            })
        out.sort(key=lambda bb: (bb.get("validade") or "9999-99-99"))
        return out
    except Exception:
        return []

# ================== Consumo por Exames (baixa nos lotes) ==================
def consume_stock_by_batches(items: list):
    """
    Abate saldo do ESTOQUE_FILE por lote específico (lote_id) ou por FIFO de validade.
    items: [{material_id:int, quantidade:float, lote_id:int|None, ...}, ...]
    Levanta ValueError em caso de saldo insuficiente.
    """
    if not items: 
        return

    est = _read_estoque()

    # Índice por id de lote para cada material
    def _by_id(mid: int):
        idx = {}
        for r in est.setdefault(str(mid), []):
            try:
                idx[int(r.get("id"))] = r
            except Exception:
                pass
        return idx

    def _fifo(mid: int):
        rs = [r for r in est.get(str(mid), []) if float(r.get("saldo") or 0.0) > 0.0]
        rs.sort(key=lambda x: (x.get("validade") or "9999-99-99"))
        return rs

    def _dec(row: dict, q: float):
        cur = float(row.get("saldo") or 0.0)
        if cur + 1e-9 < q:
            raise ValueError(f"Saldo insuficiente no lote id={row.get('id')} (saldo={cur} < qtd={q}).")
        row["saldo"] = round(cur - q, 6)

    for it in items:
        if not it or "material_id" not in it:
            continue
        mid = int(it["material_id"])
        qtd = float(it.get("quantidade") or 0.0)
        if qtd <= 0:
            continue

        lote_id = it.get("lote_id")
        if lote_id not in (None, "", "null"):
            lote_id = int(lote_id)
            idx = _by_id(mid)
            if lote_id not in idx:
                raise ValueError(f"Lote id={lote_id} não encontrado para material id={mid}.")
            _dec(idx[lote_id], qtd)
        else:
            restante = qtd
            for row in _fifo(mid):
                if restante <= 0:
                    break
                saldo = float(row.get("saldo") or 0.0)
                if saldo <= 0:
                    continue
                cons = min(saldo, restante)
                _dec(row, cons)
                restante -= cons
            if restante > 1e-9:
                raise ValueError(f"Saldo insuficiente para material id={mid}. Falta {restante}.")

    _write_estoque(est)

# ================== Navbar helper ==================
def build_home_button(href: str = "/", label: str = "Início", button_id: str = "btn_nav_home"):
    try:
        import dash_bootstrap_components as dbc
        from dash import html
    except Exception:
        return None

    return dbc.Button(
        [html.I(className="fa-solid fa-house me-2"), label],
        id=button_id,
        href=href,
        color="primary",
        size="sm",
        className="rounded-pill me-2 shadow-sm",
        style={"fontWeight": 600, "paddingInline": "14px"},
    )
