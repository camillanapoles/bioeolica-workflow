# 03 — Modelo Relacional Integrado (JSON1 + JSON2) e Descoberta por Query

**Fonte:** `DOC1-KDI_MECH-ELECTRO-MATERIALS.md` (JSON1 — KDI `mech-electro-materials-scientist` v3.0-omnibus) + `DOC2-KAIZEN.md` (JSON2 — Engine Omnibus v3.0, 8 partes) + `INSTRUCTIONS.md` (mandato de governança).

**Finalidade:** cumprir o mandato — *"extrair JSON1, carregar num DB, usar o objeto JSON para entender relacionamentos por query, depois adicionar JSON2 (Kaizen) ao DB integrado, respeitando a integração de JSON1, de modo que via query se obtenha tudo."* Este documento é o **schema SSOT** (futuro PostgreSQL + pgvector); a descoberta relacional é demonstrada por queries exemplificativas.

> **Status do graph DB em sessão:** o classificador MCP para escritas está temporariamente indisponível neste turno; o carregamento no `mcp__graph-engine` (grafo `bioeolica`) fica pendente. O modelo abaixo é o que será carregado (nós + arestas) e o que o PostgreSQL materializará (tabelas + FKs).

---

## 0) Retificação de modelo (correção de paradeigma)

| Antes (incorreto) | Agora (correto) |
|---|---|
| 10 domínios fixos | **10 domínios = apenas SEED/base de construção** (os mais comuns). O conjunto real de uma execução é **derivado do contexto** — pode haver **mais ou menos** que 10. |
| `domain_catalog` = enumeração fechada | `domain_catalog` = **catálogo-semente** + `runtime_domain` derivado por **KDI + 5W1H + Ishikawa** |
| 5W1H/Ishikawa/KDI mencionados de passagem | **Enforçados como estágios/gates/gatilhos rigorosos** no fluxo |

Consequência estrutural: a cardinalidade do time (multi-instance) é **decidida em runtime** pela query `relevance_check` sobre `runtime_domain`, nunca fixada em código.

---

## 1) JSON1 → modelo relacional (KDI como dados)

### 1.1 `kdi_agent` (raiz identidade)
| coluna | valor (JSON1) |
|---|---|
| `agent_id` | `mech-electro-materials-scientist` |
| `version` | `3.0-omnibus` |
| `principle` | `socratic-context-first` |
| `philosophy` | `teach-to-fish-never-limit-quantity` |
| `role` | `Engenheiro Cientista Multidisciplinar` |
| `expertise_level` | `SOTA 2025-2026` |
| `methodology` | `Computacional-first · Analítico-validado · Experimental-correlacionado` |

### 1.2 `domain_catalog` (SEED — 10, context-dependent)
> **NÃO é fechado.** É a base semeada. Cada linha tem `is_seed=true`. Domínios runtime são inseridos em `runtime_domain` quando derivados do contexto.

| domain_id | name | is_seed | typical_capability |
|---|---|---|---|
| D01 | Mecânica | true | structural_analysis |
| D02 | Eletrotécnica | true | energy_systems |
| D03 | Materiais | true | materials_science |
| D04 | Análise Computacional | true | computational_analysis |
| D05 | Mecânica dos Fluidos | true | fluid_dynamics |
| D06 | Mecânica dos Sólidos | true | structural_analysis |
| D07 | Elementos Finitos (FEM) | true | computational_analysis |
| D08 | Análise de Tensões e Esforços | true | structural_analysis |
| D09 | Dinâmica de Cargas | true | structural_analysis |
| D10 | Energia e Sistemas Energéticos | true | energy_systems |

### 1.3 `capability` (5) — ramo `core_capabilities`
| capability | governs / models |
|---|---|
| computational_analysis | methods: FEM, FVM, FDM, BEM, IGA, SPH, DEM, ROM, PINNs · tools: ANSYS, ABAQUS, COMSOL, OpenFOAM, CalculiX, FEniCS, ParaView, NumPy/SciPy, Julia/Gridap |
| fluid_dynamics | eqs: Navier-Stokes, Euler, Bernoulli, RANS, LES, DNS · subs: CFD, turbulência, multifásico |
| materials_science | models: elasticidade, plasticidade (vM), visco, fratura LEFM, creep, fadiga SN |
| structural_analysis | loads: estáticas, dinâmicas, térmicas, pressão, fadiga · stress: principais, vM equivalente, concentração |
| energy_systems | methods: exergética, entrópica, ciclos Rankine/Brayton, multi-objetivo |

