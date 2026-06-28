"""
lab_db.models — ORM do laboratório computacional (SSOT relacional).

Materializa JSON1 (DOC1 — KDI v3.0-omnibus) + JSON2 (DOC2-KAIZEN — Engine Omnibus)
como dados consultáveis. O código é apenas o motor fino (schema + relações);
todos os valores de domínio (domínios, métodos, regras, gates, métricas) vivem
como LINHAS no DB, satisfazendo o mandato no-hardcoded.

Engine: SQLite (desenvolvimento). Trocável por PostgreSQL+pgvector em produção
sem mudar o schema.

Tabelas runtime (multi-agente + FSM) em lab_db.seed_fsm: runtime_domain,
team_instance, agent_run, agent_provider, agent_output, method_kernel, gate_verdict,
timeout_watchdog, gate_timeout, dmn_rule.
Este ORM as espelha para manter o princípio 1:1 (DDL sqlite3 em build.py/seed_fsm.py
== ORM aqui). Migrar um exige migrar o outro.

NOTA: sqlalchemy é uma dependência OPCIONAL — não exigida para build/run do DB
(sqlite3 stdlib basta). Desativado reportMissingImports neste arquivo porque o
sandbox offline não tem PyPI.
"""
# pyright: reportMissingImports=false
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Table,
    Text,
    create_engine,
)
from sqlalchemy.orm import DeclarativeBase, relationship, sessionmaker


class Base(DeclarativeBase):
    pass


# ───────────────────────── Tabelas de associação (N:N) ─────────────────────────
capability_method = Table(
    "capability_method",
    Base.metadata,
    Column("capability_id", String, ForeignKey("capability.id"), primary_key=True),
    Column("method_id", String, ForeignKey("numerical_method.id"), primary_key=True),
)

method_tool = Table(
    "method_tool",
    Base.metadata,
    Column("method_id", String, ForeignKey("numerical_method.id"), primary_key=True),
    Column("tool_id", String, ForeignKey("tool.id"), primary_key=True),
)

domain_capability = Table(
    "domain_capability",
    Base.metadata,
    Column("domain_id", String, ForeignKey("domain_catalog.id"), primary_key=True),
    Column("capability_id", String, ForeignKey("capability.id"), primary_key=True),
)


# ───────────────────────── JSON1 — Identidade KDI ─────────────────────────
class KdiAgent(Base):
    __tablename__ = "kdi_agent"
    id = Column(String, primary_key=True)
    version = Column(String, nullable=False)
    role = Column(String)
    expertise_level = Column(String)
    methodology = Column(String)
    principle = Column(String)
    philosophy = Column(String)


class DomainCatalog(Base):
    """Catálogo de domínios. is_seed=true marca os 10 da base de construção.
    Domínios runtime (derivados do contexto) são inseridos com is_seed=false."""
    __tablename__ = "domain_catalog"
    id = Column(String, primary_key=True)
    name = Column(String, nullable=False, unique=True)
    is_seed = Column(Boolean, default=True, nullable=False)
    capabilities = relationship("Capability", secondary=domain_capability, back_populates="domains")


class Capability(Base):
    __tablename__ = "capability"
    id = Column(String, primary_key=True)
    name = Column(String, nullable=False)
    description = Column(Text)
    domains = relationship("DomainCatalog", secondary=domain_capability, back_populates="capabilities")
    methods = relationship("NumericalMethod", secondary=capability_method, back_populates="capabilities")
    tools = relationship("Tool", secondary=method_tool, back_populates="capabilities")


class NumericalMethod(Base):
    """Folhas da decision-tree (Parte 3). regime/continuity/mesh alimentam o DMN."""
    __tablename__ = "numerical_method"
    id = Column(String, primary_key=True)
    regime = Column(String)
    continuity = Column(String)
    mesh = Column(String)
    source = Column(String)  # "JSON1" | "JSON2"
    capabilities = relationship("Capability", secondary=capability_method, back_populates="methods")


