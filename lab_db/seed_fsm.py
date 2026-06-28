"""
lab_db.seed_fsm — DDL aditiva + seed das 3 DMNs + tabelas runtime.

Fecha a Pendência #2 do doc 04 §7 ("Materializar as 3 DMNs ... sem literais em
código"): as regras de decisão são **linhas de DB** (tabela dmn_rule), interpretadas
genericamente por lab_db.dmn. Nenhuma string de domínio/método/métrica vive no engine.

Engine: sqlite3 (stdlib) — mesma filosofia zero-dependência de lab_db.build.
As regras abaixo são extraídas de:
  - DOC2 Parte 3 (decision-tree binária de método numérico + comparison_table)
  - DOC2 Parte 4 (relevance_check por domínio)
  - Mandato M3 (critérios VVV: Verificação / Validação / Validada)
  - DOC1/DOC2 (palavras-chave de cada domínio de engenharia)

Hit-policy: FIRST — a primeira regra cujo predicado satisfaça (ordenada por `ord`)
vence. Para relevância (múltiplas keywords), use evaluate_all() e conte acertos.
"""
from __future__ import annotations

# ═══════════════════════ DDL ADITIVA ═══════════════════════
DDL_FSM = """
-- Tabela unificada de regras de decisão (uma DMN = um decision_id).
-- operator ∈ {eq, in, lt, gt, between, keyword_match} — interpretado por lab_db.dmn.
-- scope: domain_id p/ regras de relevância (a qual domínio a keyword se aplica);
--         NULL p/ method/vvv (decisões não-dominais).
CREATE TABLE dmn_rule (
    decision_id  TEXT NOT NULL,    -- dmn_relevance_check | dmn_method_selection | dmn_vvv_acceptance
    ord          INTEGER NOT NULL, -- prioridade (menor = primeira)
    scope        TEXT,             -- domain_id ou NULL
    input_key    TEXT NOT NULL,    -- nome do campo de entrada esperado
    operator     TEXT NOT NULL,    -- eq | in | lt | gt | between | keyword_match
    input_value  TEXT NOT NULL,    -- valor de comparação (string; listas separadas por ',')
    output_key   TEXT NOT NULL,
    output_value TEXT NOT NULL,
    note         TEXT
);

-- Instância de workflow (uma por pesquisa submetida). Rastreabilidade M4/M6.
CREATE TABLE workflow_instance (
    run_id                TEXT PRIMARY KEY,
    started_at            TEXT NOT NULL,
    research_context_json TEXT NOT NULL,   -- 5W1H + Ishikawa + 7 layers
    status                TEXT NOT NULL,   -- RUNNING | PASS | FAIL | BLOCKED
    cardinality           INTEGER,         -- |runtime_domain applicable| (variável)
    coverage              REAL             -- fraction [0,1] coberta
);

-- Domínios derivados em runtime (F2). is_seed=1 → do catálogo base; 0 → proposto pelo contexto.
CREATE TABLE runtime_domain (
    run_id            TEXT NOT NULL REFERENCES workflow_instance(run_id),
    domain_id         TEXT NOT NULL,
    is_seed           INTEGER NOT NULL,
    relevance_score   REAL,
    applicable        INTEGER,             -- 1 inclui / 0 exclui (gate G1)
    justification     TEXT,
    method_id         TEXT,                -- selecionado em F3 (dmn_method_selection)
    team_instance_id  TEXT,                -- link ao time spawnado (M7)
    agent_run_id      TEXT,                -- link ao agente especialista executando o domínio
    PRIMARY KEY (run_id, domain_id)
);

-- Vereditos de gate por run (auditoria M6 — toda decisão é rastreável a regra).
CREATE TABLE gate_verdict (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id        TEXT NOT NULL REFERENCES workflow_instance(run_id),
    gate          TEXT NOT NULL,        -- G0 | G1 | G_metodo | G2 | G3 | G4 | G5
    phase         TEXT NOT NULL,        -- F1..F7
    verdict       TEXT NOT NULL,        -- PASS | FAIL
    dmn_decision  TEXT,                 -- qual decision_id decidiu (ou NULL p/ heurística)
    dmn_rule_ord  INTEGER,              -- qual regra (ord) disparou
    decided_by    TEXT,                 -- dmn | agent_run_id | orchestrator | watchdog
    detail        TEXT,
    ts            TEXT NOT NULL
);

-- Time multi-agente (cardinalidade N decidida em G1; M7 governa a composição).
CREATE TABLE team_instance (
    id           TEXT PRIMARY KEY,
    run_id       TEXT NOT NULL REFERENCES workflow_instance(run_id),
    cardinality  INTEGER NOT NULL,      -- N agentes (variável por pesquisa)
    status       TEXT NOT NULL DEFAULT 'composing',  -- composing|active|joined|failed
    created_at   TEXT NOT NULL
);

-- Execução de um agente especialista (1 por domínio relevante). Sujeito a watchdog.
CREATE TABLE agent_run (
    id            TEXT PRIMARY KEY,
    team_instance_id TEXT NOT NULL REFERENCES team_instance(id),
    run_id        TEXT NOT NULL REFERENCES workflow_instance(run_id),
    domain_id     TEXT NOT NULL,
    method_id     TEXT,
    status        TEXT NOT NULL DEFAULT 'pending',   -- pending|running|done|fail|timeout
    started_at    TEXT,
    finished_at   TEXT,
    result_ref    TEXT,                 -- path/índice do resultado (F4)
    provider_id   TEXT REFERENCES agent_provider(id)  -- resolvedor cai no is_default se NULL
);

-- Configuração de provider LLM como DADO (mandato no-hardcoded). kind é mapeado pelo
-- executor (valor-de-coluna -> callable), nunca literal em código. api_key_env guarda o
-- NOME da variável de ambiente (nunca a chave). is_default=1 em exatamente 1 linha.
CREATE TABLE agent_provider (
    id           TEXT PRIMARY KEY,
    kind         TEXT NOT NULL,        -- stub | http (extensível)
    model        TEXT,                 -- nome do modelo (NULL p/ stub)
    base_url     TEXT,                 -- endpoint chat-completions (NULL p/ stub)
    api_key_env  TEXT,                 -- nome da env-var (lida via os.environ no call)
    timeout_s    INTEGER NOT NULL,
    is_default   INTEGER NOT NULL DEFAULT 0,
    note         TEXT
);

-- Payload do agente (casa do "resultado real"). Append-style: nunca UPDATE/DELETE.
CREATE TABLE agent_output (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    agent_id    TEXT NOT NULL REFERENCES agent_run(id),
    payload     TEXT,
    created_at  TEXT NOT NULL
);

-- Watchdog de gate: sem verdict PASS/FAIL antes do deadline -> evento TIMEOUT.
CREATE TABLE timeout_watchdog (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id      TEXT NOT NULL REFERENCES workflow_instance(run_id),
    gate_id     TEXT NOT NULL,
    phase_id    TEXT,
    armed_at    TEXT NOT NULL,
    deadline    TEXT NOT NULL,          -- ISO-8601
    tripped     INTEGER NOT NULL DEFAULT 0,
    trip_reason TEXT
);

-- Thresholds de timeout POR GATE como dados (não literais em código). Lidos por fsm/crud.
CREATE TABLE gate_timeout (
    gate_id   TEXT PRIMARY KEY,
    phase_id  TEXT,
    seconds   INTEGER NOT NULL
);

-- Ponte método numérico -> kernel executável (mandato no-hardcoded). method_id é FK ao
-- catálogo JSON1; `kernel` é um valor-de-coluna mapeado pelo executor (numeric_exec) via
-- registry valor-de-coluna→callable (mesmo padrão de _PROVIDERS/_GATE_KIND) — nunca literal
-- de lógica. `params_json` carrega parâmetros do solver (grid, iters, BCs) como DADO.
-- Linha ausente → aquele method_id não tem kernel stdlib; executor cai no provider (LLM/stub).
CREATE TABLE method_kernel (
    method_id   TEXT PRIMARY KEY REFERENCES numerical_method(id),
    kernel      TEXT NOT NULL,    -- fdm_poisson | fdm_advection | ... (registry)
    params_json TEXT,              -- parâmetros numéricos como dado (JSON)
    note        TEXT
);

CREATE INDEX IF NOT EXISTS idx_agent_run_team ON agent_run(team_instance_id);
CREATE INDEX IF NOT EXISTS idx_gate_verdict_run ON gate_verdict(run_id, gate);
CREATE INDEX IF NOT EXISTS idx_watchdog_run ON timeout_watchdog(run_id, tripped);
"""

