# 04 — FSM Rigorosa: Estágios, Gates, Gatilhos, Fluxos e Conexões

**Fonte:** DOC2-KAIZEN Partes 6 (Fluxo F1–F7) + 5 (Mandatos) + 3 (decision-tree) + DOC1 `socratic_behavior.response_structure` (6 passos) + retificação "domínios context-dependent".

**Finalidade:** especificar a máquina de estados da orquestração com rigor — cada estágio tem **trigger de entrada, atividade, contrato de dados de saída, condition de saída**; cada gate tem **tipo, pergunta, fonte DMN, fail_target**. A cardinalidade do time é **variável** (derivada em F2, decidida em G1), nunca fixada em código.

---

## 1) Catálogo de Estados (F1–F7)

| state_id | nome | trigger de entrada | atividade principal | contrato de saída (data) | condition de saída |
|---|---|---|---|---|---|
| **F1** | Captura de Contexto | `Start: enunciado/produto recebido` | 5W1H + Ishikawa + 7 context_layers | `research_context{who,what,when,where,why,how,how_much, ishikawa_causes[], layers[7]}` | `research_context` persistido no WAL |
| **F2** | Derivação de Domínios | `on research_context persisted` | KDI lê `domain_catalog`(SEED) + contexto → propõe `runtime_domain[]`; roda `dmn_relevance_check` por domínio | `team_instance{agents[], cardinality=N}` (N variável) | `cardinality ≥ 1` ∧ todos com `relevance_score` |
| **F3** | Decomposição M³ | `on team composed (F2 exit)` | por domínio (multi-instance): Macro/Meso/Micro + ferramentas (M1) + `dmn_method_selection` | `analysis_plan{domain, m3{macro,meso,micro}, method, tools[]}` | 1 plano por agente, método selecionado |
| **F4** | Execução da Análise | `on analysis_plan ready` | executar solver/metodologia | `analysis_result{raw, metadata, solver, run_id}` | resultado + metadados brutos |
| **F5** | Correlação Holística | `on all domain results join (P2)` | integração meso dos resultados | `integrated_result{correlations[], conflicts[]}` | sem conflitos não-resolvidos |
| **F6** | Cobertura + Memória | `on G5 PASS` | WAL append + Mapa Único + índice RAG | `wal_log[]`, `map_index`, `rag_embeddings` | WAL selado + índice atualizado |
| **F7** | Entrega Validada | `on F6 exit` | empacotar entrega rastreável | `deliverable{artifact, trace_id, quality_report}` | `End` |

> **Nota:** a `response_structure` de 6 passos do KDI (JSON1) é o **micro-fluxo interno de cada agente dentro de F3–F4** (VALIDAÇÃO→FUNDAMENTAÇÃO→METODOLOGIA→EXECUÇÃO→VALIDAÇÃO→EXTENSÃO), não um nível alternativo.

---

## 2) Catálogo de Gates (G1–G5) — decisões auditáveis

| gate_id | tipo | pergunta / critério | fonte (DMN/mandato) | PASS → | FAIL → |
|---|---|---|---|---|---|
| **G0** | completeness (pré) | 5W1H + Ishikawa completos? | heuristic | F2 | F1 |
| **G1** | XOR (relevance) | domínio aplicável? | `dmn_relevance_check` | inclui agente | exclui + `justification` |
| **G_método** | DMN (seleção) | deformação×continuidade×malha → método? | `dmn_method_selection` | método lock | F3 |
| **G2** | XOR (Verificação) | convergência, estabilidade, unidades, conservação? (M3) | `dmn_vvv_acceptance[V]` | G3 | F4 |
| **G3** | XOR (Validação) | benchmark/exp/analítica/cross-code? (M3) | `dmn_vvv_acceptance[Val]` | G4 | F3 |
| **G4** | XOR (Validada) | fonte confiável + erro quantificado + reprodutível? (M3) | `dmn_vvv_acceptance[Vali]` | P2 (join) | F2 |
| **G5** | XOR (cobertura) | 75–90% dos domínios relevantes cobertos? (D1) | métrica D1 | F6 | F2 |

**Regra de loop Kaizen (DOC2 Parte 8→1):** cada FAIL retorna à fase **anterior adequada**, nunca ao início. Falhas repetidas > threshold → **incidente Camunda** (escalonamento), não loop infinito.

---

## 3) Triggers formalizados (tipos de evento BPMN)

