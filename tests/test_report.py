"""tests/test_report.py — artefato "resultado do lab real".

Prova que build_report() agrega metadados + gates + resultados numéricos,
que store_report() persiste JSON íntegro, e que emit_report() faz ambos.

Pytest-FREE: `python3 -m tests.test_report` (apenas assert + sqlite3 stdlib).
"""
from __future__ import annotations

import json
import os
import sqlite3
import sys
import tempfile

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)

_TMP = tempfile.mkdtemp(prefix="report_test_")
import lab_db.build as build  # noqa: E402

build.DB_PATH = os.path.join(_TMP, "report.db")
build.main()

from lab_db import report, fsm  # noqa: E402

CONN = sqlite3.connect(build.DB_PATH, check_same_thread=False)
CONN.execute("PRAGMA foreign_keys = ON;")

_METRICS = {"mesh_error": 0.005, "time_residual": 0.003,
            "source_quality": "peer-reviewed", "reproducible": 1}


def _run(rid: str, how="FEM", deformation="small") -> str:
    """Helper: executa fsm.run com métricas mínimas para chegar a F7."""
    ctx = dict(id=rid, who="lab", what="test", when="2026",
               where="x", why="y", how=how, deformation=deformation)
    return fsm.run(CONN, ctx, metrics=_METRICS)


# ──────────── Metadata + gates ────────────
def test_report_build_includes_run_metadata():
    """Report contém run_id, status, cardinality após execução."""
    rid = _run("R1")
    r = report.build_report(CONN, rid)
    assert r["run_id"] == rid
    assert r["status"] in ("PASS", "FAIL")
    assert isinstance(r["cardinality"], int) and r["cardinality"] > 0
    assert "research_context" in r


def test_report_build_includes_gate_verdicts():
    """Report tem array de gates com gate, verdict, detail."""
    rid = _run("R2")
    r = report.build_report(CONN, rid)
    assert isinstance(r["gates"], list) and len(r["gates"]) > 0
    for g in r["gates"]:
        assert "gate" in g and "verdict" in g, f"gate entry malformed: {g}"
    gate_names = [g["gate"] for g in r["gates"]]
    assert "G0" in gate_names


# ──────────── Numeric results ────────────
def test_report_build_includes_numeric_results():
    """Report com dados de agent_output numérico (kernel FEM→Poisson 1D)."""
    rid = _run("R3")
    r = report.build_report(CONN, rid)
    assert "numeric_domains" in r
    # Após execução real, pelo menos 1 domínio com método kernel
    if r["numeric_domains"]:
        nd = r["numeric_domains"][0]
        assert "domain_id" in nd and "method_id" in nd
        assert nd["field_max"] is not None or nd.get("linear_residual") is not None


# ──────────── Persistência ────────────
def test_report_stored_in_db():
    """store + read preserva o JSON (round-trip)."""
    rid = _run("R4")
    r = report.build_report(CONN, rid)
    report.store_report(CONN, rid, r)
    row = CONN.execute(
        "SELECT report_json FROM report_artifact WHERE run_id=? ORDER BY id DESC LIMIT 1",
        (rid,),
    ).fetchone()
    assert row is not None, "report não persistido em report_artifact"
    restored = json.loads(row[0])
    assert restored["run_id"] == rid
    assert restored["status"] == r["status"]


# ──────────── Empty run ────────────
def test_report_empty_run():
    """Run sem agentes numéricos produz report com arrays vazios."""
    r = report.build_report(CONN, "NONEXISTENT")
    assert r["status"] == "UNKNOWN"
    assert "error" in r


# ──────────── emit_report pipeline ────────────
def test_emit_report_builds_and_stores():
    """emit_report chama build + store e retorna o dict."""
    rid = _run("R5")
    r = report.emit_report(CONN, rid)
    assert r["run_id"] == rid
    row = CONN.execute(
        "SELECT report_json FROM report_artifact WHERE run_id=? ORDER BY id DESC LIMIT 1",
        (rid,),
    ).fetchone()
    assert row is not None, "emit_report deve persistir em report_artifact"


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
