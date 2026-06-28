# Objetivo Global — Workflow: Laboratório Computacional Multi-Agente → Resultados de Lab Real → Report + Paper

**Fonte:** mandato do usuário (FSM de governança) + Engine Omnibus v3.0-unified. Este documento é o **contrato de rastreabilidade** que liga cada fase do engine a um artefato concreto no SSOT (`lab.db`) e a um entregável de pesquisa.

---

## 1) Cadeia do Objetivo Global

```
Enunciado de pesquisa
   │  PRE-ALWAYS (P7): contexto antes de ação
   ▼
[F1 Captura 5W1H+Ishikawa] ── WAL ──> research_context
   │  G0 (completeness)
   ▼
[F2 Deriva domínios] ── dmn_relevance_check ──> runtime_domain[] (is_seed=0)
   │  G1 (XOR, por domínio) ──> team_instance{cardinality=N}  (spawn multi-agente)
   ▼
[F3 Decomposição M³ + decision-tree método] ── dmn_method_selection ──> analysis_plan{macro,meso,micro,method,tools}
   │  G_método (DMN)
   ▼
[F4 Execução da análise] ── agent_run(status) ── solver executa ──> raw_result
   │  G2 Verificação (convergência/unidades)   watchdog G2
   │  G3 Validação (benchmark/exp/analítica)    watchdog G3
   │  G4 Validada (fonte+erro+reprodutível)     watchdog G4
   ▼
[F5 Correlação Holística meso] ── integrated_result{correlations, conflicts}
   │  G5 Cobertura 75–90% (D1)                  watchdog G5
   ▼
[F6 Cobertura + Memória] ── WAL selado + Mapa Único + RAG
   ▼
[F7 Entrega Validada] ── deliverable{artifact, trace_id, quality_report}
   │
   ├──> REPORT FINAL (execução + métricas D1-D10 + VVV)
   └──> PAPER (metodologia + resultados + incerteza + referências)
```

## 2) Garantias do lab (PRE-ALWAYS, KDI, M³, comunicação on-time)

| Garantia | Como é garantida no SSOT |
|----------|--------------------------|
| **PRE-ALWAYS** (contexto antes de ação) | F1 obrigatório; G0 bloqueia avanço sem 5W1H+Ishikawa completos |
| **Seleção KDI** | `dmn_relevance_check` (linhas em `dmn_decision`) decide domínios runtime |
| **Análise Macro/Meso/Micro** | `analysis_plan` em F3 obrigatoriamente com 3 escalas; gap detection registrado |
| **Comunicação on-time** | `timeout_watchdog` + `gate_event(TIMEOUT)` escalonam se agente não responder no deadline |
| **Resultados de lab real** | `agent_run.result_ref` + `gate_event(verdict=PASS em G3/G4)` atestam validação contra benchmark |
| **Report final + paper** | F7 empacota `deliverable` rastreável por `trace_id` ligado ao WAL |

## 3) FSM de gates com watchdog (monitoramento por tempo)

Cada gate tem watchdog armado em `arm_watchdogs(run_id)`. Se nenhum `PASS`/`FAIL` for registrado antes do deadline → `trip_expired()` registra `gate_event(verdict=TIMEOUT)` e o orquestrador escala (re-spawn de agente, recomposição de time, ou incidente Camunda — conforme `04-fsm-gates-triggers.md`).

Thresholds (como **dados** em `WATCHDOG_THRESHOLDS`): G1=5min, G2=30min, G3=60min, G4=30min, G5=10min.

## 4) Checklist para o primeiro lab concreto

Antes de rodar um lab real, decidir (com humano, no gate de escopo):

- [ ] **Domínio-alvo**: qual produto física o primeiro lab resolve (ex.: turbina eólica, vaso de pressão, compressor H₂)? — define o conteúdo dos 10 domínios SEED aplicáveis.
- [ ] **Benchmark de validação (G3/G4)**: dado experimental/analítico de referência — sem ele, VVV não fecha.
- [ ] **Solver executor**: o que `agent_run` dispara de fato (CalculiX? OpenFOAM? mock?). Hoje o `agent_run` registra apenas status; a invocação do solver é o próximo acoplamento.
- [ ] **Formato do paper**: template (LaTeX/IEEE/Elsevier) e repositório de referências (RAG).
- [ ] **Decision-tree de método**: confirmar que `dmn_method_selection` cobre o regime do domínio-alvo (acrescentar linhas se preciso — sempre como dados).

## 5) Onde cada coisa vive (mandato: dados em DB, não em código)

| Entidade | Tabela em `lab.db` |
|----------|-------------------|
| Domínios base | `domain_catalog` (is_seed=1) |
| Domínios runtime | `runtime_domain` (is_seed=0, derivados) |
| Time + cardinalidade | `team_instance` |
| Agente especialista | `agent_run` |
| Regras de decisão | `dmn_decision` (relevance / method_selection / vvv_acceptance) |
| Verdicts de gate | `gate_event` |
| Monitoramento de timeout | `timeout_watchdog` |
| Métricas D1-D10 | `quality_metric` |
| Mandatos M1-M7 | `mandate` |
| Estados F1-F7 + gates | `workflow_phase` |
| Rastreabilidade append-only | `wal_log` |

## 6) Como rodar a cadeia hoje (estado atual)

```bash
source .venv/bin/activate
python3 -m lab_db.build          # SSOT base (JSON1+JSON2) + Q1-Q6
python3 -m lab_db.extensions     # multi-agente + DMN + watchdog + EXT-Q1..Q4
pytest -q                        # valida CRUD, DMN, gates, watchdog
```

**Próximo acoplamento pendente**: ligar `agent_run` a um executor de solver real (mock → CalculiX/OpenFOAM) e gerar `result_ref` consumível por F5 e pelo template de paper.
