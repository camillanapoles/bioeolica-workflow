"""tests/test_numeric_exec.py — ponte de execução numérica REAL.

Prova que o engine agora COMPUTA (não só fala sobre): method_id com kernel mapeado
(method_kernel — DADO) → solver stdlib de verdade → agent_output com números reais
verificáveis contra solução analítica. E que method_id sem kernel cai no fallback
provider (stub/http), preservando o caminho anterior.

Pytest-FREE: `python3 -m tests.test_numeric_exec` (apenas assert + sqlite3 stdlib).
"""
from __future__ import annotations

import json
import os
import re
import sqlite3
import sys
import tempfile
from datetime import datetime, timezone

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)

_TMP = tempfile.mkdtemp(prefix="numeric_test_")
import lab_db.build as build  # noqa: E402

build.DB_PATH = os.path.join(_TMP, "numeric.db")
build.main()

from lab_db import numeric_exec, agent_exec, crud  # noqa: E402

CONN = sqlite3.connect(build.DB_PATH, check_same_thread=False)
CONN.execute("PRAGMA foreign_keys = ON;")


def _seed_agent(run_id: str, domain: str, method_id: str | None) -> dict:
    """Cria workflow_instance + team + 1 agent_run com method_id setado. Retorna o agent dict."""
    CONN.execute(
        "INSERT INTO workflow_instance (run_id,started_at,research_context_json,status) "
        "VALUES (?,?,?,?)",
        (run_id, datetime.now(timezone.utc).isoformat(), "{}", "RUNNING"),
    )
    CONN.commit()
    crud.compose_team(CONN, run_id, [domain])
    if method_id is not None:
        CONN.execute("UPDATE agent_run SET method_id=? WHERE run_id=?", (method_id, run_id))
        CONN.commit()
    return agent_exec.pending_agents(CONN, run_id)[0]


# ──────────── Poisson 1D produz números reais, analytic-checkable ────────────
def test_fdm_poisson_produces_real_numbers():
    out = numeric_exec.run_numeric(CONN, {"run_id": "R", "domain_id": "D07", "method_id": "FEM"})
    assert out is not None, "FEM deve ter kernel mapeado"
    assert out["equation"] == "poisson_1d"
    assert out["linear_residual"] < 1e-9, f"solver linear não convergiu: {out['linear_residual']}"
    # analítico: u_max = 1/(9√3) ≈ 0.06415 ; erro da discretização O(h²) com n=60
    assert out["analytic_max"] is not None
    assert abs(out["field_max"] - out["analytic_max"]) < 1e-3, (
        f"field_max={out['field_max']} longe do analítico {out['analytic_max']}"
    )
    assert out["field_min"] >= -1e-9, "u(0)=u(1)=0 → mínimo não-negativo esperado"
    assert len(out["grid_x"]) == len(out["grid_u"]) and len(out["grid_x"]) >= 5


# ──────────── Advecção 1D upwind produz campo numérico real ────────────
def test_fdm_advection_produces_real_numbers():
    out = numeric_exec.run_numeric(CONN, {"run_id": "R", "domain_id": "D05", "method_id": "FVM"})
    assert out is not None and out["equation"] == "advection_1d"
    # IC seno deslocado ∈ [0,2]; após advecção linear o campo permanece ∈ [0,2] aprox.
    assert 0.0 <= out["field_min"] and out["field_max"] <= 2.0 + 1e-6
    assert out["mass_drift"] >= 0.0          # drift de massa (conservação) reportado
    assert out["n"] > 0 and out["steps"] > 0


# ──────────── kernel resolvido do DB (method_kernel — zero hardcode) ────────────
def test_kernel_resolved_from_db():
    kind, params = numeric_exec.resolve_kernel(CONN, "FEM")
    assert kind == "fdm_poisson"
    assert params["source"] == "x" and params["n"] == 60
    # method_id sem linha → None (fallback ao provider)
    assert numeric_exec.resolve_kernel(CONN, "ROM") is None
    assert numeric_exec.resolve_kernel(CONN, None) is None


# ──────────── run_one escreve output NUMÉRICO quando kernel mapeado ────────────
def test_run_one_writes_numeric_output():
    rid = "RUN-NUM-1"
    agent = _seed_agent(rid, "D07", "FEM")
    status = agent_exec.run_one(CONN, agent)
    assert status == "done"
    row = CONN.execute(
        "SELECT payload,result_ref FROM agent_output o "
        "JOIN agent_run a ON a.id=o.agent_id WHERE a.run_id=?", (rid,)
    ).fetchone()
    assert row and "real-numeric" in row[0], f"payload não é numérico: {row}"
    payload = json.loads(row[0])
    assert "result" in payload and "field_max" in payload["result"]
    assert row[1].endswith("/NUMERIC"), f"result_ref deve marcar NUMERIC: {row[1]}"


# ──────────── fallback ao provider quando method_id sem kernel ────────────
def test_fallback_to_provider_when_no_kernel():
    rid = "RUN-NUM-2"
    # ROM não tem method_kernel → cai no provider stub (is_default=1)
    agent = _seed_agent(rid, "D04", "ROM")
    status = agent_exec.run_one(CONN, agent)
    assert status == "done"
    row = CONN.execute(
        "SELECT payload FROM agent_output o "
        "JOIN agent_run a ON a.id=o.agent_id WHERE a.run_id=?", (rid,)
    ).fetchone()
    assert row and "offline-stub" in row[0], f"esperado fallback stub; obtido {row}"


# ──────────── anti-hardcode: kinds só no registry _KERNELS; sem nomes de método ────────────
def test_no_hardcoded_methods_or_kernel_kinds():
    path = os.path.join(REPO, "lab_db", "numeric_exec.py")
    src = open(path, encoding="utf-8").read()
    # kernel kinds ("fdm_poisson"/"fdm_advection") só na linha do registry _KERNELS
    registry_line = [ln for ln in src.splitlines() if "_KERNELS" in ln and "{" in ln]
    assert registry_line, "registry _KERNELS ausente"
    for kind_lit in ("fdm_poisson", "fdm_advection"):
        total = src.count(f'"{kind_lit}"')
        in_registry = registry_line[0].count(f'"{kind_lit}"')
        assert total == in_registry, (
            f"'{kind_lit}' aparece {total}x mas só {in_registry}x no registry — kernel kind "
            "não pode ser literal de branch"
        )
    # nomes de método (FEM/FVM/...) não podem aparecer como literais de lógica no engine
    engine = src.split("def run_numeric")[0]
    for pat in (r"\bFEM\b", r"\bFVM\b", r"\bDEM\b", r"\bMPM\b"):
        assert not re.search(pat, engine), f"numeric_exec contém literal de método: {pat}"


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
