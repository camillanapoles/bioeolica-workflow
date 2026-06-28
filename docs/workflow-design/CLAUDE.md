[raiz](../../CLAUDE.md) > [docs](../) > **workflow-design**

# docs/workflow-design — Artefatos de Design do Engine Omnibus v3.0

## Responsabilidade do Módulo

Quatro artefatos de design que decompõem o engine **Omnibus v3.0-unified** em visões complementares: a topologia do KDI (JSON1), a orquestração BPMN multi-agente, o modelo relacional SSOT (JSON1+JSON2), e a máquina de estados rigorosa (estados, gates, triggers, transições). São a **especificação-fonte** que `lab_db` materializa como dados consultáveis.

**Fontes de verdade**: `DOC1-KDI_MECH-ELECTRO-MATERIALS.md` (JSON1), `DOC2-KAIZEN.md` (JSON2, 8 partes), `INSTRUCTIONS.md` (mandato de governança).

## Entrada e Estrutura

Não há execução — são documentos Markdown com Mermaid embutido (renderizáveis em qualquer viewer MD) e, no `02`, XML BPMN 2.0 importável em `c8ctl`/Camunda/bpmn.io.

| Artefato | Visão | Conteúdo-chave |
|----------|-------|----------------|
| `01-mindmap-kdi.md` | Topologia hierárquica do KDI | Mermaid mindmap de metadados, identity, core_capabilities, socratic_behavior, context_engine, output_standards |
| `02-bpmn-orchestration.md` | Orquestração multi-agente | Swimlanes (Orquestrador/Team/VVV/Memória) + gates G1-G5 + tabela metodológica + XML BPMN 2.0 |
| `03-relational-model-json1-json2.md` | Schema SSOT + descoberta por query | Retificação "domínios context-dependent"; tabelas, FKs, queries exemplificativas |
| `04-fsm-gates-triggers.md` | FSM rigorosa | Estados F1-F7 (trigger/atividade/contrato-saída/condition), gates G0-G5, triggers BPMN, transições explícitas |

## Interfaces Externas

- **Consumidores**: `lab_db/build.py` (implementa o schema de `03`), `lab_db/graph.py` (projeta as transições de `04`).
- **BPMN XML** (`02`, seção C): salvar como `orchestration.bpmn` e importar via `c8ctl` (profile `local`) ou bpmn.io/Camunda. *Nota do autor*: o comando `/bpmn` não estava exposto na sessão de criação — o XML manual é o artefato equivalente.

## Dependências e Configuração-Chave

- Sem dependências de runtime. Mermaid e XML BPMN são formatos-texto.
- Alinhamento mandatório: todo estado/gate/métrica/mandato nomeado aqui **deve** ter linha correspondente em `lab.db` (verificar via Q3/Q4/Q5 em `lab_db/build.py`).

## Modelo de Dados (implícito)

O artefato `03` é o **schema SSOT** documentado (18 tabelas, cadeia domínio→capability→method→tool, N:N via tabelas de associação). `04` formaliza gates com `tipo`, `pergunta`, `fonte DMN`, `PASS→` e `FAIL→`. A regra de loop Kaizen: **cada FAIL retorna à fase anterior adequada, nunca ao início**; falhas repetidas > threshold viram incidente Camunda (escalonamento), não loop infinito.

## Testes e Qualidade

- Sem testes automatizados (documentos). A validação é por **consistência**: rodar `lab_db.build` Q3-Q5 e conferir que estados/gates/métricas/mandatos batem com `04`.

## FAQ

- **Por que FSM e BPMN separados?** — `02` é a visão de orquestração (swimlanes, paralelismo multi-instance, join), `04` é a visão de máquina de estados (contratos de dados, conditions formais). Complementares, não redundantes.
- **Gates G0-G5 vs F1-F7?** — F* são **estados** (atividades); G* são **decisões** (gateways XOR/DMN/completeness) entre transições. `G_método` é um gate DMN dentro de F3.
- **M3 e VVV?** — Mandato M3 exige Verificação (G2) + Validação (G3) + Validada (G4) — gate triplo em sequência, não opcional.

## Arquivos Relevantes

| Arquivo | Papel |
|---------|-------|
| `01-mindmap-kdi.md` | Topologia do JSON1 |
| `02-bpmn-orchestration.md` | Orquestração + XML BPMN |
| `03-relational-model-json1-json2.md` | Schema SSOT + retificação context-dependent |
| `04-fsm-gates-triggers.md` | FSM estados/gates/triggers/transições |

## Changelog

| Data | Ação |
|------|------|
| 2026-06-28T02:32Z | CLAUDE.md do módulo criado pelo arquiteto (inicialização). |
