"""tests/test_lab_db.py — cobertura do SSOT unificado: schema base + seed_fsm (DMN
materializadas como linhas) + crud (API conn-passing) + dmn (engine de decisão).

Pytest-FREE: roda via `python3 -m tests.test_lab_db` (apenas assert + sqlite3 stdlib).
Honra o mandato zero-PyPI: nenhuma dependência externa.

Execução:  python3 -m tests.test_lab_db
"""
from __future__ import annotations

import os
import sqlite3
import sys
import tempfile

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)

_TMP = tempfile.mkdtemp(prefix="labdb_test_")
import lab_db.build as build  # noqa: E402

build.DB_PATH = os.path.join(_TMP, "test.db")
build.main()  # materializa lab.db com JSON1+JSON2 + seed_fsm (tabelas runtime + 3 DMNs)

from lab_db import crud, dmn  # noqa: E402

# Conexão única compartilhada (sequential, pytest-free) — evita "database is locked".
CONN = sqlite3.connect(build.DB_PATH, check_same_thread=False)
CONN.execute("PRAGMA foreign_keys = ON;")


def _ensure_instance(run_id: str):
    """compose_team referenceia workflow_instance via FK — cria stub antes."""
    CONN.execute(
        "INSERT OR REPLACE INTO workflow_instance (run_id,started_at,research_context_json,status) "
        "VALUES (?,?,?,?)",
        (run_id, "2026-01-01T00:00:00Z", "{}", "RUNNING"),
    )
    CONN.commit()


# ──────────── schema base (Q1-Q6 do build) ────────────
def test_seed_domains_count():
    n = CONN.execute("SELECT COUNT(*) FROM domain_catalog WHERE is_seed=1").fetchone()[0]
    assert n == 10, f"esperado 10 domínios seed, obtido {n}"


def test_q1_fluid_methods_present():
    rows = CONN.execute("""
        SELECT cm.method_id FROM domain_catalog d
        JOIN domain_capability dc ON dc.domain_id=d.id
        JOIN capability_method cm ON cm.capability_id=dc.capability_id
        WHERE d.name='Mecanica_dos_Fluidos'""").fetchall()
    methods = {r[0] for r in rows}
    assert {"FVM", "SPH", "FDM"} <= methods, f"faltam métodos de fluido: {methods}"


def test_q6_methods_split_by_source():
    j1 = CONN.execute("SELECT COUNT(*) FROM numerical_method WHERE source='JSON1'").fetchone()[0]
    j2 = CONN.execute("SELECT COUNT(*) FROM numerical_method WHERE source='JSON2'").fetchone()[0]
    assert j1 >= 7 and j2 >= 4


# ──────────── DMN materializado como linhas (zero hardcoded) ────────────
def test_dmn_rules_loaded():
    for did in ("dmn_relevance_check", "dmn_method_selection", "dmn_vvv_acceptance"):
        n = CONN.execute("SELECT COUNT(*) FROM dmn_rule WHERE decision_id=?", (did,)).fetchone()[0]
        assert n > 0, f"DMN {did} sem regras seed"


def test_dmn_select_method_large_deformation():
    m = dmn.select_method(CONN, {"deformation": "large"})
    assert m == "MPM", f"grande deformação → MPM esperado, obtido {m}"


def test_dmn_select_method_small_deformation():
    assert dmn.select_method(CONN, {"deformation": "small"}) == "FEM"


def test_dmn_vvv_pass_and_fail():
    v_pass, _ = dmn.vvv_verdict(CONN, "G2", {"mesh_error": 0.005, "time_residual": 0.003, "conservation_ok": 1})
    v_fail, _ = dmn.vvv_verdict(CONN, "G2", {"mesh_error": 0.5, "time_residual": 0.4})
    assert v_pass == "PASS" and v_fail == "FAIL"


# ──────────── CRUD multi-agente (API conn-passing) ────────────
def test_compose_team_cardinality():
    _ensure_instance("RUN-T1")
    tid = crud.compose_team(CONN, "RUN-T1", ["D01", "D03", "D05"])
    card = CONN.execute("SELECT cardinality FROM team_instance WHERE id=?", (tid,)).fetchone()[0]
    agents = CONN.execute("SELECT COUNT(*) FROM agent_run WHERE team_instance_id=?", (tid,)).fetchone()[0]
    assert card == 3 and agents == 3


def test_set_agent_status():
    _ensure_instance("RUN-T2")
    crud.compose_team(CONN, "RUN-T2", ["D01"])
    aid = CONN.execute("SELECT id FROM agent_run WHERE team_instance_id LIKE 'TI-RUN-T2%' LIMIT 1").fetchone()[0]
    crud.set_agent_status(CONN, aid, "done", result_ref="results/runt2.json")
    st = CONN.execute("SELECT status, result_ref FROM agent_run WHERE id=?", (aid,)).fetchone()
    assert st[0] == "done" and st[1] == "results/runt2.json"


# ──────────── gates + watchdog (thresholds como dados) ────────────
def test_record_and_last_verdict():
    _ensure_instance("RUN-T3")
    crud.record_gate(CONN, "RUN-T3", "G2", "PASS", phase="F4", decided_by="dmn_vvv_acceptance")
    assert crud.last_verdict(CONN, "RUN-T3", "G2") == "PASS"


def test_watchdog_no_trip_when_verdict_recorded():
    _ensure_instance("RUN-T4")
    crud.arm_watchdogs(CONN, "RUN-T4")
    for gate in ("G1", "G2", "G3", "G4", "G5", "G_metodo"):
        crud.record_gate(CONN, "RUN-T4", gate, "PASS", phase="F0")
    tripped = crud.trip_expired(CONN, "RUN-T4")
    assert tripped == [], f"watchdog tripou sem motivo: {tripped}"


def test_watchdog_trips_on_missing_verdict():
    """Deadline vencido + sem verdict → trip + registra TIMEOUT."""
    from datetime import datetime, timezone, timedelta
    _ensure_instance("RUN-T5")
    past = (datetime.now(timezone.utc) - timedelta(seconds=10)).isoformat()
    CONN.execute(
        "INSERT INTO timeout_watchdog (run_id,gate_id,phase_id,armed_at,deadline,tripped) "
        "VALUES ('RUN-T5','G2','F4',?, ?,0)",
        (past, past),
    )
    CONN.commit()
    tripped = crud.trip_expired(CONN, "RUN-T5")
    assert any(t["gate_id"] == "G2" for t in tripped), "G2 deveria ter tripado"
    assert crud.last_verdict(CONN, "RUN-T5", "G2") == "TIMEOUT"


# ──────────── runner pytest-free ────────────
_TESTS = [v for k, v in sorted(globals().items()) if k.startswith("test_")]


def run_all():
    fails = 0
    for t in _TESTS:
        try:
            t()
            print(f"  PASS  {t.__name__}")
        except Exception as e:
            fails += 1
            print(f"  FAIL  {t.__name__}: {type(e).__name__}: {e}")
    print(f"\n{len(_TESTS) - fails}/{len(_TESTS)} passed")
    return fails


if __name__ == "__main__":
    sys.exit(1 if run_all() else 0)
