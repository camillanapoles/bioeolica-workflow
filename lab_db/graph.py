"""
lab_db.graph — deriva um knowledge graph DATA-DRIVEN do DB integrado (lab.db).

Sem hardcoded: todos os nós/arestas são lidos de lab.db via SQL. Honra o mandato
no-hardcoded — o grafo É a projeção relacional.

Nós (tipados): agent, domain, capability, method, tool, rule, step, layer,
ctx_method, output, source, mandate, phase, metric.
Arestas:
  - domain -> capability  (domain_capability)
  - capability -> method  (capability_method)
  - method -> tool        (method_tool)
  - phase -> phase        (transição F1..F7, anotada com gate)
  - metric -> gate        (valida)
  - mandate -> phase      (mandate_ref)
  - phase -> fail_target  (loop kaizen)

Saídas (em lab_db/graph_out/): graph.json, graph.mmd (Mermaid), graph.dot (Graphviz).
"""
from __future__ import annotations

import json
import os
import sqlite3

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "lab.db")
OUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "graph_out")


def load_nodes(conn):
    """Cada linha relevante vira um nó (id global único <tipo>:<id>)."""
    specs = [
        ("agent",       "SELECT id, version AS label FROM kdi_agent"),
        ("domain",      "SELECT id, name AS label FROM domain_catalog"),
        ("capability",  "SELECT id, name AS label FROM capability"),
        ("method",      "SELECT id, id AS label, source FROM numerical_method"),
        ("tool",        "SELECT id, name AS label, license FROM tool"),
        ("rule",        "SELECT id, rule AS label FROM socratic_rule"),
        ("step",        "SELECT id, name AS label FROM response_step"),
        ("layer",       "SELECT id, name AS label FROM context_layer"),
        ("ctx_method",  "SELECT id, name AS label FROM context_method"),
        ("output",      "SELECT id, name AS label FROM output_standard"),
        ("source",      "SELECT id, name AS label FROM knowledge_source"),
        ("mandate",     "SELECT id, name AS label FROM mandate"),
        ("phase",       "SELECT id, name AS label, ord FROM workflow_phase"),
        ("metric",      "SELECT id, name AS label, target FROM quality_metric"),
    ]
    nodes = []
    for ntype, sql in specs:
        cols = [d[0] for d in conn.execute(sql).description]
        for row in conn.execute(sql):
            rec = dict(zip(cols, row))
            nid = f"{ntype}:{rec['id']}"
            attrs = {k: v for k, v in rec.items() if k not in ("id",)}
            nodes.append({"id": nid, "type": ntype, "label": rec["id"], "attrs": attrs})
    return nodes


def load_edges(conn):
    edges = []

    def add(s, t, rel, **props):
        e = {"source": s, "target": t, "rel": rel}
        e.update({k: v for k, v in props.items() if v is not None})
        edges.append(e)

    # cadeia de domínio -> capability -> method -> tool
    for d, c in conn.execute("SELECT domain_id, capability_id FROM domain_capability"):
        add(f"domain:{d}", f"capability:{c}", "has_capability")
    for c, m in conn.execute("SELECT capability_id, method_id FROM capability_method"):
        add(f"capability:{c}", f"method:{m}", "solved_by")
    for m, t in conn.execute("SELECT method_id, tool_id FROM method_tool"):
        add(f"method:{m}", f"tool:{t}", "runs_on")

    # workflow: transições sequenciais F1->F2->...->F7, anotadas com gate de origem
    phases = conn.execute("SELECT id, ord, gate, gate_type, dmn_source, fail_target, mandate_ref "
                          "FROM workflow_phase ORDER BY ord").fetchall()
    prev = None
    gate_prev = None
    for pid, ord_, gate, gtype, dmn, fail, mand in phases:
        if prev is not None:
            add(f"phase:{prev}", f"phase:{pid}", "transitions", gate=gate_prev)
        gate_prev = gate
        prev = pid
        # loops kaizen (fail_target)
        if fail and fail != pid:
            add(f"phase:{pid}", f"phase:{fail}", "fail_loop", reason="kaizen_retry")
        # mandate que rege a fase
        if mand:
            add(f"mandate:{mand}", f"phase:{pid}", "governs")

    # métricas validam gates/fases
    for mid, target, gate in conn.execute("SELECT id, target, gate FROM quality_metric"):
        if gate:
            tgt = gate if gate.startswith("F") else None  # gates G* não são nós
            if tgt:
                add(f"metric:{mid}", f"phase:{tgt}", "validates", target=target)
            else:
                add(f"metric:{mid}", gate, "validates_gate", target=target)

    return edges


