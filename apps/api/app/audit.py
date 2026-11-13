"""Log de auditoria: quem fez o quê. Só administradores leem (`GET /audit`).

Registra logins (certos e errados), mudanças de usuários e de acesso, criação/exclusão/movimentação de conteúdo e
acessos negados. NÃO registra cada salvamento automático de relatório/dashboard (ruído) nem leituras/consultas.
O registro nunca derruba a operação principal: falha ao gravar é ignorada.
"""
import json
import logging
from contextlib import closing
from datetime import datetime, timezone

from . import auth, db

# Eventos de negócio também vão para o log do processo (uma linha JSON por evento, pronta para `docker logs | jq`),
# além da tabela `audit`. O logger tem handler próprio: não depende da configuração de logging do uvicorn.
events_log = logging.getLogger("metastatistic.events")
if not events_log.handlers:
    _handler = logging.StreamHandler()
    _handler.setFormatter(logging.Formatter("%(message)s"))
    events_log.addHandler(_handler)
    events_log.setLevel(logging.INFO)
    events_log.propagate = False

# Ações que contam como evento de negócio (o restante, como acessos negados e logins, segue só na tabela de auditoria)
BUSINESS_ACTIONS = {"register", "setup", "create", "delete", "move", "share", "login", "denied"}


def log(user: "auth.User | None", action: str, kind: str | None = None, target: str | None = None, detail: str | None = None,
        *, username: str | None = None) -> None:
    anonymous = user is None or user.id == auth.ANONYMOUS_ADMIN.id
    try:
        with closing(db.connect()) as con, con:
            con.execute(
                "INSERT INTO audit (ts, user_id, username, action, kind, target, detail) VALUES (?,?,?,?,?,?,?)",
                [datetime.now(timezone.utc).isoformat(), None if anonymous else user.id,
                 username or (None if user is None else user.username), action, kind, target, (detail or None) and detail[:300]],
            )
    except Exception:  # auditoria é best-effort
        pass
    if action in BUSINESS_ACTIONS:
        events_log.info(json.dumps({
            "event": f"{kind or 'session'}.{action}", "ts": datetime.now(timezone.utc).isoformat(),
            "user": None if anonymous else user.username, "target": target, "detail": (detail or None) and detail[:200],
        }, ensure_ascii=False))


def list_events(limit: int = 100, before_id: int | None = None, action: str | None = None) -> list[dict]:
    limit = min(max(limit, 1), 500)
    clauses, args = [], []
    if before_id is not None:
        clauses.append("id < ?"); args.append(before_id)
    if action:
        clauses.append("action = ?"); args.append(action)
    where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
    with closing(db.connect()) as con:
        rows = con.execute(f"SELECT * FROM audit {where} ORDER BY id DESC LIMIT ?", [*args, limit]).fetchall()
    return [dict(r) for r in rows]
