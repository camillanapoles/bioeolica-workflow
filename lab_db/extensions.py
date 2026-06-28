"""
lab_db.extensions — [DEPRECIADO] shim de compatibilidade.

HISTÓRICO: este módulo continha DDL multi-agente paralelo (runtime_domain com
schema id/name, dmn_decision, gate_event) que vivia fora do SSOT. Esse schema foi
RECONCILIADO em `lab_db.seed_fsm` (tabelas runtime unificadas: runtime_domain,
team_instance, agent_run, gate_verdict, timeout_watchdog, gate_timeout, dmn_rule) e
a API de integração vive em `lab_db.crud`.

Este arquivo agora é um shim fino que apenas re-exporta a API unificada, para não
quebrar importadores legais. Nenhum DDL é emitido daqui — única fonte = seed_fsm.

Usar no lugar:
    python3 -m lab_db.build     # materializa lab.db (inclui seed_fsm)
    python3 -m lab_db.fsm       # executa F1-F7 (usa crud internamente)
"""
from __future__ import annotations

import warnings

warnings.warn(
    "lab_db.extensions está depreciado; use lab_db.seed_fsm (DDL/seed) e "
    "lab_db.crud (API de integração). Nenhum DDL paralelo é emitido.",
    DeprecationWarning,
    stacklevel=2,
)

# Re-exporta a API unificada p/ importadores legados (sem lógica própria).
from .seed_fsm import init_fsm_schema, seed_dmns, arm_watchdogs, trip_expired  # noqa: E402,F401
from . import crud  # noqa: E402,F401


def main() -> None:
    print("lab_db.extensions está DEPRECIADO.")
    print("  DDL/seed multi-agente + DMN: lab_db.seed_fsm (chamado por lab_db.build)")
    print("  API de integração (team/agent/gate/watchdog): lab_db.crud")
    print("  Orquestração F1-F7: lab_db.fsm")
    print("Nenhuma ação realizada — única fonte = seed_fsm.")


if __name__ == "__main__":
    main()
