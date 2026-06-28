"""
lab_db.build — carrega JSON1 (DOC1) + JSON2 (DOC2-Kaizen) no DB integrado e
executa as queries Q1–Q6 da descoberta relacional.

Engine: sqlite3 (biblioteca padrão — zero dependências externas), para rodar em
ambientes sem acesso ao PyPI. O schema espelha o ORM SQLAlchemy em lab_db/models.py
(mesmas tabelas/colunas/FKs), então a migração para SQLAlchemy + PostgreSQL é 1:1.

Uso:  python3 -m lab_db.build
"""
from __future__ import annotations

import os
import sqlite3

# DDL + seed das 3 DMNs e tabelas runtime (FSM data-driven). seed_fsm é folha (não
# importa deste módulo) → sem ciclo; import relativo p/ resolução Pyright no pacote.
from . import seed_fsm

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "lab.db")
URL = f"sqlite:///{DB_PATH}"  # compat com referência ORM

# ═══════════════════════ DDL (espelha lab_db/models.py) ═══════════════════════
DDL = """
PRAGMA foreign_keys = ON;

CREATE TABLE kdi_agent (
    id TEXT PRIMARY KEY, version TEXT NOT NULL, role TEXT, expertise_level TEXT,
    methodology TEXT, principle TEXT, philosophy TEXT);

CREATE TABLE domain_catalog (
    id TEXT PRIMARY KEY, name TEXT NOT NULL UNIQUE, is_seed INTEGER NOT NULL DEFAULT 1);

CREATE TABLE capability (
    id TEXT PRIMARY KEY, name TEXT NOT NULL, description TEXT);

CREATE TABLE numerical_method (
    id TEXT PRIMARY KEY, regime TEXT, continuity TEXT, mesh TEXT, source TEXT);

CREATE TABLE tool (
    id TEXT PRIMARY KEY, name TEXT NOT NULL, license TEXT);

CREATE TABLE capability_method (
    capability_id TEXT REFERENCES capability(id),
    method_id TEXT REFERENCES numerical_method(id),
    PRIMARY KEY (capability_id, method_id));

CREATE TABLE method_tool (
    method_id TEXT REFERENCES numerical_method(id),
    tool_id TEXT REFERENCES tool(id),
    PRIMARY KEY (method_id, tool_id));

CREATE TABLE domain_capability (
    domain_id TEXT REFERENCES domain_catalog(id),
    capability_id TEXT REFERENCES capability(id),
    PRIMARY KEY (domain_id, capability_id));

CREATE TABLE socratic_rule (id TEXT PRIMARY KEY, rule TEXT NOT NULL);
CREATE TABLE response_step (id TEXT PRIMARY KEY, ord INTEGER NOT NULL, name TEXT NOT NULL);
CREATE TABLE context_layer (id TEXT PRIMARY KEY, name TEXT NOT NULL);
CREATE TABLE context_method (id TEXT PRIMARY KEY, name TEXT NOT NULL, purpose TEXT);
CREATE TABLE output_standard (id TEXT PRIMARY KEY, name TEXT NOT NULL);
CREATE TABLE knowledge_source (id TEXT PRIMARY KEY, name TEXT NOT NULL);

CREATE TABLE mandate (id TEXT PRIMARY KEY, name TEXT NOT NULL, description TEXT NOT NULL);

CREATE TABLE workflow_phase (
    id TEXT PRIMARY KEY, ord INTEGER NOT NULL, name TEXT NOT NULL,
    gate TEXT, gate_type TEXT, dmn_source TEXT, fail_target TEXT, mandate_ref TEXT);

CREATE TABLE quality_metric (
    id TEXT PRIMARY KEY, name TEXT NOT NULL, target TEXT NOT NULL, gate TEXT);

CREATE TABLE wal_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT, run_id TEXT NOT NULL,
    ts TEXT NOT NULL, phase TEXT NOT NULL, actor_agent TEXT,
    action_5w1h TEXT, map_index TEXT, quality_metrics TEXT, patch TEXT);
"""


# ═══════════════════════ DADOS JSON1 (DOC1 — KDI) ═══════════════════════
JSON1_AGENT = dict(
    id="mech-electro-materials-scientist", version="3.0-omnibus",
    role="Engenheiro Cientista Multidisciplinar", expertise_level="SOTA 2025-2026",
    methodology="Computacional-first · Analitico-validado · Experimental-correlacionado",
    principle="socratic-context-first", philosophy="teach-to-fish-never-limit-quantity",
)

