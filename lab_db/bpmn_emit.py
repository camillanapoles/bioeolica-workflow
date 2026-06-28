"""
lab_db.bpmn_emit — emite BPMN 2.0 + DMN 2.0 XML **gerados do DB** (lab.db).

Ponte SSOT → Camunda 8 / c8run / bpmn.io da arquitetura 4-camadas. Espelha o padrão
data-driven de `lab_db.graph` (projeção do relacional em formato-texto): nenhum ID de
fase/gate/regra é literal aqui — tudo é lido de `workflow_phase` (BPMN) e `dmn_rule` (DMN).
Honra o mandato no-hardcoded.

Fontes:
  - workflow_phase(id, name, ord, gate, gate_type, dmn_source, fail_target, mandate_ref)
  - dmn_rule(decision_id, ord, scope, input_key, operator, input_value, output_key, output_value, note)

Saídas (em lab_db/bpmn_out/): orchestration.bpmn + {decision_id}.dmn por decisão.

Engine: sqlite3 (stdlib) — zero PyPI, roda offline.
"""
from __future__ import annotations

import os
import sqlite3

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "lab.db")
OUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "bpmn_out")

# gate_type (dado em workflow_phase) → tipo de elemento BPMN 2.0.
# Mapeamento data-driven: a chave é um valor de coluna, não um literal de lógica de domínio.
_GATE_KIND = {
    "XOR": "exclusiveGateway",
    "completeness": "exclusiveGateway",
    "DMN": "businessRuleTask",
}
_DEFAULT_KIND = "exclusiveGateway"


