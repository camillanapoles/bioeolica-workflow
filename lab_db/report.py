"""
lab_db.report — agregador de resultados do workflow (artefato "resultado do lab real").

Produz um dict JSON-serializável consolidando run metadata + gate verdicts +
resultados numéricos por domínio. Consumido pelo F7 (Entrega Validada) e
exportável para geração de paper/relatório.

Mandato no-hardcoded honrado: todas as queries são sobre dados do DB, sem
literais de domínio/método/gate. Mandato SSOT: o report é uma projeção do
lab.db (não duplica dados).
"""
from __future__ import annotations

import json
from datetime import datetime, timezone


def _ts() -> str:
    return datetime.now(timezone.utc).isoformat()


def build_report(conn, run_id: str) -> dict:
    """Agrega dados da run num dict estruturado.

    Consulta workflow_instance + gate_verdict + agent_output (modo numérico)
    + runtime_domain. Retorna dict com run_id, status, gates[], domains[], ...
    """
    inst = conn.execute(
        "SELECT run_id,status,cardinality,coverage,research_context_json "
        "FROM workflow_instance WHERE run_id=?", (run_id,)
    ).fetchone()
    if not inst:
        return {"run_id": run_id, "status": "UNKNOWN", "error": "run not found"}

    run_id, status, cardinality, coverage, ctx_json = inst

    # Gates
    gates = [
        {"gate": r[0], "verdict": r[1], "detail": r[2]}
        for r in conn.execute(
            "SELECT gate,verdict,detail FROM gate_verdict WHERE run_id=? ORDER BY id",
            (run_id,),
        ).fetchall()
    ]

    # Domínios aplicáveis com método selecionado
    domains = [
        {"domain_id": r[0], "method_id": r[1], "justification": r[2]}
        for r in conn.execute(
            "SELECT domain_id,method_id,justification FROM runtime_domain "
            "WHERE run_id=? AND applicable=1 ORDER BY domain_id",
            (run_id,),
        ).fetchall()
    ]

    # Resultados numéricos por domínio (agent_output mode=real-numeric)
    numeric_rows = conn.execute(
        "SELECT a.domain_id, a.method_id, o.payload "
        "FROM agent_output o "
        "JOIN agent_run a ON a.id=o.agent_id "
        "WHERE a.run_id=? AND o.payload LIKE '%real-numeric%'",
        (run_id,),
    ).fetchall()

    numeric_domains = []
    for domain_id, method_id, payload_str in numeric_rows:
        try:
            payload = json.loads(payload_str)
            result = payload.get("result", {})
        except (json.JSONDecodeError, TypeError):
            result = {}
        # Projeta TODOS os campos do result dinamicamente — sem hardcode de nomes.
        # Campos escalares (int/float/str) vão direto; listas/dicts são omitidos.
        entry: dict = {"domain_id": domain_id, "method_id": method_id}
        for key, val in result.items():
            if isinstance(val, (int, float, str, bool)) and val is not None:
                entry[key] = val
        numeric_domains.append(entry)

    return {
        "run_id": run_id,
        "status": status,
        "cardinality": cardinality,
        "coverage": coverage,
        "research_context": ctx_json,
        "gates": gates,
        "domains": domains,
        "numeric_domains": numeric_domains,
        "ts": _ts(),
    }


def store_report(conn, run_id: str, report: dict):
    """Persiste o report em report_artifact (SSOT append-only)."""
    conn.execute(
        "INSERT INTO report_artifact (run_id,report_json,created_at) VALUES (?,?,?)",
        (run_id, json.dumps(report, ensure_ascii=False), _ts()),
    )
    conn.commit()


def emit_report(conn, run_id: str) -> dict:
    """build + store + return. Chamado pelo F7 da FSM."""
    report = build_report(conn, run_id)
    store_report(conn, run_id, report)
    return report