SEED_DOMAINS = [
    ("D01", "Mecanica", "structural_analysis"),
    ("D02", "Eletrotecnica", "energy_systems"),
    ("D03", "Materiais", "materials_science"),
    ("D04", "Analise_Computacional", "computational_analysis"),
    ("D05", "Mecanica_dos_Fluidos", "fluid_dynamics"),
    ("D06", "Mecanica_dos_Solidos", "structural_analysis"),
    ("D07", "Elementos_Finitos_FEM", "computational_analysis"),
    ("D08", "Analise_de_Tensoes_Esforcos", "structural_analysis"),
    ("D09", "Dinamica_de_Cargas", "structural_analysis"),
    ("D10", "Energia_Sistemas_Energeticos", "energy_systems"),
]

CAPABILITIES = [
    ("computational_analysis", "Análise Computacional", "FEM/FVM/.../PINNs + ferramentas"),
    ("fluid_dynamics", "Mecânica dos Fluidos", "CFD, turbulência, multifásico"),
    ("materials_science", "Ciência dos Materiais", "modelos constitutivos"),
    ("structural_analysis", "Análise Estrutural", "tensões, cargas, fadiga"),
    ("energy_systems", "Sistemas Energéticos", "exergética, ciclos, multi-objetivo"),
]

METHODS = {
    "FEM":  ("pequena deformação", "solido", "requer malha", "JSON1"),
    "FVM":  ("volumes finitos", "fluido", "estruturada", "JSON1"),
    "FDM":  ("diferenças finitas", "fluido/solido", "estruturada", "JSON1"),
    "BEM":  ("elementos de contorno", "solido", "contorno", "JSON1"),
    "IGA":  ("isogeométrico", "solido", "NURBS", "JSON1"),
    "SPH":  ("sem malha", "livre-livre", "kernel", "JSON2"),
    "DEM":  ("granular/descontinuo", "discreto", "particulas", "JSON2"),
    "ROM":  ("reduzido", "projecao", "POD", "JSON1"),
    "PINNs":("neural", "campo", "NN", "JSON1"),
    "MPM":  ("grande deformação", "particula-materia", "material point", "JSON2"),
    "Peridynamics": ("fratura/descontinuo", "sem malha", "bonds", "JSON2"),
}

CAP_METHOD = {
    "computational_analysis": ["FEM","FVM","FDM","BEM","IGA","SPH","DEM","ROM","PINNs","MPM","Peridynamics"],
    "fluid_dynamics": ["FVM","SPH","FDM"],
    "materials_science": ["FEM","MPM","Peridynamics"],
    "structural_analysis": ["FEM","BEM","IGA","MPM"],
    "energy_systems": ["FVM","FDM"],
}

TOOLS = {
    "ANSYS":"commercial","ABAQUS":"commercial","COMSOL":"commercial",
    "OpenFOAM":"open-source","CalculiX":"open-source","FEniCS":"open-source",
    "SU2":"open-source","Code_Aster":"open-source","ParaView":"open-source",
}
CAP_TOOL = {
    "computational_analysis": ["ANSYS","ABAQUS","COMSOL","OpenFOAM","CalculiX","FEniCS","ParaView"],
    "fluid_dynamics": ["OpenFOAM","SU2","ANSYS"],
    "structural_analysis": ["ABAQUS","CalculiX","Code_Aster"],
    "materials_science": ["ABAQUS","FEniCS"],
    "energy_systems": ["OpenFOAM","ANSYS"],
}

RULES = [
    ("SR1","Nunca dar resposta pronta"),("SR2","Nunca limitar quantidade"),
    ("SR3","Explicar o PORQUE antes do COMO"),("SR4","Contextualizar a teoria"),
    ("SR5","Sugerir próximos passos"),("SR6","Validar como revisor hostil"),
    ("SR7","Oferecer alternativas"),("SR8","Citar fontes/metodologias"),
]
STEPS = [
    ("Step1",1,"VALIDACAO de premissas"),("Step2",2,"FUNDAMENTACAO teorica"),
    ("Step3",3,"METODOLOGIA"),("Step4",4,"EXECUCAO guiada"),
    ("Step5",5,"VALIDACAO de resultados"),("Step6",6,"EXTENSAO/proximos passos"),
]
LAYERS = [
    ("CL1","dominio tecnico"),("CL2","complexidade"),("CL3","restricoes fisicas"),
    ("CL4","normas ISO/ASTM/ASME/ABNT/DIN"),("CL5","dados/ferramentas"),
    ("CL6","otimizacao"),("CL7","tempo/custo"),
]
CTX_METHODS = [
    ("5W1H","5W1H","captura de contexto (who/what/when/where/why/how + how much)"),
    ("Ishikawa","Ishikawa","diagrama causa-efeito"),
    ("M3","M3 Macro/Meso/Micro","decomposição em escalas"),
]
OUTPUTS = [
    ("OS_format","formato hierarquico"),("OS_units","unidades SI"),
    ("OS_precision","precisao + incerteza"),("OS_vvv","validacao VVV"),
]
SOURCES = [
    ("JOURNALS","peer-reviewed journals 2024-2026"),
    ("CONFERENCES","conference proceedings"),
    ("STANDARDS","technical standards"),
]