class Tool(Base):
    __tablename__ = "tool"
    id = Column(String, primary_key=True)
    name = Column(String, nullable=False)
    license = Column(String)  # "commercial" | "open-source" (mandate M1)
    capabilities = relationship("Capability", secondary=method_tool, back_populates="tools")


class SocraticRule(Base):
    __tablename__ = "socratic_rule"
    id = Column(String, primary_key=True)
    rule = Column(Text, nullable=False)


class ResponseStep(Base):
    """Estrutura de resposta (6 passos) — micro-fluxo interno do agente em F3–F4."""
    __tablename__ = "response_step"
    id = Column(String, primary_key=True)
    ord = Column(Integer, nullable=False)
    name = Column(String, nullable=False)


class ContextLayer(Base):
    __tablename__ = "context_layer"
    id = Column(String, primary_key=True)
    name = Column(String, nullable=False)


class ContextMethod(Base):
    __tablename__ = "context_method"
    id = Column(String, primary_key=True)
    name = Column(String, nullable=False)
    purpose = Column(String)


class OutputStandard(Base):
    __tablename__ = "output_standard"
    id = Column(String, primary_key=True)
    name = Column(String, nullable=False)


class KnowledgeSource(Base):
    __tablename__ = "knowledge_source"
    id = Column(String, primary_key=True)
    name = Column(String, nullable=False)


# ───────────────────────── JSON2 — Camada operacional Kaizen ─────────────────────────
class Mandate(Base):
    """Mandatos M1–M7 (Parte 5) — restrições de governança/aceitação."""
    __tablename__ = "mandate"
    id = Column(String, primary_key=True)
    name = Column(String, nullable=False)
    description = Column(Text, nullable=False)


class WorkflowPhase(Base):
    """Estágios F1–F7 (Parte 6) com gate e fail_target — o BPMN como dados."""
    __tablename__ = "workflow_phase"
    id = Column(String, primary_key=True)
    ord = Column(Integer, nullable=False)
    name = Column(String, nullable=False)
    gate = Column(String)
    gate_type = Column(String)
    dmn_source = Column(String)
    fail_target = Column(String)
    mandate_ref = Column(String)


class QualityMetric(Base):
    """Métricas D1–D10 (Parte 7)."""
    __tablename__ = "quality_metric"
    id = Column(String, primary_key=True)
    name = Column(String, nullable=False)
    target = Column(String, nullable=False)
    gate = Column(String)


class WalLog(Base):
    """WAL (Parte 8) — append-only, rastreabilidade por execução."""
    __tablename__ = "wal_log"
    id = Column(Integer, primary_key=True, autoincrement=True)
    run_id = Column(String, nullable=False, index=True)
    ts = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    phase = Column(String, nullable=False)
    actor_agent = Column(String)
    action_5w1h = Column(Text)
    map_index = Column(String)
    quality_metrics = Column(Text)
    patch = Column(Text)


# ───────────────────────── EXTENSÕES MULTI-AGENTE / DMN / WATCHDOG ─────────────────────────
# Espelho ORM 1:1 de lab_db/extensions.py (DDL sqlite3). Manter sincronizado.
class RuntimeDomain(Base):
    """Domínio derivado do contexto (KDI + 5W1H + Ishikawa + M3). is_seed=0 em domain_catalog."""
    __tablename__ = "runtime_domain"
    id = Column(String, primary_key=True)
    name = Column(String, nullable=False, unique=True)
    derived_from = Column(String)
    relevance_score = Column(Float)
    team_instance_id = Column(String)
    created_at = Column(String, nullable=False)


class TeamInstance(Base):
    """Instância de time — cardinalidade N decidida em G1 (variável, context-dependent)."""
    __tablename__ = "team_instance"
    id = Column(String, primary_key=True)
    run_id = Column(String, nullable=False)
    cardinality = Column(Integer, nullable=False)
    created_at = Column(String, nullable=False)
    status = Column(String, nullable=False, default="composing")


