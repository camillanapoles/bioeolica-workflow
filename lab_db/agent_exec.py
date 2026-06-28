"""
lab_db.agent_exec — camada de EXECUÇÃO por agentes LLM (data-driven).

Worker que drena `agent_run` pendentes: resolve identidade (kdi_agent) + provider
(agent_provider) + prompt (cadeia domínio→capability→method + context_layer M³) do DB,
chama o provider (stub offline OU http via urllib stdlib), respeita o watchdog de deadline,
e escreve resultado/status de volta via CRUD (crud.set_agent_status / crud.record_gate).

Mandato ZERO-HARDCODED honrado pelo mesmíssimo padrão de `bpmn_emit._GATE_KIND`: o
provider registry é um mapping **valor-de-coluna → callable** — `kind` é lido de
`agent_provider.kind` (linha de DB), nunca literal de lógica. Prompt é montado via SQL
sobre kdi_agent + cadeia de domínio + context_layer; nenhum nome de domínio/método vive aqui.

Engine: sqlite3 + urllib (stdlib) — zero PyPI, roda offline (provider stub default).
Integrado ao fsm.run (chamado no lugar do mock F6) E entrypoint standalone
(`python3 -m lab_db.agent_exec`) para o worker Camunda/Claude-Code dev-ops.
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from datetime import datetime, timezone

from .build import connect
from . import crud, numeric_exec

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "lab.db")


def _ts() -> str:
    return datetime.now(timezone.utc).isoformat()


# ═══════════════════════ PROVIDER REGISTRY (valor-de-coluna → callable) ═══════════════════════
# Mesmo padrão estrutural de bpmn_emit._GATE_KIND: a chave é um valor de coluna lido do DB,
# não um literal de domínio. Adicionar um provider = nova linha em agent_provider + 1 entrada.
def _stub_provider(cfg: dict, system: str, user: str, deadline: str) -> str | None:
    """Provider offline determinístico. Sem rede, sem PyPI. Garante pipeline GREEN.
    Payload sintético derivado apenas do system/user recebidos — sem literais de domínio."""
    return json.dumps({
        "provider": cfg.get("id"),
        "system": system,
        "user": user,
        "executed_at": _ts(),
        "deadline": deadline,
        "mode": "offline-stub",
    }, ensure_ascii=False)


def _http_provider(cfg: dict, system: str, user: str, deadline: str) -> str | None:
    """Provider HTTP (chat-completions) via urllib (STDLIB). Auth lida de os.environ
    pelo NOME em cfg['api_key_env'] — a chave nunca entra no DB nem no código.
    Retorna o conteúdo da resposta, ou None em qualquer falha (rede/auth/timeout)."""
    base = cfg.get("base_url") or ""
    env_name = cfg.get("api_key_env") or ""
    if not base:
        return None
    key = os.environ.get(env_name, "") if env_name else ""
    timeout = int(cfg.get("timeout_s") or 60)
    body = json.dumps({
        "model": cfg.get("model") or "",
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
    }).encode("utf-8")
    req = urllib.request.Request(base, data=body, method="POST")
    req.add_header("Content-Type", "application/json")
    if key:
        req.add_header("Authorization", f"Bearer {key}")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read().decode("utf-8", errors="replace")
    except (urllib.error.URLError, urllib.error.HTTPError, OSError, ValueError):
        return None


_PROVIDERS = {"stub": _stub_provider, "http": _http_provider}


# ═══════════════════════ LEITURAS DATA-DRIVEN ═══════════════════════
def pending_agents(conn, run_id: str | None = None) -> list[dict]:
    """agent_run pendentes (opcionalmente de uma run). Status='pending'."""
    if run_id:
        rows = conn.execute(
            "SELECT id,run_id,domain_id,method_id,provider_id FROM agent_run "
            "WHERE status='pending' AND run_id=? ORDER BY id",
            (run_id,),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT id,run_id,domain_id,method_id,provider_id FROM agent_run "
            "WHERE status='pending' ORDER BY id"
        ).fetchall()
    return [{"id": r[0], "run_id": r[1], "domain_id": r[2],
             "method_id": r[3], "provider_id": r[4]} for r in rows]


def resolve_provider(conn, agent: dict) -> tuple[str, dict]:
    """Resolve o provider: agent_run.provider_id se setado, senão a linha is_default=1.
    Retorna (kind, cfg_row) — tudo do DB, zero hardcode de qual/kind."""
    pid = agent.get("provider_id")
    if pid:
        row = conn.execute(
            "SELECT id,kind,model,base_url,api_key_env,timeout_s FROM agent_provider WHERE id=?",
            (pid,),
        ).fetchone()
    else:
        row = conn.execute(
            "SELECT id,kind,model,base_url,api_key_env,timeout_s FROM agent_provider "
            "WHERE is_default=1 LIMIT 1"
        ).fetchone()
    if not row:
        raise RuntimeError("nenhum agent_provider configurado (rode seed_providers)")
    kind, cfg = row[1], {"id": row[0], "kind": row[1], "model": row[2], "base_url": row[3],
                         "api_key_env": row[4], "timeout_s": row[5]}
    return kind, cfg


def build_prompt(conn, agent: dict) -> tuple[str, str]:
    """Monta (system, user) do DB: kdi_agent (identidade) + cadeia domínio→capability +
    method (regime/continuity/mesh) + context_layer (M³ macro/meso/micro) + research_context.
    Tudo via SQL — nenhum nome de domínio/método é literal aqui."""
    kdi = conn.execute(
        "SELECT role,methodology,principle,philosophy FROM kdi_agent LIMIT 1"
    ).fetchone()
    caps = conn.execute(
        "SELECT c.name FROM domain_catalog d "
        "JOIN domain_capability dc ON dc.domain_id=d.id "
        "JOIN capability c ON c.id=dc.capability_id WHERE d.id=?",
        (agent["domain_id"],),
    ).fetchall()
    method = conn.execute(
        "SELECT regime,continuity,mesh FROM numerical_method WHERE id=?",
        (agent["method_id"],),
    ).fetchone() if agent.get("method_id") else None
    layers = conn.execute("SELECT id,name FROM context_layer ORDER BY id").fetchall()
    ctx_json = conn.execute(
        "SELECT research_context_json FROM workflow_instance WHERE run_id=?",
        (agent["run_id"],),
    ).fetchone()

    role = (kdi[0] if kdi else "agente especialista")
    system = (
        f"role: {role}\n"
        f"methodology: {kdi[1] if kdi else ''}\n"
        f"principle: {kdi[2] if kdi else ''}\n"
        f"philosophy: {kdi[3] if kdi else ''}\n"
        f"capabilities: {[c[0] for c in caps]}\n"
        f"context_layers (M3 macro/meso/micro): {[{'id': layer[0], 'name': layer[1]} for layer in layers]}"
    )
    user = (
        f"run_id={agent['run_id']} domain={agent['domain_id']} "
        f"method={agent.get('method_id')} "
        f"characteristics={list(method) if method else None}\n"
        f"research_context: {ctx_json[0] if ctx_json else '{}'}"
    )
    return system, user


# ═══════════════════════ WATCHDOG (deadline da run) ═══════════════════════
def _earliest_deadline(conn, run_id: str) -> str | None:
    """Deadline mais cedo entre watchdogs ainda armados (tripped=0) da run.
    Se já passou do now → a run está sem tempo → agente deve TIMEOUT."""
    row = conn.execute(
        "SELECT MIN(deadline) FROM timeout_watchdog WHERE run_id=? AND tripped=0",
        (run_id,),
    ).fetchone()
    return row[0] if row else None


# ═══════════════════════ EXECUÇÃO ═══════════════════════
def _set_running(conn, agent_id: str):
    """Marca agente running + started_at (lock de execução). Estado intermed. não-terminal."""
    conn.execute(
        "UPDATE agent_run SET status='running', started_at=? WHERE id=?",
        (_ts(), agent_id),
    )
    conn.commit()


def _append_output(conn, agent_id: str, payload: str):
    """Grava payload em agent_output (append-style SSOT — casa do 'resultado real')."""
    conn.execute(
        "INSERT INTO agent_output (agent_id,payload,created_at) VALUES (?,?,?)",
        (agent_id, payload, _ts()),
    )
    conn.commit()


def run_one(conn, agent: dict) -> str:
    """Executa UM agente: running → (watchdog check) → provider call → done/fail/timeout.
    Retorna o status terminal alcançado."""
    _set_running(conn, agent["id"])

    # Watchdog: se a run está fora de tempo (deadline armado já expirou) → TIMEOUT.
    deadline = _earliest_deadline(conn, agent["run_id"])
    if deadline and deadline < _ts():
        crud.set_agent_status(conn, agent["id"], "timeout",
                              result_ref=f"MAP/EXE/{agent['run_id']}/{agent['domain_id']}/TIMEOUT",
                              method_id=agent.get("method_id"))
        crud.record_gate(conn, agent["run_id"], "G5", "TIMEOUT", phase="F6",
                         decided_by="watchdog", detail=f"agent {agent['id']} deadline={deadline}")
        return "timeout"

    kind, cfg = resolve_provider(conn, agent)

    # Caminho NUMÉRICO (prioridade): se o method_id tem kernel mapeado (method_kernel — DADO),
    # executa o solver de verdade e grava resultados numéricos reais em agent_output. Sem kernel
    # → cai para o provider (stub/http) abaixo. Ramo estritamente aditivo: nada muda quando não
    # há linha em method_kernel (preserva regressão 20/20).
    numeric = numeric_exec.run_numeric(conn, agent)
    if numeric is not None:
        payload = json.dumps({"executed_at": _ts(), "deadline": deadline or "",
                              "mode": "real-numeric", "result": numeric}, ensure_ascii=False)
        _append_output(conn, agent["id"], payload)
        crud.set_agent_status(conn, agent["id"], "done",
                              result_ref=f"MAP/EXE/{agent['run_id']}/{agent['domain_id']}/NUMERIC",
                              method_id=agent.get("method_id"))
        return "done"

    system, user = build_prompt(conn, agent)
    fn = _PROVIDERS.get(kind)
    result = fn(cfg, system, user, deadline or "") if fn else None

    if result is None:
        crud.set_agent_status(conn, agent["id"], "fail",
                              result_ref=f"MAP/EXE/{agent['run_id']}/{agent['domain_id']}/FAIL",
                              method_id=agent.get("method_id"))
        return "fail"

    _append_output(conn, agent["id"], result)
    crud.set_agent_status(conn, agent["id"], "done",
                          result_ref=f"MAP/EXE/{agent['run_id']}/{agent['domain_id']}",
                          method_id=agent.get("method_id"))
    return "done"


def run_pending(conn, run_id: str | None = None) -> int:
    """Drena todos os agent_run pendentes (de uma run ou globais). Retorna o count executado."""
    agents = pending_agents(conn, run_id)
    for a in agents:
        run_one(conn, a)
    return len(agents)


# ═══════════════════════ CLI / worker standalone ═══════════════════════
def main():
    """Worker standalone (modo Camunda/Claude-Code dev-ops). Drena pendentes do DB.
    O provider usado é definido pela linha is_default=1 (dados), não por flag de código."""
    conn = connect()
    n = run_pending(conn)
    summary = conn.execute(
        "SELECT status, COUNT(*) FROM agent_run GROUP BY status ORDER BY status"
    ).fetchall()
    outs = conn.execute("SELECT COUNT(*) FROM agent_output").fetchone()[0]
    conn.close()
    print(f"agent_exec: {n} agente(s) drenado(s).")
    for status, count in summary:
        print(f"  {status:<10} {count}")
    print(f"agent_output: {outs} payload(s)")


if __name__ == "__main__":
    main()