# Thresholds de watchdog como DADOS (mandato no-hardcoded). fsm.arm_watchdogs lê daqui.
GATE_TIMEOUTS = [
    ("G1", "F2", 300),     # relevance: 5 min
    ("G_metodo", "F3", 300),
    ("G2", "F4", 1800),    # verificação: 30 min
    ("G3", "F5", 3600),    # validação: 60 min
    ("G4", "F5", 1800),    # validada: 30 min
    ("G5", "F6", 600),     # cobertura: 10 min
]

# Providers LLM como DADOS (mandato no-hardcoded). agent_exec.resolve_provider lê daqui;
# is_default=1 marca o provider usado quando agent_run.provider_id é NULL. api_key_env é o
# NOME da env-var (a chave nunca entra no DB). Estes são SEED (config-base, extensível).
# (id, kind, model, base_url, api_key_env, timeout_s, is_default, note)
PROVIDERS = [
    ("prov_stub", "stub", None, None, None, 30, 1,
     "offline deterministic — pipeline GREEN sem rede/PyPI"),
    ("prov_http_local", "http", "", "http://localhost:11434/v1", "LLM_API_KEY", 60, 0,
     "stdlib urllib; auth via os.environ[api_key_env]"),
]

# Ponte método→kernel como DADO (mandato no-hardcoded). O `kernel` aqui é um valor-de-coluna
# resolvido pelo registry em numeric_exec._KERNELS (valor-de-coluna→callable) — adicionar um
# solver = 1 entrada no registry + 1 linha aqui, nunca literal em branch de código.
# params_json carrega a config numérica (grid, iters, BC) como dado; o kernel aplica defaults
# se faltar. A ausência de linha para um method_id → fallback ao provider (LLM/stub).
# (method_id, kernel, params_json, note)
METHOD_KERNELS = [
    ("FEM", "fdm_poisson",
     '{"equation":"poisson_1d","source":"x","n":60,"bc":"dirichlet_zero"}',
     "FEM stand-in: Poisson 1D por diferenças finitas + Thomas (analytic-checkable, stdlib math)"),
    ("FVM", "fdm_advection",
     '{"equation":"advection_1d","scheme":"upwind","n":80,"steps":200,"cfl":0.8}',
     "FVM stand-in: advecção 1D upwind (stdlib math)"),
]