### 1.4 `numerical_method` (folhas da decision-tree — Parte 3 enriquece)
| method | regime | continuity | mesh |
|---|---|---|---|
| FEM | pequena deformação | sólido | requer malha |
| FVM | volumes finitos | fluido | estruturada |
| MPM | grande deformação | partícula-matéria | material point |
| SPH | sem malha | livre-livre | kernel |
| DEM | granular/descontínuo | discreto | partículas |
| Peridynamics | fratura/discreto | sem malha | bonds |
| IGA / ROM / PINNs | reduzido/neural | — | NURBS/POD/NN |

### 1.5 `socratic_rule` (8) e `response_step` (6)
- **Regras:** SR1 nunca resposta-pronta · SR2 nunca limitar quantidade · SR3 explicar *porque* antes do *como* · SR4 contextualizar teoria · SR5 sugerir próximos passos · SR6 validar como revisor hostil · SR7 oferecer alternativas · SR8 citar fontes/metodologias.
- **Response structure (6 passos → FSM/gates):** Step1 VALIDAÇÃO de premissas · Step2 FUNDAMENTAÇÃO teórica · Step3 METODOLOGIA · Step4 EXECUÇÃO guiada · Step5 VALIDAÇÃO de resultados · Step6 EXTENSÃO.

### 1.6 `context_layer` (7) + `context_method`
- **Layers:** CL1 domínio técnico · CL2 complexidade · CL3 restrições físicas · CL4 normas (ISO/ASTM/ASME/ABNT/DIN) · CL5 dados/ferramentas · CL6 otimização · CL7 tempo/custo.
- **Métodos:** `5W1H_context_capture`, `Ishikawa_causa_efeito`, `M3_Macro_Meso_Micro`.

### 1.7 `output_standard` + `knowledge_source`
- Padrões: formato hierárquico, unidades SI, precisão+incerteza, validação VVV.
- Fontes: journals peer-reviewed (2024–2026), conferências, standards técnicos.

---

## 2) JSON2 (Kaizen) → integração sobre JSON1

JSON2 **não substitui** JSON1; **opera sobre** ele. As 8 partes mapeiam como *camadas operacionais*:

| Parte JSON2 | Opera sobre (JSON1) | Efeito no modelo |
|---|---|---|
| **P1 Filosofia** (8 princípios) | `kdi_agent.principle` | add `principle_catalog` (P1–P8) |
| **P2 KDI** | `kdi_agent` | formaliza KDI como objeto-canônico (**é o JSON1**) |
| **P3 Métodos Numéricos** | `numerical_method` (4→11) | add MPM/SPH/DEM/Peridynamics + **decision-tree** → DMN `method_selection` |
| **P4 Domínios** (10 + `relevance_check`) | `domain_catalog`/`runtime_domain` | add `relevance_check` + **M³**; 10 = seed |
| **P5 Mandatos** (M1–M7) | todo o schema | add `mandate` (Open Source First, SSOT, VVV, WAL, governança) |
| **P6 Fluxo** (F1–F7) | `response_step` (6) | **refina em FSM F1–F7** com gates G1–G5 → BPMN (`02-...`) |
| **P7 Métricas** (D1–D10) | `output_standard` (VVV) | add `quality_metric` mensurável; cobertura 75–90% (D1) |
| **P8 WAL** | `knowledge_source` + novo | add `wal_log` (5W1H por ação + map_index + metrics + patches) |

### 2.1 Tabelas novas introduzidas pelo JSON2
`principle_catalog`, `mandate`, `workflow_phase` (com `prev_phase`, `next_phase`, `gate`, `fail_target`), `quality_metric` (`target`, `gate`), `m3_decomposition`, `wal_log`, e as DMNs `dmn_relevance_check`, `dmn_method_selection`, `dmn_vvv_acceptance`.

---

## 3) Modelo entidade-relacionamento (grafo de integração)

```
kdi_agent ─┬─ has_identity ──> Identity ──has_base_domain──> domain_catalog(SEED, 10)
           ├─ has_capability ─> capability ─uses_method─> numerical_method ─decision_tree─> DMN method_selection
           │                                 ─uses_tool───> tool
           ├─ has_socratic_rule (8) ───────────────────────> gate F2/F5
           ├─ has_response_step (6) ── refined_by(P6) ─────> workflow_phase (F1–F7) ─gate─> G1..G5
           ├─ has_context_layer (7) ── capture_method ─────> 5W1H / Ishikawa / M3
           ├─ has_output_standard ── measured_by(P7) ──────> quality_metric (D1–D10)
           ├─ updates_from ──> knowledge_source ─ persisted_as(P8) ──> wal_log
           └─ governed_by(P5) ──> mandate (M1–M7)

runtime_domain ─derived_from─> research_context (5W1H+Ishikawa) ─relevance_check(G1)─> team_instance (1 agent/domain)
```

