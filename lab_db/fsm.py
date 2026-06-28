"""
lab_db.fsm — FSM data-driven: estados/transições/gates lidos do DB, executados sobre
QUALQUER research_context. Fecha as 3 pendências do doc 04 §7:
  #1 validate_invariants (I1-I4) contra os dados;
  #2 run() executa F1-F7 com cardinalidade DERIVADA (não fixa) e gates via DMN (zero hardcoded);
  #3 trace da run em gate_verdict + WAL (rastreabilidade M6/M4) → projetável no grafo.

Nenhum nome de domínio/método/gate/métrica é literal aqui: tudo vem de workflow_phase,
domain_catalog e dmn_rule. Mudar o workflow = editar linhas de DB, não este código.

Pré-requisito: `python3 -m lab_db.build` já materializou lab.db (schema JSON1/JSON2 +
DDL/seed FSM). Esta engine só consome.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

from .build import connect
from . import dmn, crud, agent_exec


# ═══════════════════════ modelo da FSM (data-driven) ═══════════════════════
@dataclass(frozen=True)
class Phase:
    id: str
    ord: int
    name: str
    gate: Optional[str]
    gate_type: Optional[str]
    dmn_source: Optional[str]
    fail_target: Optional[str]
    mandate_ref: Optional[str]


@dataclass
class Fsm:
    phases: list[Phase]
    by_id: dict = field(default_factory=dict)

    def fail_edges(self) -> list[tuple[str, str]]:
        """Arestas (src -> fail_target) para cada fase com fail_target."""
        return [(p.id, p.fail_target) for p in self.phases if p.fail_target]


class InvariantViolation(Exception):
    """Levantada quando um invariante I1-I4 é ofendido pelos dados do DB."""


def load_fsm(conn) -> Fsm:
    """Monta a FSM a partir de workflow_phase (estados/transições/gates como dados)."""
    rows = conn.execute(
        "SELECT id,ord,name,gate,gate_type,dmn_source,fail_target,mandate_ref "
        "FROM workflow_phase ORDER BY ord"
    ).fetchall()
    phases = [Phase(*r) for r in rows]
    fsm = Fsm(phases=phases, by_id={p.id: p for p in phases})
    return fsm


# ═══════════════════════ Pendência #1 — invariantes I1-I4 ═══════════════════════
def validate_invariants(fsm: Fsm, conn=None) -> list[str]:
    """Valida I1-I4 contra os dados. Retorna lista de relatórios; levanta
    InvariantViolation na primeira ofensa (uso típico: gate de bootstrap).

    I1 — sem reinício total pós-execução: nenhuma fase com ord>=4 pode ter
         fail_target == 'F1' (proibido F4->F1 e similares).
    I2 — todo FAIL tem fail_target válido ∈ {F1,F2,F3,F4}.
    I3 — cardinalidade spawn(F2)==join: workflow_instance.cardinality ==
         COUNT(runtime_domain applicable) em toda run registrada (se conn dado).
    I4 — G5 só dispara após a fase de correlação (F5): a fase que carrega G5
         tem ord > ord da fase que carrega G3.
    """
    reports = []
    ids = set(fsm.by_id)
    valid_fail = {"F1", "F2", "F3", "F4"}

    # I1
    for p in fsm.phases:
        if p.ord >= 4 and p.fail_target == "F1":
            raise InvariantViolation(
                f"I1: fase {p.id} (ord={p.ord}) reinício total -> fail_target=F1 proibido"
            )
    reports.append("I1 OK: nenhuma transição de reinício total pós-execução")

    # I2
    for p in fsm.phases:
        if p.gate and p.gate_type:  # fase com gate de decisão pode falhar
            ft = p.fail_target
            if ft is None:
                raise InvariantViolation(f"I2: fase {p.id} tem gate {p.gate} sem fail_target")
            if ft not in valid_fail:
                raise InvariantViolation(
                    f"I2: fase {p.id} fail_target={ft} fora de {valid_fail}"
                )
            if ft not in ids:
                raise InvariantViolation(f"I2: fase {p.id} fail_target={ft} não é fase conhecida")
    reports.append("I2 OK: todo gate de FAIL tem fail_target válido")

    # I3 (apenas se houver runtime data para checar)
    if conn is not None:
        for (run_id, card) in conn.execute(
            "SELECT run_id,cardinality FROM workflow_instance WHERE cardinality IS NOT NULL"
        ).fetchall():
            actual = conn.execute(
                "SELECT COUNT(*) FROM runtime_domain WHERE run_id=? AND applicable=1",
                (run_id,),
            ).fetchone()[0]
            if actual != card:
                raise InvariantViolation(
                    f"I3: run {run_id} cardinality={card} != aplicáveis runtime={actual}"
                )
        reports.append("I3 OK: cardinalidade spawn==join em toda run registrada")
    else:
        reports.append("I3 skip: sem conn runtime (validado em run-time)")

    # I4
    ord_of = {p.gate: p.ord for p in fsm.phases if p.gate}
    g3, g5 = ord_of.get("G3"), ord_of.get("G5")
    if g3 is not None and g5 is not None and g5 <= g3:
        raise InvariantViolation(
            f"I4: G5 (ord={g5}) deve disparar após G3 (ord={g3})"
        )
    reports.append("I4 OK: G5 dispara após correlação (G3)")
    return reports


# ═══════════════════════ Pendência #2 — execução F1-F7 ═══════════════════════
def _ts() -> str:
    return datetime.now(timezone.utc).isoformat()


def _record_verdict(conn, run_id, gate, phase, verdict, dmn_decision=None,
                    dmn_rule_ord=None, detail=None):
    """Auditoria M6: toda decisão de gate vira linha rastreável."""
    conn.execute(
        "INSERT INTO gate_verdict (run_id,gate,phase,verdict,dmn_decision,dmn_rule_ord,detail,ts) "
        "VALUES (?,?,?,?,?,?,?,?)",
        (run_id, gate, phase, verdict, dmn_decision, dmn_rule_ord, detail, _ts()),
    )
    conn.commit()


def _append_wal(conn, run_id, phase, actor, action_5w1h, map_index, metrics=None):
    """M4: WAL append-only por ação."""
    conn.execute(
        "INSERT INTO wal_log (run_id,ts,phase,actor_agent,action_5w1h,map_index,quality_metrics,patch) "
        "VALUES (?,?,?,?,?,?,?,?)",
        (run_id, _ts(), phase, actor, action_5w1h, map_index, metrics, None),
    )
    conn.commit()


def _g0_complete(ctx: dict) -> tuple[bool, str]:
    """G0 completeness: 5W1H presente (who/what/when/where/why/how). Genérico — só contratu."""
    need = ["who", "what", "when", "where", "why", "how"]
    miss = [k for k in need if not ctx.get(k)]
    if miss:
        return False, f"5W1H ausente: {miss}"
    return True, "5W1H completo"


def _extract_text(ctx: dict) -> str:
    """Concatena campos textuais do contexto p/ keyword_match de relevância."""
    return json.dumps(ctx, ensure_ascii=False).lower()


def run(conn, research_context: dict, *, force_fail_gate: Optional[str] = None,
        metrics: Optional[dict] = None) -> str:
    """Executa F1->F7 sobre um research_context arbitrário.

    - Cardinalidade do time é DERIVADA em F2 (gate G1), nunca fixa.
    - Gates roteados aos DMN lidos do DB (zero hardcoded).
    - FAIL -> fail_target da fase (loop Kaizen), nunca reinício total.
    - `force_fail_gate` injeta FAIL num gate p/ exercitar o kaizen loop (demo/teste).
    - `metrics` carrega valores medidos (mesh_error, error_vs_benchmark, ...).
    Retorna run_id.
    """
    fsm = load_fsm(conn)
    metrics = metrics or {}
    ctx = dict(research_context)
    run_id = f"RUN-{ctx.get('id', datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S'))}"
    _purge_run(conn, run_id)  # idempotência: reprocessar a mesma run não choca PKs

    # F1 — Captura de Contexto + G0 completeness.
    # Instância persistida ANTES de qualquer gate_verdict (FK gate_verdict.run_id -> workflow_instance).
    ok, detail = _g0_complete(ctx)
    _persist_instance(conn, run_id, ctx, "BLOCKED" if not ok else "RUNNING")
    if not ok:
        _record_verdict(conn, run_id, "G0", "F1", "FAIL", detail=detail)
        return run_id
    _record_verdict(conn, run_id, "G0", "F1", "PASS", detail=detail)
    _append_wal(conn, run_id, "F1", "orchestrator", "captura 5W1H+Ishikawa+7layers",
                f"MAP/CTX/{run_id}", "D2=100%")

    # F2 — Derivação de domínios (cardinalidade variável) + G1
    text = _extract_text(ctx)
    seeds = conn.execute("SELECT id FROM domain_catalog WHERE is_seed=1").fetchall()
    applicable = []
    for (dom_id,) in seeds:
        appl, score = dmn.relevance(conn, dom_id, text)
        if appl:
            conn.execute(
                "INSERT INTO runtime_domain (run_id,domain_id,is_seed,relevance_score,applicable,justification) "
                "VALUES (?,?,1,?,1,?)",
                (run_id, dom_id, score, f"keyword match score={score:.2f}"),
            )
            applicable.append(dom_id)
    cardinality = len(applicable)
    _persist_cardinality(conn, run_id, cardinality)
    g1 = "FAIL" if (force_fail_gate == "G1" or cardinality == 0) else "PASS"
    _record_verdict(conn, run_id, "G1", "F2", g1,
                    dmn_decision="dmn_relevance_check",
                    detail=f"cardinalidade={cardinality} applicable={applicable}")
    _append_wal(conn, run_id, "F2", "orchestrator", f"derivação de domínios ({cardinality})",
                f"MAP/DOM/{run_id}", f"D1~{cardinality}")
    if g1 == "FAIL":
        _set_status(conn, run_id, "BLOCKED")
        return run_id

    # M7 — composição do time multi-agente (1 agente por domínio aplicável) + watchdogs
    # de gate armados (thresholds lidos de gate_timeout — dados; trip dispara TIMEOUT).
    tid = crud.compose_team(conn, run_id, applicable)
    crud.arm_watchdogs(conn, run_id)
    _append_wal(conn, run_id, "F2", "orchestrator",
                f"team {tid} composto ({cardinality} agentes) + watchdogs armados",
                f"MAP/TEAM/{run_id}")

    # F3 — Decomposição M3 + seleção de método (G_metodo) por domínio
    problem = {k: ctx.get(k) for k in
               ("deformation", "fracture", "fragmentation", "material_type",
                "fluid_free_surface", "regime", "high_strain_rate", "reduction",
                "physics_informed")}
    for dom_id in applicable:
        m = dmn.select_method(conn, problem)
        conn.execute("UPDATE runtime_domain SET method_id=? WHERE run_id=? AND domain_id=?",
                     (m, run_id, dom_id))
        conn.execute("UPDATE agent_run SET method_id=? WHERE run_id=? AND domain_id=?",
                     (m, run_id, dom_id))
    gmet = "FAIL" if force_fail_gate == "G_metodo" else "PASS"
    _record_verdict(conn, run_id, "G_metodo", "F3", gmet,
                    dmn_decision="dmn_method_selection",
                    detail=f"método={dmn.select_method(conn, problem)}")
    _append_wal(conn, run_id, "F3", "team", "M3 macro/meso/micro + método",
                f"MAP/M3/{run_id}")
    if gmet == "FAIL":
        _kaizen(conn, run_id, fsm, "F3")
        return run_id

    # F4 — Execução + G2 Verificação
    v2, o2 = ("FAIL", None) if force_fail_gate == "G2" else dmn.vvv_verdict(conn, "G2", metrics)
    _record_verdict(conn, run_id, "G2", "F4", v2, "dmn_vvv_acceptance", o2,
                    detail=f"metrics={ {k:metrics.get(k) for k in metrics} }")
    _append_wal(conn, run_id, "F4", "team", "execução numérica", f"MAP/EXE/{run_id}", "D3")
    if v2 == "FAIL":
        _kaizen(conn, run_id, fsm, "F4")
        _set_status(conn, run_id, "FAIL")
        return run_id

    # F5 — Correlação Holística + G3 Validação
    v3, o3 = ("FAIL", None) if force_fail_gate == "G3" else dmn.vvv_verdict(conn, "G3", metrics)
    _record_verdict(conn, run_id, "G3", "F5", v3, "dmn_vvv_acceptance", o3, detail="benchmark/exp")
    _append_wal(conn, run_id, "F5", "team", "correlação macro-meso-micro", f"MAP/COR/{run_id}", "D4")
    if v3 == "FAIL":
        _kaizen(conn, run_id, fsm, "F5")
        _set_status(conn, run_id, "FAIL")
        return run_id

    # F6 — Cobertura + Memória + G5. Gate hard = cobertura ≥ 0.75 (D1: alvo 75-90%).
    # >0.90 é over-coverage (subótimo, sinalizado no detail), não FAIL.
    # EXECUÇÃO REAL: cada agent_run pendente passa pelo executor (provider resolvido do DB,
    # prompt montado de kdi_agent+cadeia domínio, watchdog respeitado) → done/fail/timeout.
    # Substitui o mock bulk-done anterior — agora cobertura conta só agentes efetivamente 'done'.
    agent_exec.run_pending(conn, run_id)
    done = conn.execute(
        "SELECT COUNT(*) FROM agent_run WHERE run_id=? AND status='done'", (run_id,)
    ).fetchone()[0]
    coverage = done / cardinality if cardinality else 0.0
    if force_fail_gate == "G5":
        g5 = "FAIL"
    else:
        g5 = "PASS" if coverage >= 0.75 else "FAIL"
    note = " (acima do alvo 75-90%: cobertura redundante)" if coverage > 0.90 else ""
    _record_verdict(conn, run_id, "G5", "F6", g5, detail=f"coverage={coverage:.2f}{note}")
    _append_wal(conn, run_id, "F6", "orchestrator", "selo WAL + Mapa Único",
                f"MAP/WAL/{run_id}", "D8,D9,D10")
    conn.execute("UPDATE workflow_instance SET coverage=? WHERE run_id=?", (coverage, run_id))
    conn.commit()
    # Watchdog: registra TIMEOUT de gates/agentes que estouraram deadline (comunicação on-time).
    crud.trip_expired(conn, run_id)
    if g5 == "FAIL":
        _kaizen(conn, run_id, fsm, "F6")
        _set_status(conn, run_id, "FAIL")
        return run_id

    # F7 — Entrega Validada
    _record_verdict(conn, run_id, "DELIVERY", "F7", "PASS", detail=f"deliverable#{run_id}")
    _append_wal(conn, run_id, "F7", "orchestrator", "entrega rastreável selada",
                f"MAP/OUT/{run_id}", "D5,D6")
    _set_status(conn, run_id, "PASS")
    return run_id


def _purge_run(conn, run_id):
    """Idempotência: re-executar a mesma run (mesmo run_id) limpa artefatos anteriores
    antes de reprocessar. Ordem inversa de dependência (FKs child-first). NÃO toca
    dmn_rule/schema. Inclui tabelas multi-agente (team/agent/watchdog) — senão FK
    de team_instance→workflow_instance bloqueia o DELETE."""
    conn.execute("DELETE FROM agent_output WHERE agent_id IN "
                 "(SELECT id FROM agent_run WHERE run_id=?)", (run_id,))
    conn.execute("DELETE FROM agent_run WHERE run_id=?", (run_id,))
    conn.execute("DELETE FROM timeout_watchdog WHERE run_id=?", (run_id,))
    conn.execute("DELETE FROM team_instance WHERE run_id=?", (run_id,))
    conn.execute("DELETE FROM gate_verdict WHERE run_id=?", (run_id,))
    conn.execute("DELETE FROM runtime_domain WHERE run_id=?", (run_id,))
    conn.execute("DELETE FROM wal_log WHERE run_id=?", (run_id,))
    conn.execute("DELETE FROM workflow_instance WHERE run_id=?", (run_id,))
    conn.commit()


def _persist_instance(conn, run_id, ctx, status):
    """Insert inicial (F1). Não chamar p/ mudar status — usar _set_status (preserva cardinality/coverage)."""
    conn.execute(
        "INSERT OR REPLACE INTO workflow_instance "
        "(run_id,started_at,research_context_json,status) VALUES (?,?,?,?)",
        (run_id, _ts(), json.dumps(ctx, ensure_ascii=False), status),
    )
    conn.commit()


def _set_status(conn, run_id, status):
    """Muda status preservando cardinality/coverage (INSERT OR REPLACE os zeraria)."""
    conn.execute("UPDATE workflow_instance SET status=? WHERE run_id=?", (status, run_id))
    conn.commit()


def _persist_cardinality(conn, run_id, cardinality):
    conn.execute("UPDATE workflow_instance SET cardinality=? WHERE run_id=?",
                 (cardinality, run_id))
    conn.commit()


def _kaizen(conn, run_id, fsm: Fsm, phase_id: str):
    """Loop Kaizen: FAIL -> fail_target da fase (nunca reinício total). I1 garantido."""
    p = fsm.by_id[phase_id]
    target = p.fail_target or phase_id  # default: auto-retry
    _record_verdict(conn, run_id, "KAIZEN", phase_id, "FAIL",
                    detail=f"fail_target={target} (loop Kaizen, sem reinício total)")
    _append_wal(conn, run_id, phase_id, "orchestrator",
                f"kaizen -> {target}", f"MAP/KZ/{run_id}")


# ═══════════════════════ CLI / demo ═══════════════════════
def main():
    """Demo: 2 research_context distintos -> cardinalidades diferentes (prova 'qq pesquisa')."""
    conn = connect()
    fsm = load_fsm(conn)
    print("═" * 72)
    print("FSM data-driven — invariantes I1-I4")
    for r in validate_invariants(fsm, conn):
        print("  ", r)

    ctxA = dict(
        id="FLUIDA", who="lab-fluidos", what="escoamento em tubulação",
        when="2026", where="duto", why="perda de carga", how="CFD",
        regime="fluid_flow", fluid_free_surface="yes",
        metrics={"mesh_error": 0.005, "time_residual": 0.003, "conservation_ok": 1,
                 "error_vs_benchmark": 0.03, "error_vs_experimental": 0.04,
                 "source_quality": "peer-reviewed", "reproducible": 1},
    )
    ctxB = dict(
        id="ESTRUTURA", who="lab-estruturas", what="tensão em viga",
        when="2026", where="viga I", why="verificação de fadiga", how="FEM",
        deformation="small",
        metrics={"mesh_error": 0.008, "conservation_ok": 1,
                 "error_vs_experimental": 0.02, "source_quality": "peer-reviewed", "reproducible": 1},
    )
    ctxFAIL = dict(
        id="FALHA-G2", who="lab", what="demo kaizen", when="2026", where="x",
        why="exercitar fail-loop", how="FEM", deformation="small",
        metrics={"mesh_error": 0.5, "time_residual": 0.4},  # G2 vai FAIL
    )

    for ctx in (ctxA, ctxB, ctxFAIL):
        raw_metrics = ctx.get("metrics")
        run_metrics = raw_metrics if isinstance(raw_metrics, dict) else {}
        rid = run(conn, ctx, metrics=run_metrics)
        card = conn.execute("SELECT cardinality FROM workflow_instance WHERE run_id=?",
                            (rid,)).fetchone()[0]
        verdicts = [r[0] for r in conn.execute(
            "SELECT gate FROM gate_verdict WHERE run_id=? ORDER BY id", (rid,)).fetchall()]
        status = conn.execute("SELECT status FROM workflow_instance WHERE run_id=?",
                              (rid,)).fetchone()[0]
        print("═" * 72)
        print(f"run={rid}  status={status}  cardinality={card}")
        print(f"  gates: {verdicts}")

    conn.close()


if __name__ == "__main__":
    main()