# ═══════════════════════ SEED: dmn_relevance_check (Parte 4 + DOC1) ═══════════════════════
# scope = domain_id; keyword_match: se o research_context contiver a keyword → acerto.
# relevance_score = (#keywords casadas) / (#keywords do domínio). G1 PASS se score > 0.
# Domínios = SEED_DOMAINS de build.py (D01..D10); palavras-chave extraídas de DOC1/DOC2.
_RELEVANCE = {
    "D01": ["carga", "esforco", "tensao", "vibracao", "flambagem", "buckling", "estrutura", "mecanica"],
    "D02": ["motor", "gerador", "eletrico", "eletromagnetico", "bobina", "transformador", "rede eletrica"],
    "D03": ["material", "liga", "composto", "polimero", "corrosao", "microestrutura", "creep", "fadiga"],
    "D04": ["simulacao", "malha", "solver", "elementos finitos", "numerico", "computacional"],
    "D05": ["fluido", "escoamento", "cfd", "turbulencia", "aerodinamica", "pressao", "viscosidade"],
    "D06": ["solido", "deformacao", "elastico", "plastico", "tencao", "cisalhamento"],
    "D07": ["fem", "elementos finitos", "malha estruturada", "forma fraca"],
    "D08": ["tensao principal", "von mises", "concentracao de tensao", "tenacidade"],
    "D09": ["impacto", "dinamica", "carga dinamica", "sismico", "frequencia natural"],
    "D10": ["energia", "termodinamica", "eficiencia", "potencia", "ciclo rankine", "exergia"],
}