def _esc(s: str) -> str:
    """Escapa caracteres XML em atributo/texto."""
    return (s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;") \
        .replace('"', "&quot;").replace("'", "&apos;")


def _num_or_str(v: str) -> str:
    """FEEL: número bare se numérico, senão string entre aspas."""
    v = (v or "").strip()
    try:
        f = float(v)
        if f == int(f):
            return str(int(f))
        return str(f)
    except ValueError:
        return f'"{v}"'


def _feel_entry(operator: str, value: str) -> str:
    """Codifica o operator do dmn_rule como expressão FEEL (DMN input entry)."""
    op = (operator or "").strip()
    if op == "lt":
        return f"<{_num_or_str(value)}"
    if op == "gt":
        return f">{_num_or_str(value)}"
    if op == "between":
        parts = [p.strip() for p in (value or "").split(",")]
        if len(parts) == 2:
            return f"[{_num_or_str(parts[0])}..{_num_or_str(parts[1])}]"
        return _num_or_str(value)
    if op == "in":
        return ",".join(_num_or_str(p.strip()) for p in (value or "").split(",") if p.strip())
    # eq | keyword_match → literal (keyword_match: semântica de contenção documentada via note)
    return _num_or_str(value)


# ═══════════════════════ BPMN 2.0 ═══════════════════════
def load_phases(conn):
    """Linhas de workflow_phase ordenadas por ord (backbone do processo)."""
    rows = conn.execute(
        "SELECT id, name, ord, gate, gate_type, dmn_source, fail_target "
        "FROM workflow_phase ORDER BY ord"
    ).fetchall()
    return [
        {"id": r[0], "name": r[1], "ord": r[2], "gate": r[3],
         "gate_type": r[4], "dmn_source": r[5], "fail_target": r[6]}
        for r in rows
    ]


def emit_bpmn(conn) -> str:
    """Gera o XML BPMN 2.0 do processo a partir das linhas de workflow_phase.

    Topologia (tudo derivado, nada hardcode):
      startEvent S → F1 → ...(task por fase)...→ F7 → endEvent E
      cada fase com `gate` emite um nó gateway (XOR/completeness→exclusiveGateway,
      DMN→businessRuleTask); ramos PASS→próxima fase, FAIL→fail_target (loop Kaizen).
    """
    phases = load_phases(conn)
    n = len(phases)
    elements, flows = [], []
    flow_id = [0]

    def flow(src, tgt, name=None):
        flow_id[0] += 1
        flows.append((f"flow{flow_id[0]}", src, tgt, name))

    # nós
    elements.append('<bpmn:startEvent id="S" name="Enunciado / Produto recebido"/>')
    for p in phases:
        elements.append(f'<bpmn:task id="{_esc(p["id"])}" name="{_esc(p["name"])}"/>')
        g = p["gate"]
        if g:
            kind = _GATE_KIND.get(p["gate_type"], _DEFAULT_KIND)
            gname = g if not p["dmn_source"] else f"{g} · {_esc(p['dmn_source'])}"
            attrs = f'id="{_esc(g)}" name="{_esc(gname)}"'
            if kind == "businessRuleTask" and p["dmn_source"]:
                attrs += f' camunda:decisionRef="{_esc(p["dmn_source"])}"'
            elements.append(f"<bpmn:{kind} {attrs}/>")
    elements.append('<bpmn:endEvent id="E" name="Entrega validada + rastreavel"/>')

    # fluxos
    for i, p in enumerate(phases):
        nxt = phases[i + 1]["id"] if i + 1 < n else "E"
        if i == 0:
            flow("S", p["id"])
        g = p["gate"]
        if g:
            flow(p["id"], g)
            flow(g, nxt, "PASS")
            if p["fail_target"]:
                flow(g, p["fail_target"], "FAIL")
        else:
            flow(p["id"], nxt)

    sf = "\n    ".join(
        f'<bpmn:sequenceFlow id="{fid}" sourceRef="{_esc(s)}" targetRef="{_esc(t)}"'
        + (f' name="{_esc(name)}"/>' if name else "/>")
        for fid, s, t, name in flows
    )
    body = "\n    ".join(elements)

    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<bpmn:definitions xmlns:bpmn="http://www.omg.org/spec/BPMN/20100524/MODEL"\n'
        '                  xmlns:camunda="http://camunda.org/schema/1.0/bpmn"\n'
        '                  targetNamespace="http://bioeolica/workflow">\n'
        f'  <bpmn:process id="Process_Omnibus_v3" isExecutable="false">\n'
        f"    {body}\n"
        f"    {sf}\n"
        f"  </bpmn:process>\n"
        f"</bpmn:definitions>\n"
    )


# ═══════════════════════ DMN 2.0 ═══════════════════════
def load_rules(conn, decision_id: str):
    """Linhas de dmn_rule de uma decisão, ordenadas por ord."""
    rows = conn.execute(
        "SELECT ord, input_key, operator, input_value, output_key, output_value, note "
        "FROM dmn_rule WHERE decision_id=? ORDER BY ord",
        (decision_id,),
    ).fetchall()
    return [
        {"ord": r[0], "input_key": r[1], "operator": r[2], "input_value": r[3],
         "output_key": r[4], "output_value": r[5], "note": r[6]}
        for r in rows
    ]


