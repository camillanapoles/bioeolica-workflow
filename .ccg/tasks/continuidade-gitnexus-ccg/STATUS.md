# STATUS — Continuidade do Projeto bioeolica-workflow

**Última verificação**: 2026-06-28T14:02Z (alinhado com sessão fcc-claude `agent-execution-layer`)
**Branch ativa**: `main` (HEAD `641178a` — merge do PR #4)
**Mandato**: zero-PyPI, SSOT data-driven, multi-modelo (KDI composition)
**Orquestração**: fcc-claude (proxy glm-5.2) + CCG + GitNexus + mgrep

---

## Estado de Saúde (snapshot)

| Verificação | Estado | Detalhe |
|-------------|--------|---------|
| Testes | ✅ 38/38 | 5 módulos, todos passando via `python3 -m tests` |
| Lint (ruff) | ✅ clean | `ruff check lab_db/ tests/` → 0 erros |
| Types (pyright) | ✅ clean | `pyright lab_db/ tests/` → 0 errors |
| GitNexus index | ✅ fresh | `main@641178a` — 635 nós / 943 arestas / 24 flows |
| Stack continuidade | ✅ operacional | fcc-server, fcc-claude, mgrep, gitnexus |
| Git working tree | ⚠️ uncommitted | fixes + infra CCG + .gitignore ready p/ commit |
| `.ccg/` infra | ✅ criado | spec/backend, tasks/, este doc |

## Arquitetura atual (lab_db)

```
JSON1 (KDI) + JSON2 (Kaizen)
        │
        ▼
   build.py ── DDL + seed ──▶ lab.db (SQLite SSOT)
        │
        ├── models.py (ORM SQLAlchemy 1:1, ref p/ Postgres+pgvector)
        ├── crud.py (API conn-passing)
        ├── dmn.py (decisão data-driven)
        ├── fsm.py (máquina F1-F7, gates, invariantes I1-I4, loop Kaizen)
        ├── agent_exec.py (orquestração LLM worker, watchdog, run_one)
        ├── numeric_exec.py (solvers FDM reais keyed by DB)
        └── bpmn_emit.py (SSOT→BPMN/DMN XML Camunda)
```

## Roadmap (estado real após merge em main)

| Fase | Commit em `main` | Estado |
|------|-------------------|--------|
| FSM data-driven | `e43bcd5` (#1) | ✅ merged |
| BPMN/DMN emit | `978c28e` | ✅ merged |
| Agent execution | `b157861` | ✅ merged |
| Numeric exec (real) | `37236da` | ✅ merged |
| ORM reconcile | `315df66` | ✅ merged (blast radius 0) |
| Security harden | `2dd99bf` | ✅ merged (COUNT query whitelist) |
| PR #4 integration | `641178a` | ✅ HEAD (default branch corrigido) |
| **Próximo** | — | 🟡 gate G4/Validada sobre agent_output numérico |

### Próximos passos (da sessão fcc-claude `agent-execution-layer`)

- Gate **G4/Validada** sobre `agent_output` numérico (validar `field_max` vs `analytic_max` — o VVV que falta).
- **Report F7** agregando `field_max/analytic_max` + mapear mais `method_id→kernel` (DEM/MPM/SPH/PINNs).
- Paper + provider `http` real (LLM local `localhost:11434/v1`).
- Checkpoint memory (stack merged, sem débito ativo).
- **Nenhum bloqueio funcional** — apenas fricção pontual de sandbox em `.git/config` / `.claude/settings.json`.

### Pendências estruturais (de lab_db/CLAUDE.md)

- Migração `models.py` SQLAlchemy → PostgreSQL+pgvector em produção.
- `wal_log` WAL selado: auditoria append-only existe mas sem checkpoint/rotate.

## Stack de continuidade (orquestrada CCG)

| Componente | Papel | Estado |
|------------|-------|--------|
| `fcc-server` (pid 36536, :8082) | Proxy multi-modelo (ZAI/glm-5.2) | ✅ 2d18h uptime |
| `fcc-claude` (session `agent-execution-layer`) | Claude Code via proxy — gestão do timeline | ✅ ativa |
| `gitnexus` (MCP + CLI) | Knowledge graph — impacto/blast-radius | ✅ fresh @641178a |
| `mgrep` | Busca semântica (dry-run local / sync remoto) | ✅ operacional |
| `scripts/verify.sh` | Gate de continuidade (iron rule #6) | ✅ PASS |

## Como rodar a verificação de continuidade (orquestrada)

```bash
source .venv/bin/activate
bash scripts/verify.sh                        # gate completo (ruff+pyright+tests+gitnexus)
ruff check lab_db/ tests/                     # lint (isolado)
pyright lab_db/ tests/                        # types (isolado)
python3 -m tests                              # testes (5 módulos, 38 testes)
gitnexus status                               # freshness do índice
mgrep search "<symbol>" lab_db/ -d -c         # busca semântica local (dry-run)
```

## Como retomar a sessão fcc-claude

```bash
ANTHROPIC_BASE_URL=http://127.0.0.1:8082 \
ANTHROPIC_AUTH_TOKEN="$(grep ^ANTHROPIC_AUTH_TOKEN= ~/.fcc/.env | cut -d= -f2)" \
ANTHROPIC_MODEL="anthropic/zai/glm-5.2" \
claude --resume 15e7c37e-6be5-4d3f-92d2-6a57d982a351
```

Todos os gates devem passar antes de declarar tarefa completa (CCG iron rule #6).
