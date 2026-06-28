"""tests/test_fsm.py — FSM data-driven: invariantes I1-I4, cardinalidade variável,
loop Kaizen, anti-hardcode. Fecha a pendência #1 do doc 04 §7.

Pytest-FREE: roda via `python3 -m tests.test_fsm` (apenas assert + sqlite3 stdlib).
Honra o mandato zero-PyPI.

Execução:  python3 -m tests.test_fsm
"""
from __future__ import annotations

import os
import re
import sqlite3
import sys
import tempfile

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)

_TMP = tempfile.mkdtemp(prefix="fsm_test_")
import lab_db.build as build  # noqa: E402

build.DB_PATH = os.path.join(_TMP, "fsm.db")
build.main()  # lab.db com seed_fsm

from lab_db import fsm  # noqa: E402

# Conexão única compartilhada (sequential, pytest-free) — evita "database is locked".
CONN = sqlite3.connect(build.DB_PATH, check_same_thread=False)
CONN.execute("PRAGMA foreign_keys = ON;")


def _ctx_fluid():
    return dict(
        id="FLUIDA", who="lab-fluidos", what="escoamento em tubulação",
        when="2026", where="duto", why="perda de carga", how="CFD",
        regime="fluid_flow", fluid_free_surface="yes",
    )


def _ctx_structure():
    return dict(
        id="ESTRUTURA", who="lab-estruturas", what="tensão em viga",
        when="2026", where="viga I", why="verificação de fadiga", how="FEM",
        deformation="small",
    )


# ──────────── Pendência #1 — invariantes I1-I4 ────────────
def test_invariants_I1_I4():
    f = fsm.load_fsm(CONN)
    reports = fsm.validate_invariants(f, CONN)
    assert len(reports) >= 4, f"esperado ≥4 relatórios, obtido {len(reports)}"
    assert all("OK" in r or "skip" in r for r in reports), reports


def test_invariant_violation_I1_raises():
    """Injetar fail_target=F1 numa fase ord>=4 deve levantar InvariantViolation (I1)."""
    CONN.execute("UPDATE workflow_phase SET fail_target='F1' WHERE id='F4'")
    CONN.commit()
    f = fsm.load_fsm(CONN)
    try:
        fsm.validate_invariants(f)
        raised = False
    except fsm.InvariantViolation as e:
        raised = "I1" in str(e)
    finally:
        CONN.execute("UPDATE workflow_phase SET fail_target='F4' WHERE id='F4'")
        CONN.commit()
    assert raised, "I1 violado deveria levantar InvariantViolation"


# ──────────── Pendência #2 — cardinalidade DERIVADA (variável por pesquisa) ────────────
def test_variable_cardinality_two_contexts():
    """2 research_context distintos → cardinalidades diferentes (prova 'qq pesquisa')."""
    rid_a = fsm.run(CONN, _ctx_fluid())
    rid_b = fsm.run(CONN, _ctx_structure())
    card_a = CONN.execute("SELECT cardinality FROM workflow_instance WHERE run_id=?", (rid_a,)).fetchone()[0]
    card_b = CONN.execute("SELECT cardinality FROM workflow_instance WHERE run_id=?", (rid_b,)).fetchone()[0]
    assert card_a > 0 and card_b > 0, "ambos devem ter ≥1 domínio aplicável"
    assert card_a != card_b, f"cardinalidades deveriam diferir (genérico); ambas={card_a}"


def test_team_spawned_matches_cardinality():
    """I3: |team agents| == cardinalidade declarada."""
    rid = fsm.run(CONN, _ctx_structure())
    card = CONN.execute("SELECT cardinality FROM workflow_instance WHERE run_id=?", (rid,)).fetchone()[0]
    n_agents = CONN.execute("SELECT COUNT(*) FROM agent_run WHERE run_id=?", (rid,)).fetchone()[0]
    assert n_agents == card, f"|agents|={n_agents} != cardinalidade={card} (I3)"


# ──────────── Loop Kaizen — FAIL→fail_target, nunca reinício total ────────────
def test_kaizen_g2_fail_no_total_restart():
    """G2 FAIL → vai ao fail_target (loop Kaizen), nunca F1/reinício total."""
    rid = fsm.run(CONN, _ctx_structure(),
                  metrics={"mesh_error": 0.5, "time_residual": 0.4},
                  force_fail_gate="G2")
    status = CONN.execute("SELECT status FROM workflow_instance WHERE run_id=?", (rid,)).fetchone()[0]
    gates = [r[0] for r in CONN.execute("SELECT gate FROM gate_verdict WHERE run_id=? ORDER BY id", (rid,))]
    assert status == "FAIL"
    assert "KAIZEN" in gates, f"esperado KAIZEN em {gates}"
    assert gates.count("G0") == 1, f"G0 deveria aparecer 1x (sem reinício total): {gates}"


def test_idempotent_rerun_same_run_id():
    """Re-executar a mesma run (mesmo id) não choca PKs (_purge_run)."""
    rid1 = fsm.run(CONN, _ctx_fluid())
    rid2 = fsm.run(CONN, _ctx_fluid())  # mesmo id (ctx.id="FLUIDA")
    assert rid1 == rid2
    n = CONN.execute("SELECT COUNT(*) FROM workflow_instance WHERE run_id=?", (rid1,)).fetchone()[0]
    assert n == 1, f"re-run deveria ser idempotente; {n} instâncias"


# ──────────── Anti-hardcode (mandato ZERO literais de domínio no ENGINE) ────────────
def test_no_hardcoded_domains_in_engine():
    """O ENGINE (fsm.py/dmn.py, excluindo demo main()) NÃO contém nomes de domínio/método
    como literais de LÓGICA. seed_fsm.py legitimamente os tem — como DADOS (linhas de
    dmn_rule). 'Dxx' pode ser ID de métrica (quality_metric) — não é hardcode de domínio."""
    # nomes de domínio (não IDs Dxx) e métodos como decisões embutidas:
    banned = [r"\bMecanica\b", r"\bMateriais\b", r"\bEnergia\b", r"\bFluido[s]?\b"]
    for mod in ("fsm.py", "dmn.py"):
        path = os.path.join(REPO, "lab_db", mod)
        src = open(path, encoding="utf-8").read()
        # exclui o bloco demo main() (input 5W1H do usuário, não lógica do engine)
        engine = src.split("def main(")[0]
        for pat in banned:
            assert not re.search(pat, engine), f"{mod} engine contém literal de domínio: {pat}"


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