def emit_dmn(conn, decision_id: str) -> str:
    """Gera o XML DMN 2.0 (decisionTable hitPolicy FIRST) a partir de dmn_rule.

    Inputs = distintos input_key da decisão; outputs = distintos output_key.
    Cada linha → <dmn:rule> com inputEntry (FEEL) por input e outputEntry por output.
    """
    rules = load_rules(conn, decision_id)
    if not rules:
        return ""

    input_keys = []
    for r in rules:
        if r["input_key"] not in input_keys:
            input_keys.append(r["input_key"])
    output_keys = []
    for r in rules:
        if r["output_key"] not in output_keys:
            output_keys.append(r["output_key"])

    def in_entry(r, key):
        if r["input_key"] != key:
            return ""
        return _feel_entry(r["operator"], r["input_value"])

    def out_entry(r, key):
        return _num_or_str(r["output_value"]) if r["output_key"] == key else ""

    inputs = "\n        ".join(
        f'<dmn:input id="in_{i}" label="{_esc(k)}">'
        f'<dmn:inputExpression id="inExpr_{i}" typeRef="string">'
        f'<dmn:text>{_esc(k)}</dmn:text></dmn:inputExpression></dmn:input>'
        for i, k in enumerate(input_keys)
    )
    outputs = "\n        ".join(
        f'<dmn:output id="out_{i}" label="{_esc(k)}" typeRef="string"/>'
        for i, k in enumerate(output_keys)
    )

    rule_xml = []
    for idx, r in enumerate(rules):
        ins = "\n          ".join(
            f'<dmn:inputEntry id="ie_{idx}_{i}"><dmn:text>{_esc(in_entry(r, k))}</dmn:text></dmn:inputEntry>'
            for i, k in enumerate(input_keys)
        )
        outs = "\n          ".join(
            f'<dmn:outputEntry id="oe_{idx}_{i}"><dmn:text>{_esc(out_entry(r, k))}</dmn:text></dmn:outputEntry>'
            for i, k in enumerate(output_keys)
        )
        desc = f'<dmn:description>{_esc(r["note"])}</dmn:description>' if r["note"] else ""
        rule_xml.append(
            f'        <dmn:rule id="rule_{idx}">{desc}\n'
            f"          {ins}\n          {outs}\n        </dmn:rule>"
        )
    rules_block = "\n".join(rule_xml)

    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<dmn:definitions xmlns:dmn="http://www.omg.org/spec/DMN/20180521/MODEL"\n'
        '                  targetNamespace="http://bioeolica/workflow">\n'
        f'  <dmn:decision id="{_esc(decision_id)}" name="{_esc(decision_id)}">\n'
        f'    <dmn:decisionTable id="{_esc(decision_id)}_table" hitPolicy="FIRST">\n'
        f"        {inputs}\n        {outputs}\n"
        f"{rules_block}\n"
        f"    </dmn:decisionTable>\n"
        f"  </dmn:decision>\n"
        f"</dmn:definitions>\n"
    )


def list_decisions(conn) -> list[str]:
    """decision_ids distintos presentes em dmn_rule (fonte única de decisões)."""
    return [r[0] for r in conn.execute(
        "SELECT DISTINCT decision_id FROM dmn_rule ORDER BY decision_id").fetchall()]


def main():
    # auto-build se lab.db não existe (mesmo padrão de tests/test_fsm.py)
    if not os.path.exists(DB_PATH):
        import lab_db.build as build
        build.DB_PATH = DB_PATH
        build.main()

    os.makedirs(OUT_DIR, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)

    bpmn = emit_bpmn(conn)
    with open(os.path.join(OUT_DIR, "orchestration.bpmn"), "w", encoding="utf-8") as f:
        f.write(bpmn)
    n_tasks = bpmn.count("<bpmn:task ")
    n_gw_xor = bpmn.count("<bpmn:exclusiveGateway ")
    n_brt = bpmn.count("<bpmn:businessRuleTask ")
    n_fail = bpmn.count('name="FAIL"')
    print(f"BPMN: orchestration.bpmn — {n_tasks} tasks, {n_gw_xor} exclusiveGateways, "
          f"{n_brt} businessRuleTasks, {n_fail} fluxos FAIL (Kaizen)")

    decisions = list_decisions(conn)
    for did in decisions:
        dmn = emit_dmn(conn, did)
        with open(os.path.join(OUT_DIR, f"{did}.dmn"), "w", encoding="utf-8") as f:
            f.write(dmn)
        n_rules = dmn.count("<dmn:rule ")
        print(f"DMN:  {did}.dmn — {n_rules} regras, hitPolicy=FIRST")

    conn.close()
    print(f"Saídas: {OUT_DIR}/{{orchestration.bpmn, *.dmn}}")


if __name__ == "__main__":
    main()
