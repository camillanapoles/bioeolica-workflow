# Backend Spec — lab_db (SSOT Relacional)

Lei do módulo `lab_db/`. Estes são padrões **descobertos no código** e validados
por 38 testes (ruff+pyright clean). Violá-los sem motivo forte quebra o mandato
do projeto.

## Mandato fundacional (inviolável)

- **Zero PyPI / zero-Pytest**: apenas `sqlite3`, `os`, `json`, `__future__` e stdlib.
  O `.venv` Python 3.14 é isolado por uv (`include-system-site-packages = false`).
  NUNCA adicionar dependência externa sem justificativa de migração documentada.
  Motivo: o engine deve rodar offline, em ambientes sem acesso ao PyPI.
- **No-hardcoded domains**: literais de domínio/método/gate/métrica/regra vivem
  **como linhas de DB** (seed), nunca como constantes de código. Cada arquivo
  `test_*.py` tem um teste `test_no_hardcoded_*` que falha se isso quebra.

## Convenções de código (validadas por ruff + pyright)

- `from __future__ import annotations` em **todo** módulo (permite `str | None` em 3.14).
- **Nomes de variáveis não-ambíguos** (ruff E741): usar `layer`, não `l`.
- **Unpacking defensivo**: quando uma função retorna `tuple | None`, NÃO fazer
  `kind, params = f()` (explode em runtime se None). Sempre:
  ```python
  resolved = f()
  assert resolved is not None, "msg"
  kind, params = resolved
  ```
- `CONN = sqlite3.connect(path, check_same_thread=False)` + `PRAGMA foreign_keys = ON`.
  Conexão única compartilhada por módulo de teste (sequential, evita "database is locked").
- `DB_PATH` determinado por `os.path` relativo ao módulo — **não depende do cwd**.

## Camadas do lab_db

| Camada | Arquivo | Responsabilidade |
|--------|---------|----------------|
| Schema (DDL) | `build.py` | Cria/recria `lab.db`, seed JSON1+JSON2, queries Q1-Q6 |
| Schema (ORM) | `models.py` | SQLAlchemy 1:1 — referência p/ migração Postgres+pgvector |
| Decisão | `dmn.py` | Engine DMN data-driven (regras como linhas) |
| FSM | `fsm.py` | Máquina F1-F7 com gates, invariantes I1-I4, loop Kaizen |
| Orquestração | `agent_exec.py` | Drenagem pending→done, provider, watchdog, run_one |
| Execução | `numeric_exec.py` | Solvers FDM reais (Poisson/Advection) keyed by DB |
| Emissão | `bpmn_emit.py` | SSOT→BPMN/DMN XML (Camunda) |
| CRUD | `crud.py` | API conn-passing sobre as tabelas |
| Grafo | `graph.py` | Projeção data-driven: nós + arestas (json/mmd/dot) |

**build.py e models.py devem permanecer 1:1** (migrar um = migrar o outro).

## Testes

- **Runner**: `python3 -m tests` (orquestrador em `tests/__main__.py`, subprocess-isolado).
  Cada módulo também roda standalone: `python3 -m tests.test_fsm`.
- Cada `test_*.py` cria **seu próprio DB temporário** no import-time via
  `tempfile.mkdtemp(prefix="<module>_test_")` — isolamento total entre módulos.
- Padrão de descoberta: `_TESTS = [v for k,v in sorted(globals().items()) if k.startswith("test_")]`,
  executados por `run_all()` que conta `PASS/FAIL` e retorna exit code.
- Sempre adicionar teste `test_no_hardcoded_*` para novo módulo com dados.

## Quando estender

- **Novo método numérico**: seed em `seed_fsm.py` (não no código) + kernel em
  `method_kernel` table + solver em `numeric_exec.py` se for computável.
- **Novo domínio runtime**: `is_seed=0`, cardinalidade decidida em gate G1.
- **Nova fase/decisão**: adicionar linha em `workflow_phase`/`dmn_rule`,
  atualizar `bpmn_emit.py` se o BPMN muda, adicionar teste `test_bpmn_*`.

## Ferramentas

| Tool | Comando | Quando |
|------|---------|-------|
| Lint | `ruff check lab_db/ tests/` | antes de commit |
| Types | `pyright lab_db/ tests/` | antes de commit |
| Testes | `python3 -m tests` | antes de commit |
| Index GN | `gitnexus analyze` | após mudanças estruturais |
| Impacto | `impact({target, direction:"upstream"})` | antes de editar símbolo |
