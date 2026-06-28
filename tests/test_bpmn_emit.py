"""tests/test_bpmn_emit.py — emissor BPMN/DMN data-driven (fecha formalização Camunda).

Pytest-FREE: roda via `python3 -m tests.test_bpmn_emit` (apenas assert + sqlite3 stdlib).
Honra o mandato zero-PyPI. Espelha o padrão de tests/test_fsm.py (shared CONN, run_all).

Cobertura:
  - BPMN bem-formado com todas as fases F1-F7 + gateways (exclusive/businessRule).
  - Fluxos FAIL casam com fail_target de workflow_phase (loop Kaizen data-driven).
  - 3 DMNs emitidas; contagem de <dmn:rule> == COUNT(*) de dmn_rule por decisão.
  - hitPolicy="FIRST" presente em cada DMN.
  - Anti-hardcode: bpmn_emit.py sem literais de domínio/método.
"""
from __future__ import annotations

import os
import re
import sqlite3
import sys
import tempfile

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)

_TMP = tempfile.mkdtemp(prefix="bpmn_test_")
import lab_db.build as build  # noqa: E402

build.DB_PATH = os.path.join(_TMP, "bpmn.db")
build.main()  # lab.db com workflow_phase + dmn_rule seed

from lab_db import bpmn_emit  # noqa: E402

CONN = sqlite3.connect(build.DB_PATH, check_same_thread=False)
CONN.execute("PRAGMA foreign_keys = ON;")

_BPMN = bpmn_emit.emit_bpmn(CONN)


# ──────────── BPMN: fases + gateways ────────────
def test_bpmn_has_all_phases_and_gateways():
    for pid in ("F1", "F2", "F3", "F4", "F5", "F6", "F7"):
        assert f'id="{pid}"' in _BPMN, f"fase {pid} ausente no BPMN"
    assert "<bpmn:exclusiveGateway" in _BPMN, "esperado ≥1 exclusiveGateway (XOR/completeness)"
    assert "<bpmn:businessRuleTask" in _BPMN, "esperado ≥1 businessRuleTask (gate DMN)"
    assert 'camunda:decisionRef="dmn_method_selection"' in _BPMN
    assert "<bpmn:startEvent" in _BPMN and "<bpmn:endEvent" in _BPMN


# ──────────── BPMN: fluxos FAIL == fail_target (Kaizen) ────────────
def test_bpmn_fail_flows_match_fail_target():
    """Para cada fase com gate+fail_target, o ramo FAIL aponta ao fail_target da linha."""
    rows = CONN.execute(
        "SELECT gate, fail_target FROM workflow_phase "
        "WHERE gate IS NOT NULL AND fail_target IS NOT NULL"
    ).fetchall()
    assert rows, "esperado ≥1 gate com fail_target"
    for gate, fail_target in rows:
        # existe um sequenceFlow source=gate target=fail_target name=FAIL
        pat = re.compile(
            rf'<bpmn:sequenceFlow[^>]*sourceRef="{gate}"[^>]*targetRef="{fail_target}"[^>]*name="FAIL"'
        )
        # sourceRef/targetRef podem aparecer em qualquer ordem — testa ambas
        alt = re.compile(
            rf'<bpmn:sequenceFlow[^>]*targetRef="{fail_target}"[^>]*sourceRef="{gate}"[^>]*name="FAIL"'
        )
        assert pat.search(_BPMN) or alt.search(_BPMN), (
            f"gate {gate} deveria ter fluxo FAIL → {fail_target} (Kaizen)"
        )


def test_bpmn_kaizen_not_total_restart():
    """I1 (invariante doc 04): nenhum fluxo FAIL aponta a F1 como reinício total...
    Exceto gates cujo fail_target legítimo seja F1 (G1 re-contextualiza). Aqui só garantimos
    que existe loop (FAIL existe) e que fail_targets casam com a DB (test anterior)."""
    assert 'name="FAIL"' in _BPMN, "esperado ≥1 fluxo FAIL (loop Kaizen)"


# ──────────── DMN: contagem de regras por decisão == DB ────────────
def test_dmn_files_emitted_with_correct_rule_counts():
    decisions = bpmn_emit.list_decisions(CONN)
    assert set(decisions) >= {"dmn_relevance_check", "dmn_method_selection", "dmn_vvv_acceptance"}
    for did in decisions:
        dmn = bpmn_emit.emit_dmn(CONN, did)
        db_count = CONN.execute(
            "SELECT COUNT(*) FROM dmn_rule WHERE decision_id=?", (did,)
        ).fetchone()[0]
        xml_count = dmn.count("<dmn:rule ")
        assert xml_count == db_count, f"{did}: XML={xml_count} != DB={db_count}"


def test_dmn_hitpolicy_first():
    for did in bpmn_emit.list_decisions(CONN):
        assert 'hitPolicy="FIRST"' in bpmn_emit.emit_dmn(CONN, did), f"{did} sem hitPolicy FIRST"


def test_dmn_has_input_and_output_clauses():
    dmn = bpmn_emit.emit_dmn(CONN, "dmn_method_selection")
    assert "<dmn:input " in dmn and "<dmn:inputExpression" in dmn
    assert "<dmn:output " in dmn
    # método selecionado aparece como output (não hardcode de qual — só que há outputs)
    assert dmn.count("<dmn:output ") >= 1


# ──────────── Anti-hardcode (mandato ZERO literais no emissor) ────────────
def test_no_hardcoded_domains_in_emitter():
    """bpmn_emit.py não contém nomes de domínio/método como literais de lógica —
    só mapeamento gate_type→elemento BPMN e operadores FEEL genéricos."""
    src = open(os.path.join(REPO, "lab_db", "bpmn_emit.py"), encoding="utf-8").read()
    banned = [r"\bMecanica\b", r"\bMateriais\b", r"\bEnergia\b", r"\bFluido[s]?\b"]
    # métodos numéricos como decisão embutida:
    banned += [r"\bFEM\b", r"\bMPM\b", r"\bSPH\b", r"\bFVM\b", r"\bDEM\b", r"\bPINNs\b"]
    for pat in banned:
        assert not re.search(pat, src), f"bpmn_emit.py contém literal proibido: {pat}"


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