def _relevance_rows():
    """Gera linhas dmn_rule para dmn_relevance_check: 1 por (domínio, keyword)."""
    rows = []
    ord_ = 0
    for domain_id, kws in _RELEVANCE.items():
        for kw in kws:
            ord_ += 1
            rows.append((
                "dmn_relevance_check", ord_, domain_id,
                "context_text", "keyword_match", kw,
                "applicable", "1", f"domain {domain_id} keyword",
            ))
    return rows


# ═══════════════════════ SEED: dmn_method_selection (Parte 3 decision-tree) ═══════════════════════
# input_key = critério do problema; operator eq; primeira regra que casa (ord) vence.
# Critérios em ordem de prioridade da decision-tree binária de DOC2 Parte 3.
_METHOD_ROWS = [
    # (ord, input_key, input_value, output method_id, note)
    (10, "deformation",      "large",        "MPM",          "grande deformação → MPM ótimo"),
    (11, "fracture",         "yes",          "Peridynamics", "iniciação de trinca → Peridynamics"),
    (12, "fragmentation",    "yes",          "DEM",          "fragmentação → DEM"),
    (13, "material_type",    "granular",     "DEM",          "material granular → DEM"),
    (14, "fluid_free_surface", "yes",        "SPH",          "superfície livre / FSI → SPH"),
    (15, "regime",           "fluid_flow",   "FVM",          "escoamento de fluido → FVM"),
    (16, "high_strain_rate", "yes",          "MPM",          "alta taxa de deformação → MPM"),
    (17, "deformation",      "small",        "FEM",          "pequena deformação, sem trinca → FEM"),
    (18, "reduction",        "yes",          "ROM",          "redução de ordem requerida → ROM (POD)"),
    (19, "physics_informed", "yes",          "PINNs",       "neural informada por física → PINNs"),
]


def _method_rows():
    return [
        ("dmn_method_selection", o, None, k, "eq", v, "method_id", m, n)
        for (o, k, v, m, n) in _METHOD_ROWS
    ]


# ═══════════════════════ SEED: dmn_vvv_acceptance (Mandato M3 triplo) ═══════════════════════
# input_key="gate" roteia; o campo de critério carrega o valor medido.
# Para cada gate, a regra define o limiar de PASS (operator lt/eq); ausência de match → FAIL.
_VVV_ROWS = [
    # (ord, gate, criterion, operator, threshold, note)
    (20, "G2", "mesh_error",          "lt", "0.01",           "erro de malha < 1%"),
    (21, "G2", "time_residual",       "lt", "0.01",           "resíduo temporal < 1%"),
    (22, "G2", "conservation_ok",     "eq", "1",              "conservação verificada"),
    (23, "G3", "error_vs_benchmark",  "lt", "0.05",           "erro vs benchmark < 5%"),
    (24, "G3", "error_vs_experimental", "lt", "0.05",         "erro vs experimental < 5%"),
    (25, "G4", "source_quality",      "eq", "peer-reviewed",  "fonte peer-reviewed"),
    (26, "G4", "reproducible",        "eq", "1",              "reprodutível (bit-exact)"),
]


def _vvv_rows():
    """Roteamento por gate + critério de PASS. route regra seleciona o subconjunto."""
    rows = []
    seen_gates = set()
    for (o, gate, crit, op, thr, note) in _VVV_ROWS:
        if gate not in seen_gates:
            seen_gates.add(gate)
            rows.append((
                "dmn_vvv_acceptance", o, None,
                "gate", "eq", gate, "route", gate, f"roteia VVV gate {gate}",
            ))
        rows.append((
            "dmn_vvv_acceptance", o, None,
            crit, op, thr, "verdict", "PASS", note,
        ))
    return rows


