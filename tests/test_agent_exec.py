"""tests/test_agent_exec.py — camada de execução por agentes LLM.

Cobre: drenagem pending→done via stub, resolução de provider do DB (is_default),
path de watchdog TIMEOUT, path de FAIL quando provider retorna None, anti-hardcode
(literais de domínio/kind só no registro _PROVIDERS), e prova que fsm.run agora
EXECUTA agentes (agent_output populado) em vez de mockar bulk-done.

Pytest-FREE: `python3 -m tests.test_agent_exec` (apenas assert + sqlite3 stdlib).
"""
from __future__ import annotations

import os
import re
import sqlite3
import sys
import tempfile
from datetime import datetime, timezone, timedelta

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)

_TMP = tempfile.mkdtemp(prefix="agentexec_test_")
import lab_db.build as build  # noqa: E402

build.DB_PATH = os.path.join(_TMP, "agentexec.db")
build.main()

from lab_db import agent_exec, crud, fsm  # noqa: E402

CONN = sqlite3.connect(build.DB_PATH, check_same_thread=False)
CONN.execute("PRAGMA foreign_keys = ON;")


def _seed_run(run_id: str, domains: list[str]) -> str:
    """Cria workflow_instance + team + agent_run pending (não executa fsm.run)."""
    CONN.execute(
        "INSERT INTO workflow_instance (run_id,started_at,research_context_json,status) "
        "VALUES (?,?,?,?)",
        (run_id, datetime.now(timezone.utc).isoformat(), "{}", "RUNNING"),
    )
    CONN.commit()
    crud.compose_team(CONN, run_id, domains)
    return run_id


# ──────────── E2: drenagem pending → done (stub default) ────────────
def test_run_pending_stubs_all_to_done():
    rid = _seed_run("RUN-EXEC-1", ["D01", "D05"])
    # propaga method_id (como fsm.F3 faria) p/ build_prompt ter método
    CONN.execute("UPDATE agent_run SET method_id='FEM' WHERE run_id=?", (rid,))
    CONN.commit()
    n = agent_exec.run_pending(CONN, rid)
    pending = CONN.execute("SELECT COUNT(*) FROM agent_run WHERE run_id=? AND status='pending'",
                           (rid,)).fetchone()[0]
    done = CONN.execute("SELECT COUNT(*) FROM agent_run WHERE run_id=? AND status='done'",
                        (rid,)).fetchone()[0]
    outs = CONN.execute(
        "SELECT COUNT(*) FROM agent_output WHERE agent_id IN "
        "(SELECT id FROM agent_run WHERE run_id=?)", (rid,)
    ).fetchone()[0]
    rows = CONN.execute("SELECT finished_at,result_ref FROM agent_run WHERE run_id=?", (rid,)).fetchall()
    assert n == 2 and pending == 0 and done == 2, f"n={n} pending={pending} done={done}"
    assert outs == 2, f"esperado 1 agent_output/agente; obtido {outs}"
    assert all(r[0] and r[1] for r in rows), f"finished_at/result_ref não setados: {rows}"


# ──────────── provider resolvido do DB (is_default=1) — zero hardcode de kind ────────────
def test_provider_resolved_from_db_default():
    rid = _seed_run("RUN-EXEC-2", ["D03"])
    agent = agent_exec.pending_agents(CONN, rid)[0]
    assert agent["provider_id"] is None, "agente novo deve ter provider_id NULL (cai no default)"
    kind, cfg = agent_exec.resolve_provider(CONN, agent)
    default_row = CONN.execute("SELECT id FROM agent_provider WHERE is_default=1").fetchone()
    assert cfg["id"] == default_row[0], "resolve_provider deve pegar a linha is_default=1"
    assert kind == "stub", f"seed default deveria ser stub; obtido {kind}"