# ═══════════════════════ DADOS JSON2 (DOC2 — Kaizen) ═══════════════════════
MANDATES = [
    ("M1","Open Source First","Preferir solvers open-source (CalculiX, OpenFOAM, SU2...)."),
    ("M2","SSOT","Single Source of Truth — dado único, integrado."),
    ("M3","VVV","Verificação + Validação + Validada (gate triplo)."),
    ("M4","WAL","Work Activity Log — 5W1H por ação, append-only."),
    ("M5","Mapa Unico","Mapa Único integrado de artefatos."),
    ("M6","Rastreabilidade","Toda decisão rastreável a fonte/contexto."),
    ("M7","Governanca","Orquestrador KDI compõe time por domínio."),
]
# id, ord, nome, gate, gate_type, dmn_source, fail_target, mandate_ref
PHASES = [
    ("F1",1,"Captura de Contexto",   "G0","completeness",None,                   "F1","M4"),
    ("F2",2,"Derivacao de Dominios", "G1","XOR",         "dmn_relevance_check",  "F1","M7"),
    ("F3",3,"Decomposicao M3",       "G_metodo","DMN",   "dmn_method_selection", "F3","M1"),
    ("F4",4,"Execucao da Analise",   "G2","XOR",         "dmn_vvv_acceptance",   "F4","M3"),
    ("F5",5,"Correlacao Holistica",  "G3","XOR",         "dmn_vvv_acceptance",   "F3","M3"),
    ("F6",6,"Cobertura + Memoria",   "G5","XOR",         None,                   "F2","M7"),
    ("F7",7,"Entrega Validada",      None,None,          None,                   None,"M5"),
]
METRICS = [
    ("D1","Cobertura por relevancia","75-90%","G5"),
    ("D2","Completude 5W1H","100%","G0"),
    ("D3","Convergencia malha/tempo","<1%","G2"),
    ("D4","Erro vs benchmark","<5%","G3"),
    ("D5","Reprodutibilidade","bit-exact","G4"),
    ("D6","Fonte confiavel","peer-reviewed","G4"),
    ("D7","Integracao meso","sem conflitos","G5"),
    ("D8","WAL selado","append-only","F6"),
    ("D9","Mapa Unico atualizado","snapshot","F6"),
    ("D10","Latencia ingestao","< deadlines","F6"),
]


def connect():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn


def init_schema(conn):
    conn.executescript(DDL)
    conn.commit()


def seed_json1(conn):
    c = conn.cursor()
    c.execute("INSERT INTO kdi_agent (id,version,role,expertise_level,methodology,principle,philosophy) "
              "VALUES (:id,:version,:role,:expertise_level,:methodology,:principle,:philosophy)", JSON1_AGENT)
    c.executemany("INSERT INTO domain_catalog (id,name,is_seed) VALUES (?,?,1)", [(d[0], d[1]) for d in SEED_DOMAINS])
    c.executemany("INSERT INTO capability (id,name,description) VALUES (?,?,?)", CAPABILITIES)
    c.executemany("INSERT INTO numerical_method (id,regime,continuity,mesh,source) VALUES (?,?,?,?,?)",
                  [(k,)+v for k, v in METHODS.items()])
    c.executemany("INSERT INTO tool (id,name,license) VALUES (?,?,?)", [(k, k, v) for k, v in TOOLS.items()])
    c.executemany("INSERT INTO socratic_rule (id,rule) VALUES (?,?)", RULES)
    c.executemany("INSERT INTO response_step (id,ord,name) VALUES (?,?,?)", STEPS)
    c.executemany("INSERT INTO context_layer (id,name) VALUES (?,?)", LAYERS)
    c.executemany("INSERT INTO context_method (id,name,purpose) VALUES (?,?,?)", CTX_METHODS)
    c.executemany("INSERT INTO output_standard (id,name) VALUES (?,?)", OUTPUTS)
    c.executemany("INSERT INTO knowledge_source (id,name) VALUES (?,?)", SOURCES)

    # associações: domínio -> typical_capability
    c.executemany("INSERT INTO domain_capability (domain_id,capability_id) VALUES (?,?)",
                  [(d[0], d[2]) for d in SEED_DOMAINS])
    # capability -> methods
    cap_met = [(cap, m) for cap, ms in CAP_METHOD.items() for m in ms]
    c.executemany("INSERT INTO capability_method (capability_id,method_id) VALUES (?,?)", cap_met)
    # method -> tools (via capability para respeitar o domínio)
    met_tool = []
    for cap, ts in CAP_TOOL.items():
        for m in CAP_METHOD.get(cap, []):
            for t in ts:
                met_tool.append((m, t))
    # dedup
    c.executemany("INSERT OR IGNORE INTO method_tool (method_id,tool_id) VALUES (?,?)", list(set(met_tool)))
    conn.commit()