| trigger | tipo BPMN | quando dispara |
|---|---|---|
| `enunciado_recebido` | StartEvent (message) | chega enunciado de pesquisa |
| `context_persisted` | MessageCatch | WAL grava `research_context` → libera F2 |
| `team_composed` | Signal | F2 produz `team_instance` → libera F3 (multi-instance) |
| `result_ready` | MessageCatch | agente entrega `analysis_result` → join |
| `gate_verdict` | Conditional | DMN emite PASS/FAIL → escolhe sequence flow |
| `retry_budget_exceeded` | Error (boundary) | retries > threshold → incidente |
| `coverage_ok` | Conditional | D1 ∈ [0.75, 0.90] → libera F6 |

---

## 4) Transições (conexões explícitas: from → to)

```
Start ─msg─> F1
F1  ─[G0 PASS]─> F2
F1  ─[G0 FAIL]─> F1
F2  ─[G1 PASS domínio N]─> spawn agent_N   (multi-instance)
F2  ─[G1 FAIL domínio]─> exclude(domain, justification)
F2  ─[team_composed]─> F3       # cardinalidade = N (variável)
F3  ─[G_método seleciona]─> F4
F3  ─[G_método FAIL]─> F3
F4  ─[G2 PASS]─> G3
F4  ─[G2 FAIL]─> F4
G3  ─[PASS]─> G4
G3  ─[FAIL]─> F3
G4  ─[PASS]─> P2(join)
G4  ─[FAIL]─> F2               # recompor time
P2  ─all joined─> F5
F5  ─[G5 PASS]─> F6
F5  ─[G5 FAIL]─> F2            # expandir domínios
F6  ─persisted─> F7 ─> End
qualquer gate ─[retry_budget_exceeded]─> Incident
```

**Invariantes de conexão:**
- **I1:** não existe transição direta F4→F1 (proibido reinício total).
- **I2:** todo FAIL tem `fail_target` ∈ {F1,F2,F3,F4} definido no catálogo.
- **I3:** `cardinality(F2_out) == cardinality(P2_in)` (todo agente spawnado joina).
- **I4:** `G5` só dispara após `P2` (join completo).

---

## 5) Derivação dinâmica de domínios (F2) — onde a cardinalidade é decidida

1. **Ler** `domain_catalog WHERE is_seed=true` (10 candidatos base).
2. **Cruzar** com `research_context` (5W1H + Ishikawa) → gerar candidatos extras (ex.: Ishikawa aponta "vibração" → propõe `Dinâmica_de_Vibrações`, fora do seed).
3. **Para cada candidato**, chamar `dmn_relevance_check(domain, context)` → `{applicable: bool, score: 0..1, justification}`.
4. `applicable=true` → criar `runtime_domain` + `agent_role` + spawn (multi-instance).
5. `cardinality = |{applicable}|` → **3, 7, 12, ...** — variável por execução.

> Satisfaz: (a) **no-hardcode** — domínios são linhas de DB + saída de DMN; (b) **context-dependent** — 10 são seed; (c) **rastreável** — toda inclusão/exclusão tem `justification` no WAL.

---

## 6) FSM ↔ BPMN ↔ DMN ↔ mandatos

| FSM | BPMN | DMN | mandato | métrica |
|---|---|---|---|---|
| F1 | task `Capturar Contexto` | — | M4 (WAL) | D2 (5W1H completo) |
| F2 | task `Compor Team` + multi-instance | `dmn_relevance_check` | M7 (governança) | D1 (cobertura) |
| G_método | task `Selecionar método` | `dmn_method_selection` | M1 (open source) | — |
| F4 | task `Executar análise` | — | M3 (VVV) | D3 (convergência) |
| G2/G3/G4 | exclusiveGateways | `dmn_vvv_acceptance[V/Val/Vali]` | M3 (VVV triplo) | D4–D6 |
| F5 | task `Correlação Holística` | — | M5 (Mapa Único) | D7 (meso) |
| G5 | gateway `Cobertura 75-90%` | — | M7 | D1 |
| F6 | task `WAL + RAG` | — | M4/M5/M6 | D8–D10 |

---

## 7) Pendências

- [ ] Validar invariantes I1–I4 via CPT.
- [ ] Materializar as 3 DMNs com regras extraídas de DOC2 (sem literais em código).
- [ ] Conectar ao grafo `bioeolica` (nós `workflow_phase`/`gate`/`trigger`) quando o classificador MCP recuperar.
