"""
lab_db.crud — API de integração data-driven sobre o SSOT lab.db (schema unificado em
lab_db.seed_fsm). Camada fina: SQL parametrizado; verdicts/scores/status são lidos de
dmn_rule (via lab_db.dmn) e thresholds de gate_timeout. ZERO hardcode de regras de domínio.

Funções recebem `conn` (não abrem a própria conexão) para serem chamadas dentro da
transação de lab_db.fsm.run — coesão total, uma só fonte, sem _connect paralelo.
"""
from __future__ import annotations

from datetime import datetime, timezone


def _ts() -> str:
    return datetime.now(timezone.utc).isoformat()


# ───────────────────────── TIME / AGENT (M7) ─────────────────────────
def compose_team(conn, run_id: str, domains: list[str]) -> str:
    """Cria team_instance + agent_run por domínio aplicável; linka runtime_domain.
    Cardinalidade = len(domains) (variável por pesquisa). Retorna team_instance_id."""
    tid = f"TI-{run_id}"
    conn.execute(
        "INSERT OR REPLACE INTO team_instance (id,run_id,cardinality,status,created_at) "
        "VALUES (?,?,?,?,?)",
        (tid, run_id, len(domains), "active", _ts()),
    )
    for dom_id in domains:
        ar = f"AR-{run_id}-{dom_id}"
        conn.execute(
            "INSERT OR REPLACE INTO agent_run (id,team_instance_id,run_id,domain_id,status,started_at) "
            "VALUES (?,?,?,?,?,?)",
            (ar, tid, run_id, dom_id, "pending", _ts()),
        )
        # linka domínio runtime ao time + agente
        conn.execute(
            "UPDATE runtime_domain SET team_instance_id=?, agent_run_id=? "
            "WHERE run_id=? AND domain_id=?",
            (tid, ar, run_id, dom_id),
        )
    conn.commit()
    return tid


def set_agent_status(conn, agent_id: str, status: str, result_ref: str | None = None,
                     method_id: str | None = None):
    """Atualiza estado do agente especialista (pending|running|done|fail|timeout)."""
    if method_id:
        conn.execute(
            "UPDATE agent_run SET status=?, finished_at=?, result_ref=?, method_id=? WHERE id=?",
            (status, _ts(), result_ref, method_id, agent_id))
    else:
        conn.execute(
            "UPDATE agent_run SET status=?, finished_at=?, result_ref=? WHERE id=?",
            (status, _ts(), result_ref, agent_id))
    conn.commit()


# ───────────────────────── GATES (auditoria M6) ─────────────────────────
def record_gate(conn, run_id: str, gate: str, verdict: str, phase: str | None = None,
                decided_by: str = "orchestrator", dmn_decision: str | None = None,
                dmn_rule_ord: int | None = None, detail: str | None = None):
    """Insere veredito de gate em gate_verdict (toda decisão é rastreável a regra/fonte)."""
    conn.execute(
        "INSERT INTO gate_verdict (run_id,gate,phase,verdict,dmn_decision,dmn_rule_ord,decided_by,detail,ts) "
        "VALUES (?,?,?,?,?,?,?,?,?)",
        (run_id, gate, phase, verdict, dmn_decision, dmn_rule_ord, decided_by, detail, _ts()),
    )
    conn.commit()


def last_verdict(conn, run_id: str, gate: str) -> str | None:
    row = conn.execute(
        "SELECT verdict FROM gate_verdict WHERE run_id=? AND gate=? ORDER BY id DESC LIMIT 1",
        (run_id, gate),
    ).fetchone()
    return row[0] if row else None


# ───────────────────────── WATCHDOG (timeout de gate/agent) ─────────────────────────
def arm_watchdogs(conn, run_id: str, gates=None) -> list[tuple]:
    """Delega a seed_fsm.arm_watchdogs (thresholds lidos de gate_timeout — dados)."""
    from .seed_fsm import arm_watchdogs as _arm
    return _arm(conn, run_id, gates)


def trip_expired(conn, run_id: str) -> list[dict]:
    """Varre watchdogs da run cujo deadline passou sem verdict → tripa + registra TIMEOUT.
    Retorna gates tripados p/ escalonamento (o 'agente que não respondeu no tempo')."""
    now = _ts()
    tripped = []
    rows = conn.execute(
        "SELECT id,gate_id,phase_id,deadline FROM timeout_watchdog "
        "WHERE run_id=? AND tripped=0 AND deadline<?",
        (run_id, now),
    ).fetchall()
    for wid, gate_id, phase_id, deadline in rows:
        if last_verdict(conn, run_id, gate_id) in ("PASS", "FAIL"):
            continue  # gate já decidiu — não trip
        conn.execute(
            "UPDATE timeout_watchdog SET tripped=1, trip_reason='no_verdict_before_deadline' WHERE id=?",
            (wid,),
        )
        record_gate(conn, run_id, gate_id, "TIMEOUT", phase_id,
                    decided_by="watchdog", detail=f"deadline={deadline}")
        tripped.append({"gate_id": gate_id, "phase_id": phase_id, "deadline": deadline})
    conn.commit()
    return tripped