**Aresta-chave da integração JSON1↔JSON2:** `workflow_phase(F*, JSON2).gate` referencia `response_step(Step*, JSON1)` — o fluxo Kaizen **refina** a estrutura de resposta do KDI; e `quality_metric(JSON2).measures` → `output_standard(JSON1)`. Nada é duplicado; JSON2 adiciona *operacionalidade* sobre a *identidade* de JSON1.

---

## 4) Descoberta por query (demonstração: "via query consigo obter tudo")

### Q1 — Métodos/ferramentas que competem para um domínio
```sql
SELECT d.name AS domain, c.capability, m.method, t.tool
FROM domain_catalog d
JOIN capability c ON c.id = d.typical_capability
LEFT JOIN capability_method cm ON cm.capability = c.id
LEFT JOIN numerical_method m ON m.id = cm.method_id
LEFT JOIN method_tool mt ON mt.method = m.id
LEFT JOIN tool t ON t.id = mt.tool
WHERE d.name = 'Mecânica dos Fluidos';
-- → CFD, Navier-Stokes; FVM/SPH; OpenFOAM/SU2...
```

### Q2 — Cardinalidade runtime do time (variável, NÃO fixa)
```sql
SELECT d.name, rc.relevance_score, rc.justification
FROM research_context r
JOIN runtime_domain rd ON rd.context_id = r.id
JOIN domain_catalog d ON d.id = rd.domain_id
JOIN dmn_relevance_check rc ON rc.domain_id = d.id
WHERE r.id = :ctx AND rc.applicable = true;
-- count(*) → multi-instance do BPMN. Pode ser 3, 7, 12...
```

### Q3 — Caminho metodológico F1–F7 com gates e fail-loops
```sql
SELECT phase, gate, fail_target, pass_target, mandate_ref
FROM workflow_phase WHERE domain_id = :d ORDER BY ord;
-- F1(5W1H)→F2(relevance G1)→F3(M³)→F4(method DMN)→F5(exec)→
-- [G2 Verif]→[G3 Valid]→[G4 Validada]→F6(correlação meso)→F7(WAL)→[G5 cobertura 75-90%]
```

### Q4 — Métricas D* que validam padrões de saída
```sql
SELECT q.metric_id, q.name, q.target, o.standard
FROM quality_metric q JOIN output_standard o ON q.measures = o.id;
-- D1 cobertura 75-90%, D3 convergência<1%... cada um amarra um gate.
```

### Q5 — Trace de auditoria (WAL, Parte 8)
```sql
SELECT phase, actor_agent, action_5w1h, map_index, quality_metrics, patch
FROM wal_log WHERE run_id = :run ORDER BY ts;
```

### Q6 — Grafo (Cypher): domínio→método→ferramenta→gate→métrica
```cypher
MATCH (d:Domain)-[:has_capability]->(c:Capability)-[:uses_method]->(m:Method),
      (m)-[:selected_via]->(g:Gate {id:'G_metodo'}),
      (c)-[:measured_by]->(q:Metric)
WHERE d.is_seed = true
RETURN d.name, c.name, collect(m.name), collect(q.metric_id);
```

---

## 5) Impacto no design do produto (correções a aplicar)

1. **`domain_catalog` vira seed + derivação runtime** — nunca enumeração fechada. Orquestrador (KDI) lê `research_context`, roda `5W1H+Ishikawa`, propõe `runtime_domain`, e o `relevance_check` (G1/DMN) decide o time. Cardinalidade = variável.
2. **KDI + 5W1H + Ishikawa + M³ = estágios explícitos** no BPMN/DMN:
   - F1 = captura (5W1H + Ishikawa + 7 context_layers) → `research_context`
   - F2 = derivação de domínios (KDI seed + relevância) → `runtime_domain`
   - F3 = decomposição M³ por domínio
3. **Gates rigorosos com `fail_target`**: G2→F5, G3→F4, G4→recompor team (F2), G5→expandir domínios (F2). Loop Kaizen nunca volta ao início.
4. **Mandato no-hardcode satisfeito**: domínios, métodos, regras, gates, métricas, roles vivem como **linhas de DB / DMN / objetos**; código = motor fino.

---

## 6) Pendências (quando o classificador MCP recuperar)

- [ ] Carregar este modelo no `mcp__graph-engine` (grafo `bioeolica`) — nós: KDI/Domain/Capability/Method/Tool/Rule/Step/Layer/Gate/Metric/Mandate/Phase/WAL; arestas conforme §3.
- [ ] Executar Q1–Q6 contra o grafo e validar a descoberta relacional.
- [ ] Espelhar schema em PostgreSQL + pgvector (SSOT de produção).