def to_mermaid(nodes, edges):
    styles = {
        "agent": ("[", "]"), "domain": ("((", "))"), "capability": ("((", "))"),
        "method": ("[", "]"), "tool": ("{{", "}}"), "mandate": ("[[", "]]"),
        "phase": ("[", "]"), "metric": ("[/", "/]"),
    }
    lines = ["graph LR"]
    for n in nodes:
        if n["type"] not in styles:
            continue
        lb, rb = styles[n["type"]]
        safe = n["id"].replace(":", "_")
        lines.append(f'  {safe}{lb}"{n["label"]}"{rb}')
    for e in edges:
        s = e["source"].replace(":", "_")
        t = e["target"].replace(":", "_")
        if s.startswith("metric_") or t.startswith("G"):
            continue  # métricas/gates literais omitidos p/ clareza
        rel = e["rel"]
        label = {"has_capability": "", "solved_by": "", "runs_on": "",
                 "transitions": "|gate|", "fail_loop": "|FAIL↺|",
                 "governs": "|rege|"}.get(rel, f"|{rel}|")
        lines.append(f"  {s} -- {label} {t}")
    return "\n".join(lines) + "\n"


def to_dot(nodes, edges):
    shapes = {"agent": "box", "domain": "ellipse", "capability": "ellipse",
              "method": "box", "tool": "hexagon", "mandate": "note",
              "phase": "box", "metric": "note"}
    lines = ["digraph lab {", '  rankdir=LR;', '  node [fontname="Helvetica"];']
    for n in nodes:
        if n["type"] not in shapes:
            continue
        safe = n["id"].replace(":", "_")
        lines.append(f'  {safe} [shape={shapes[n["type"]]}, label="{n["label"]}"];')
    for e in edges:
        s = e["source"].replace(":", "_")
        t = e["target"].replace(":", "_")
        if s.startswith("metric_") or t.startswith("G"):
            continue
        lines.append(f'  {s} -> {t} [label="{e["rel"]}"];')
    lines.append("}")
    return "\n".join(lines) + "\n"


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    nodes = load_nodes(conn)
    edges = load_edges(conn)
    conn.close()

    g = {"nodes": nodes, "edges": edges, "meta": {"engine": "sqlite3", "db": DB_PATH}}
    with open(os.path.join(OUT_DIR, "graph.json"), "w", encoding="utf-8") as f:
        json.dump(g, f, ensure_ascii=False, indent=2)
    with open(os.path.join(OUT_DIR, "graph.mmd"), "w", encoding="utf-8") as f:
        f.write(to_mermaid(nodes, edges))
    with open(os.path.join(OUT_DIR, "graph.dot"), "w", encoding="utf-8") as f:
        f.write(to_dot(nodes, edges))

    by_type = {}
    for n in nodes:
        by_type[n["type"]] = by_type.get(n["type"], 0) + 1
    print(f"Grafo: {len(nodes)} nós, {len(edges)} arestas")
    for t, c in sorted(by_type.items()):
        print(f"  {t:<12} {c}")
    print(f"Saídas: {OUT_DIR}/{{graph.json, graph.mmd, graph.dot}}")


if __name__ == "__main__":
    main()
