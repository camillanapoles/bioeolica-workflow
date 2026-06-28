"""
lab_db.dmn — engine de decisão DMN genérico, data-driven.

Lê regras da tabela dmn_rule (criada por lab_db.seed_fsm) e as avalia contra um
dict de entradas. Nenhum nome de domínio, método ou métrica aparece aqui — o engine
só conhece `operator` e compara valores. Cumpre o mandato no-hardcoded: mudar uma
regra de negócio = editar uma linha de DB, nunca reescolher código.

Hit-policy:
  - evaluate()      → FIRST  (primeira regra casante, por `ord`)
  - evaluate_all()  → todas as casantes (p/ relevância, contar keywords)
  - vvv_verdict()   → PASS se ≥1 critério do gate satisfeito; senão FAIL
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class Rule:
    decision_id: str
    ord: int
    scope: Optional[str]
    input_key: str
    operator: str
    input_value: str
    output_key: str
    output_value: str


# ═══════════════════════ predicados genéricos ═══════════════════════
def _match(operator: str, input_value: str, actual) -> bool:
    """Avalia um predicado. `actual` é o valor de entrada fornecido pelo chamador."""
    if actual is None:
        return False
    a = str(actual).lower()
    v = input_value
    if operator == "eq":
        return a == v.lower()
    if operator == "in":
        return a in [x.strip().lower() for x in v.split(",")]
    if operator == "lt":
        try:
            return float(actual) < float(v)
        except (TypeError, ValueError):
            return False
    if operator == "gt":
        try:
            return float(actual) > float(v)
        except (TypeError, ValueError):
            return False
    if operator == "between":
        lo, hi = [x.strip() for x in v.split(",")]
        try:
            return float(lo) <= float(actual) <= float(hi)
        except (TypeError, ValueError):
            return False
    if operator == "keyword_match":
        return v.lower() in a
    raise ValueError(f"operator desconhecido: {operator!r}")


# ═══════════════════════ carregamento ═══════════════════════
def load_rules(conn, decision_id: str, scope: Optional[str] = None) -> list[Rule]:
    """Carrega regras de uma DMN, opcionalmente filtradas por scope (domain_id)."""
    if scope is None:
        rows = conn.execute(
            "SELECT decision_id,ord,scope,input_key,operator,input_value,output_key,output_value "
            "FROM dmn_rule WHERE decision_id=? ORDER BY ord", (decision_id,)
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT decision_id,ord,scope,input_key,operator,input_value,output_key,output_value "
            "FROM dmn_rule WHERE decision_id=? AND scope=? ORDER BY ord",
            (decision_id, scope)
        ).fetchall()
    return [Rule(*r) for r in rows]


# ═══════════════════════ avaliação ═══════════════════════
def evaluate_all(conn, decision_id: str, inputs: dict, scope: Optional[str] = None) -> list[Rule]:
    """Todas as regras casantes (ordenadas por ord)."""
    return [
        r for r in load_rules(conn, decision_id, scope)
        if r.input_key in inputs and _match(r.operator, r.input_value, inputs[r.input_key])
    ]


def evaluate(conn, decision_id: str, inputs: dict, scope: Optional[str] = None) -> Optional[dict]:
    """FIRST-hit: retorna {output_key: output_value, _rule_ord} da primeira casante, ou None."""
    hits = evaluate_all(conn, decision_id, inputs, scope)
    if not hits:
        return None
    r = hits[0]
    return {r.output_key: r.output_value, "_rule_ord": r.ord}


# ═══════════════════════ casuística de alto nível (ainda genérica) ═══════════════════════
def relevance(conn, domain_id: str, context_text: str) -> tuple[int, float]:
    """G1 — relevance_check por domínio.
    Retorna (applicable, score). score = keywords casadas / total do domínio.
    Domínios sem regra (novos, is_seed=0) sem keyword → applicable=0 (caller decide proposal).
    """
    rules = load_rules(conn, "dmn_relevance_check", scope=domain_id)
    if not rules:
        return 0, 0.0
    hits = [r for r in rules if _match(r.operator, r.input_value, context_text)]
    score = len(hits) / len(rules)
    return (1 if hits else 0), score


def select_method(conn, problem: dict) -> Optional[str]:
    """G_método — decision-tree de método numérico. FIRST-hit sobre características do problema."""
    out = evaluate(conn, "dmn_method_selection", problem)
    return out.get("method_id") if out else None


def vvv_verdict(conn, gate: str, metrics: dict) -> tuple[str, Optional[int]]:
    """G2/G3/G4 — VVV triplo (M3).
    PASS se ≥1 critério (regra verdict=PASS) satisfeito para o gate; senão FAIL.
    Retorna (verdict, rule_ord_da_primeira_PASS | None).
    """
    inputs = {"gate": gate, **metrics}
    for r in evaluate_all(conn, "dmn_vvv_acceptance", inputs):
        if r.output_key == "verdict" and r.output_value == "PASS":
            return "PASS", r.ord
    return "FAIL", None