class AgentRun(Base):
    """Execução de um agente especialista (1 por domínio relevante)."""
    __tablename__ = "agent_run"
    id = Column(String, primary_key=True)
    team_instance_id = Column(String, ForeignKey("team_instance.id"), nullable=False)
    domain_id = Column(String, nullable=False)
    capability_id = Column(String)
    method_id = Column(String)
    status = Column(String, nullable=False, default="pending")
    started_at = Column(String)
    finished_at = Column(String)
    result_ref = Column(String)
    provider_id = Column(String, ForeignKey("agent_provider.id"))  # NULL → is_default=1


class AgentProvider(Base):
    """Config de provider LLM como DADO (mandato no-hardcoded). kind é mapeado pelo
    executor (valor-de-coluna → callable); api_key_env guarda o NOME da env-var."""
    __tablename__ = "agent_provider"
    id = Column(String, primary_key=True)
    kind = Column(String, nullable=False)            # stub | http (extensível)
    model = Column(String)
    base_url = Column(String)
    api_key_env = Column(String)                     # nome da env-var (nunca a chave)
    timeout_s = Column(Integer, nullable=False)
    is_default = Column(Integer, nullable=False, default=0)
    note = Column(String)


class AgentOutput(Base):
    """Payload do agente — casa do 'resultado real'. Append-style (nunca UPDATE/DELETE)."""
    __tablename__ = "agent_output"
    id = Column(Integer, primary_key=True, autoincrement=True)
    agent_id = Column(String, ForeignKey("agent_run.id"), nullable=False)
    payload = Column(Text)
    created_at = Column(String, nullable=False)


class MethodKernel(Base):
    """Ponte method_id→kernel executável (mandato no-hardcoded). `kernel` é valor-de-coluna
    resolvido pelo registry em numeric_exec._KERNELS (valor-de-coluna→callable). Linha ausente
    → numeric_exec cai no fallback provider (LLM/stub)."""
    __tablename__ = "method_kernel"
    method_id = Column(String, ForeignKey("numerical_method.id"), primary_key=True)
    kernel = Column(String, nullable=False)
    params_json = Column(Text)
    note = Column(String)


class DmnDecision(Base):
    """DMN materializado — substitui strings soltas em workflow_phase.dmn_source.
    Cada linha = uma regra de decisão (relevance/method_selection/vvv_acceptance)."""
    __tablename__ = "dmn_decision"
    id = Column(String, primary_key=True)
    dmn_source = Column(String, nullable=False)
    input_key = Column(String, nullable=False)
    output_value = Column(String, nullable=False)
    rule = Column(String)


class GateEvent(Base):
    """Evento de gate auditável — a FSM transiciona por estes registros."""
    __tablename__ = "gate_event"
    id = Column(Integer, primary_key=True, autoincrement=True)
    ts = Column(String, nullable=False)
    run_id = Column(String, nullable=False)
    gate_id = Column(String, nullable=False)
    phase_id = Column(String)
    verdict = Column(String, nullable=False)  # PASS | FAIL | PENDING | TIMEOUT
    decided_by = Column(String)
    detail = Column(String)


class TimeoutWatchdog(Base):
    """Watchdog de gate — se nenhum PASS/FAIL antes do deadline -> GateEvent TIMEOUT."""
    __tablename__ = "timeout_watchdog"
    id = Column(Integer, primary_key=True, autoincrement=True)
    run_id = Column(String, nullable=False)
    gate_id = Column(String, nullable=False)
    phase_id = Column(String)
    armed_at = Column(String, nullable=False)
    deadline = Column(String, nullable=False)
    tripped = Column(Integer, nullable=False, default=0)
    trip_reason = Column(String)


Index("idx_agent_run_team", AgentRun.team_instance_id)
Index("idx_gate_event_run", GateEvent.run_id, GateEvent.gate_id)
Index("idx_watchdog_run", TimeoutWatchdog.run_id, TimeoutWatchdog.tripped)


# ───────────────────────── Engine / session factory ─────────────────────────
def make_engine(url: str = "sqlite:///lab.db"):
    return create_engine(url, future=True)


def make_session(engine):
    return sessionmaker(bind=engine, future=True)()


def init_schema(engine):
    Base.metadata.create_all(engine)