def seed_json2(conn):
    c = conn.cursor()
    c.executemany("INSERT INTO mandate (id,name,description) VALUES (?,?,?)", MANDATES)
    c.executemany("INSERT INTO workflow_phase (id,ord,name,gate,gate_type,dmn_source,fail_target,mandate_ref) "
                  "VALUES (?,?,?,?,?,?,?,?)", PHASES)
    c.executemany("INSERT INTO quality_metric (id,name,target,gate) VALUES (?,?,?,?)", METRICS)
    conn.commit()


def run_queries(conn):
    sep = "─" * 72
    print(f"\n{sep}\nQ1 — Métodos e ferramentas para 'Mecanica_dos_Fluidos'")
    rows = conn.execute("""
        SELECT c.id, GROUP_CONCAT(DISTINCT cm.method_id), GROUP_CONCAT(DISTINCT mt.tool_id)
        FROM domain_catalog d
        JOIN domain_capability dc ON dc.domain_id=d.id
        JOIN capability c ON c.id=dc.capability_id
        LEFT JOIN capability_method cm ON cm.capability_id=c.id
        LEFT JOIN method_tool mt ON mt.method_id=cm.method_id
        WHERE d.name='Mecanica_dos_Fluidos'
        GROUP BY c.id""").fetchall()
    for cid, methods, tools in rows:
        print(f"  capability={cid}  methods=[{methods}]  tools=[{tools}]")

    print(f"\n{sep}\nQ2 — Cardinalidade runtime do time (exemplo: 3 domínios relevantes)")
    relevant = ["Mecanica_dos_Fluidos", "Materiais", "Energia_Sistemas_Energeticos"]
    n = conn.execute("SELECT COUNT(*) FROM domain_catalog WHERE name IN (?,?,?)", relevant).fetchone()[0]
    print(f"  runtime_domain={relevant}  cardinality={n}  (multi-instance spawn)")
    print("  + runtime domain fora do seed seria inserido com is_seed=0 (context-dependent)")

    print(f"\n{sep}\nQ3 — Caminho metodológico F1-F7 (gate, fail_target, mandato)")
    for p in conn.execute("SELECT id,name,gate,fail_target,mandate_ref FROM workflow_phase ORDER BY ord"):
        print(f"  {p[0]} {p[1]:<24} gate={str(p[2]):<10} fail->{str(p[3]):<5} ({p[4]})")

    print(f"\n{sep}\nQ4 — Métricas D* e gates que validam")
    for m in conn.execute("SELECT id,name,target,gate FROM quality_metric ORDER BY id"):
        print(f"  {m[0]} {m[1]:<32} target={m[2]:<14} gate={m[3]}")

    print(f"\n{sep}\nQ5 — Mandatos M1-M7 (governança)")
    for m in conn.execute("SELECT id,name,description FROM mandate ORDER BY id"):
        print(f"  {m[0]} {m[1]:<18} {m[2][:60]}")

    print(f"\n{sep}\nQ6 — Métodos por origem (JSON1 vs JSON2 — integração)")
    for src in ("JSON1", "JSON2"):
        cnt = conn.execute("SELECT COUNT(*) FROM numerical_method WHERE source=?", (src,)).fetchone()[0]
        ids = [r[0] for r in conn.execute("SELECT id FROM numerical_method WHERE source=?", (src,))]
        print(f"  source={src}: {cnt} métodos  {ids}")

    print(f"\n{sep}\nTotais:")
    for t in ("domain_catalog","capability","numerical_method","tool","socratic_rule",
              "response_step","context_layer","mandate","workflow_phase","quality_metric"):
        n = conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
        print(f"  {t:<20} {n} linhas")


def main():
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)
    conn = connect()
    init_schema(conn)
    seed_json1(conn)
    seed_json2(conn)
    # FSM data-driven: tabelas aditivas + 3 DMNs materializadas como linhas (zero hardcoded).
    seed_fsm.init_fsm_schema(conn)
    seed_fsm.seed_dmns(conn)
    seed_fsm.seed_providers(conn)
    conn.execute("INSERT INTO wal_log (run_id,ts,phase,actor_agent,action_5w1h,map_index,quality_metrics,patch) "
                 "VALUES (?,?,?,?,?,?,?,?)",
                 ("RUN-DEMO-001", "2026-06-28T00:00:00Z", "F1", "orchestrator",
                  "captura 5W1H do enunciado", "MAP/CTX/001", "D2=100%", None))
    conn.commit()
    run_queries(conn)
    conn.close()
    print(f"\nDB criado: {DB_PATH}")


if __name__ == "__main__":
    main()
