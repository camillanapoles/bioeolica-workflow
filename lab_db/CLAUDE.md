[raiz](../CLAUDE.md) > **lab_db**

# lab_db — SSOT Relacional Integrado (JSON1 + JSON2)

## Responsabilidade do Módulo

Materializar o mandato de governança como **dados consultáveis**: carrega o JSON1 (KDI `mech-electro-materials-scientist` v3.0-omnibus) e o JSON2 (Engine Omnibus / Kaizen — 8 partes) num único banco SQLite integrado, e deriva um **knowledge graph data-driven** dele. O código é apenas o "motor fino" (schema + relações + projeção); **todos os valores de domínio/método/gate/métrica/regra vivem como linhas de DB**, honrando o mandato no-hardcoded.

**Engine**: `sqlite3` da biblioteca padrão (zero PyPI) — roda offline em ambientes sem acesso ao PyPI. O schema espelha 1:1 o ORM SQLAlchemy em `models.py`, de modo que a migração para PostgreSQL+pgvector em produção não exija mudança de schema.

## Entrada e Execução

| Comando | Ação | Saída |
|---------|------|------|
| `python3 -m lab_db.build` | Apaga/recria `lab.db`, executa DDL, carrega JSON1+JSON2, insere 1 linha demo de WAL, roda queries Q1-Q6 | `lab.db` + relatório stdout |
| `python3 -m lab_db.graph` | Lê `lab.db` via SQL e projeta nós/arestas | `lab_db/graph_out/{graph.json,graph.mmd,graph.dot}` |

Ambos determinam `DB_PATH` por `os.path` relativo ao módulo — independente do cwd.

## Interfaces Externas

- **DB file**: `lab.db` (SQLite, `PRAGMA foreign_keys = ON`) — consumido por futuros orquestradores/agente via SQL direto.
- **Saídas de grafo**: três formatos paralelos (`graph.json` estruturado, `graph.mmd` Mermaid, `graph.dot` Graphviz) para visualização em qualquer pipeline.
- **Queries de descoberta Q1-Q6** (em `build.run_queries`): Q1 métodos+ferramentas por domínio · Q2 cardinalidade runtime do time · Q3 caminho F1-F7 com gate/fail_target/mandato · Q4 métricas D* e gates · Q5 mandatos M1-M7 · Q6 métodos por origem (JSON1 vs JSON2).

## Dependências e Configuração-Chave

- **Sem dependências externas** para `build.py`/`graph.py` (apenas `sqlite3`, `json`, `os`, `__future__`).
- `models.py` referencia `sqlalchemy` — **opcional**, usado como referência ORM para migração; não é exigido para construir o DB.
- `.venv` = Python 3.14; `.envrc` ativa o venv automaticamente.
- `DB_PATH = <repo_root>/lab.db` (recriado a cada `build` — não é artefato persistente).

## Modelo de Dados (18 tabelas)

**Cadeia central (JSON1)**: `domain_catalog` →(`domain_capability`)→ `capability` →(`capability_method`)→ `numerical_method` →(`method_tool`)→ `tool`.

| Grupo | Tabelas |
|-------|---------|
| Identidade KDI | `kdi_agent` |
| Cadeia domínio→método→ferramenta | `domain_catalog`, `capability`, `numerical_method`, `tool`, `domain_capability`, `capability_method`, `method_tool` |
| Comportamento socrático | `socratic_rule`, `response_step` |
| Contexto | `context_layer`, `context_method`, `output_standard`, `knowledge_source` |
| Governança/fluxo (JSON2) | `mandate`, `workflow_phase`, `quality_metric`, `wal_log` |

**Notas**:
- `domain_catalog.is_seed` distingue os 10 domínios-base (`is_seed=1`) dos derivados em runtime (`is_seed=0`).
- `numerical_method.source` = `"JSON1"` (FEM/FVM/FDM/BEM/IGA/ROM/PINNs) ou `"JSON2"` (SPH/DEM/MPM/Peridynamics) — rastreia a integração.
- `workflow_phase` carrega `gate`, `gate_type`, `dmn_source`, `fail_target`, `mandate_ref` — o BPMN/FSM **como dados**.
- `wal_log` é append-only (`autoincrement`, `run_id` indexado).

## Testes e Qualidade

- **Sem `tests/`** no módulo (gap registrado). Cobertura indireta: Q1-Q6 validam relacionalmente o schema pós-seed.
- Mandato **M3 (VVV)** não tem cobertura automatizada — pendência explícita.

## FAQ

- **Por que DDL em `build.py` E ORM em `models.py`?** — Para o core offline rodar sem SQLAlchemy (sqlite3 puro); `models.py` documenta o schema-alvo para migração PostgreSQL. Devem permanecer **1:1** (migrar um = migrar o outro).
- **Os 10 domínios são fixos?** — Não. São SEED (`is_seed=1`). Domínios runtime entram com `is_seed=0`; a cardinalidade do time é variável (decidida em G1).
- **Onde vivem os DMN referenciados?** — Hoje `workflow_phase.dmn_source` guarda apenas os nomes (`dmn_relevance_check`, `dmn_method_selection`, `dmn_vvv_acceptance`); a implementação DMN é passo seguinte.

## Arquivos Relevantes

| Arquivo | Papel |
|---------|-------|
| `lab_db/build.py` | DDL + seed JSON1/JSON2 + queries Q1-Q6 + `main()` |
| `lab_db/graph.py` | Projeção data-driven: nós tipados, arestas (cadeia + transições F1-F7 + loops kaizen + validates) |
| `lab_db/models.py` | ORM SQLAlchemy 1:1 (referência de schema, não exigido p/ build) |
| `lab_db/__init__.py` | Docstring de navegação dos submódulos |
| `lab.db` | Artefato SSOT gerado (não versionar) |
| `lab_db/graph_out/*` | Saídas json/mmd/dot regeneráveis |

## Changelog

| Data | Ação |
|------|------|
| 2026-06-28T02:32Z | CLAUDE.md do módulo criado pelo arquiteto (inicialização). |