# ──────────── watchdog TIMEOUT: deadline expirado → status=timeout + gate_verdict ────────────
def test_watchdog_timeout_path():
    rid = _seed_run("RUN-EXEC-3", ["D07"])
    agent = agent_exec.pending_agents(CONN, rid)[0]
    # arma watchdog com deadline no PASSADO (simula 'agente não respondeu no tempo')
    past = (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat()
    CONN.execute(
        "INSERT INTO timeout_watchdog (run_id,gate_id,phase_id,armed_at,deadline,tripped) "
        "VALUES (?,?,?,?,?,0)",
        (rid, "G5", "F6", past, past),
    )
    CONN.commit()
    status = agent_exec.run_one(CONN, agent)
    ar = CONN.execute("SELECT status FROM agent_run WHERE id=?", (agent["id"],)).fetchone()
    gv = CONN.execute(
        "SELECT verdict,decided_by FROM gate_verdict WHERE run_id=? AND gate='G5'", (rid,)
    ).fetchone()
    assert status == "timeout", f"esperado timeout; obtido {status}"
    assert ar[0] == "timeout"
    assert gv and gv[0] == "TIMEOUT" and gv[1] == "watchdog", f"gate_verdict incorreto: {gv}"


# ──────────── FAIL path: provider http sem base_url → retorna None → status=fail ────────────
def test_fail_path_when_provider_returns_none():
    # provider http com base_url vazia → _http_provider retorna None imediatamente (sem rede)
    CONN.execute(
        "INSERT INTO agent_provider (id,kind,model,base_url,api_key_env,timeout_s,is_default,note) "
        "VALUES ('prov_fail','http','','','NOKEY',5,0,'base_url vazio → None')",
    )
    CONN.commit()
    rid = _seed_run("RUN-EXEC-4", ["D02"])
    CONN.execute("UPDATE agent_run SET provider_id='prov_fail' WHERE run_id=?", (rid,))
    CONN.commit()
    agent = agent_exec.pending_agents(CONN, rid)[0]
    status = agent_exec.run_one(CONN, agent)
    ar = CONN.execute("SELECT status FROM agent_run WHERE id=?", (agent["id"],)).fetchone()
    assert status == "fail", f"esperado fail; obtido {status}"
    assert ar[0] == "fail"


# ──────────── anti-hardcode: sem literais de domínio/kind fora do registry ────────────
def test_no_hardcoded_domains_or_provider_kind():
    """agent_exec.py não contém nomes de domínio/método como literais de LÓGICA, e as
    strings 'stub'/'http' só aparecem no registro _PROVIDERS (valor-de-coluna → callable),
    nunca em branch de código."""
    path = os.path.join(REPO, "lab_db", "agent_exec.py")
    src = open(path, encoding="utf-8").read()
    engine = src.split("def main(")[0]  # exclui CLI demo
    banned_domains = [r"\bMecanica\b", r"\bMateriais\b", r"\bFluido[s]?\b", r"\bEnergia\b"]
    for pat in banned_domains:
        assert not re.search(pat, engine), f"agent_exec contém literal de domínio: {pat}"
    # 'kind' lógico só vive no dict _PROVIDERS — contar ocorrências de "stub"/"http"
    # fora da linha do registry: se há mais do que as do dict, é hardcode de branch.
    registry_line = [ln for ln in src.splitlines() if "_PROVIDERS" in ln and "{" in ln]
    assert registry_line, "registro _PROVIDERS ausente"
    for kind_lit in ("stub", "http"):
        total = engine.count(f'"{kind_lit}"')
        in_registry = registry_line[0].count(f'"{kind_lit}"')
        assert total == in_registry, (
            f"'{kind_lit}' aparece {total}x mas só {in_registry}x no registry _PROVIDERS "
            "— provider kind não pode ser literal de branch"
        )


# ──────────── integração: fsm.run agora EXECUTA (não mocka) ────────────
def test_fsm_run_now_executes_not_mocks():
    """Após fsm.run (happy-path com metrics VVV passando G2/G3/G4), agentes done têm
    agent_output (prova que passaram pelo executor, não pelo mock bulk-done removido)."""
    before = CONN.execute("SELECT COUNT(*) FROM agent_output").fetchone()[0]
    rid = fsm.run(CONN, dict(
        id="EXEC-INT", who="lab", what="tensão", when="2026", where="viga",
        why="fadiga", how="FEM", deformation="small",
    ), metrics={
        "mesh_error": 0.005, "time_residual": 0.003, "conservation_ok": 1,
        "error_vs_benchmark": 0.03, "error_vs_experimental": 0.04,
        "source_quality": "peer-reviewed", "reproducible": 1,
    })
    done = CONN.execute(
        "SELECT COUNT(*) FROM agent_run WHERE run_id=? AND status='done'", (rid,)
    ).fetchone()[0]
    after = CONN.execute("SELECT COUNT(*) FROM agent_output").fetchone()[0]
    assert done > 0, f"esperado ≥1 agente done; obtido {done}"
    assert after > before, (
        f"agent_output não cresceu ({before}→{after}) — executor não rodou (mock voltou?)"
    )


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