# ═══════════════════════ API ═══════════════════════
def init_fsm_schema(conn):
    """Cria as tabelas aditivas (executado uma vez por build)."""
    conn.executescript(DDL_FSM)
    conn.commit()


def seed_dmns(conn):
    """Popula as 3 DMNs como linhas de dmn_rule + thresholds de gate_timeout. Idempotente."""
    c = conn.cursor()
    for decision_id in ("dmn_relevance_check", "dmn_method_selection", "dmn_vvv_acceptance"):
        c.execute("DELETE FROM dmn_rule WHERE decision_id=?", (decision_id,))
    c.executemany(
        "INSERT INTO dmn_rule (decision_id,ord,scope,input_key,operator,input_value,output_key,output_value,note) "
        "VALUES (?,?,?,?,?,?,?,?,?)",
        _relevance_rows() + _method_rows() + _vvv_rows(),
    )
    # thresholds de watchdog como dados (zero hardcoded)
    c.execute("DELETE FROM gate_timeout")
    c.executemany("INSERT INTO gate_timeout (gate_id,phase_id,seconds) VALUES (?,?,?)", GATE_TIMEOUTS)
    conn.commit()


def seed_providers(conn):
    """Popula agent_provider com os SEEDs de config (stub default + http local). Idempotente."""
    c = conn.cursor()
    c.execute("DELETE FROM agent_provider")
    c.executemany(
        "INSERT INTO agent_provider (id,kind,model,base_url,api_key_env,timeout_s,is_default,note) "
        "VALUES (?,?,?,?,?,?,?,?)",
        PROVIDERS,
    )
    conn.commit()


def seed_method_kernels(conn):
    """Popula method_kernel (ponte method_id→kernel executável como DADO). Idempotente.
    Linha ausente para um method_id → numeric_exec cai no fallback provider (LLM/stub)."""
    c = conn.cursor()
    c.execute("DELETE FROM method_kernel")
    c.executemany(
        "INSERT INTO method_kernel (method_id,kernel,params_json,note) VALUES (?,?,?,?)",
        METHOD_KERNELS,
    )
    conn.commit()


def arm_watchdogs(conn, run_id: str, gates=None):
    """Arma watchdogs p/ os gates de uma run, lendo deadlines de gate_timeout (dados).
    Retorna lista de (gate_id, deadline_iso). `gates=None` arma todos configurados.
    """
    from datetime import datetime, timezone, timedelta
    now = datetime.now(timezone.utc)
    if gates is None:
        rows = conn.execute("SELECT gate_id,phase_id,seconds FROM gate_timeout").fetchall()
    else:
        rows = conn.execute(
            "SELECT gate_id,phase_id,seconds FROM gate_timeout WHERE gate_id IN (%s)"
            % ",".join("?" * len(gates)), gates
        ).fetchall()
    armed = []
    for gate_id, phase_id, secs in rows:
        deadline = now + timedelta(seconds=secs)
        conn.execute(
            "INSERT INTO timeout_watchdog (run_id,gate_id,phase_id,armed_at,deadline,tripped) "
            "VALUES (?,?,?,?,?,0)",
            (run_id, gate_id, phase_id, now.isoformat(), deadline.isoformat()),
        )
        armed.append((gate_id, deadline.isoformat()))
    conn.commit()
    return armed


def trip_expired(conn, now_iso: str) -> list[tuple]:
    """Varre watchdogs armados: se deadline < now e não tripped -> tripa (TIMEOUT).
    Retorna [(run_id, gate_id, deadline)] dos tripados. Chamado pelo orquestrador/loop.
    """
    tripped = []
    for wid, run_id, gate_id, deadline in conn.execute(
        "SELECT id,run_id,gate_id,deadline FROM timeout_watchdog WHERE tripped=0 AND deadline<?",
        (now_iso,),
    ).fetchall():
        conn.execute(
            "UPDATE timeout_watchdog SET tripped=1, trip_reason='deadline_exceeded' WHERE id=?",
            (wid,),
        )
        tripped.append((run_id, gate_id, deadline))
    conn.commit()
    return tripped
