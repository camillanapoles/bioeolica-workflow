"""
lab_db.numeric_exec — ponte de EXECUÇÃO NUMÉRICA REAL (data-driven, stdlib).

Fecha o gap entre 'agente fala sobre simulação' e 'simulação computada': resolve o
kernel numérico mapeado ao method_id do agente (tabela method_kernel — DADO) e executa
um solver de verdade sobre o problema, produzindo **números reais** (não payload sintético).
Engine: `math` stdlib — zero PyPI, offline, determinístico (reprodutível bit-exact, mandato M3/M4).

Mandato ZERO-HARDCODED honrado pelo mesmíssimo padrão de `agent_exec._PROVIDERS` e
`bpmn_emit._GATE_KIND`: o kernel registry é um mapping **valor-de-coluna → callable** —
`kernel` é lido de `method_kernel.kernel` (linha de DB), nunca literal de branch. O termo
fonte da PDE também é dados (`params_json.source` → registry `_SOURCES`). Adicionar um
solver = 1 entrada no registry + 1 linha em method_kernel.

Integração: `agent_exec.run_one` chama `run_numeric` ANTES do provider; se houver kernel
mapeado e o solver retornar payload, grava agent_output numérico + status=done. Sem kernel
→ fallback ao provider (stub/http), preservando o caminho existente.
"""
from __future__ import annotations

import json
import math


# ═══════════════════════ KERNEL REGISTRY (valor-de-coluna → callable) ═══════════════════════
# Mesmo padrão estrutural de _PROVIDERS/_GATE_KIND: a chave é um valor de coluna lido do DB
# (method_kernel.kernel), não um literal de domínio. Adicionar solver = 1 entrada aqui + 1 linha.

def _fdm_poisson(p: dict) -> dict:
    """Resolve -u''(x) = f(x) em [0,1], u(0)=u(1)=0, por diferenças finitas centradas +
    resolução tridiagonal direta (algoritmo de Thomas, O(n)) — solução EXATA na malha discreta.
    Analytic-checkable: para f(x)=x → u(x)=x(1-x²)/6, máximo em x=1/√3 valendo 1/(9√3)≈0.06415.
    Stdlib `math` puro — sem numpy/scipy. Retorna campos numéricos reais + erro vs analítica."""
    n = int(p.get("n", 50))                       # pontos internos
    h = 1.0 / (n + 1)
    src_name = str(p.get("source", "x"))
    f = _SOURCES.get(src_name)
    if f is None:
        return {"error": f"source desconhecido: {src_name!r}"}
    # Sistema tridiagonal A·u = rhs: A diag=2, sub/super=-1; rhs_i = f(x_i)·h^2.
    rhs = [f((i + 1) * h) * h * h for i in range(n)]
    # Thomas: forward sweep (a=-1 sub, b=2 diag, c=-1 super)
    cp = [0.0] * n      # super-diagonal modificada
    dp = [0.0] * n      # rhs modificado
    for i in range(n):
        if i == 0:
            cp[i] = -1.0 / 2.0
            dp[i] = rhs[i] / 2.0
        else:
            m = 2.0 - (-1.0) * cp[i - 1]      # den = b - a*cp[i-1]
            cp[i] = -1.0 / m if i < n - 1 else 0.0
            dp[i] = (rhs[i] - (-1.0) * dp[i - 1]) / m
    # back-substitution
    u = [0.0] * n
    u[n - 1] = dp[n - 1]
    for i in range(n - 2, -1, -1):
        u[i] = dp[i] - cp[i] * u[i + 1]
    # resíduo da solução linear: max|A·u - rhs| (deve ser ≈0 — prova que o solver acertou)
    residual = 0.0
    for i in range(n):
        left = u[i - 1] if i > 0 else 0.0
        right = u[i + 1] if i < n - 1 else 0.0
        residual = max(residual, abs((2.0 * u[i] - left - right) - rhs[i]))
    field_max = max(u) if u else 0.0
    field_min = min(u) if u else 0.0
    mid = u[n // 2] if u else 0.0
    # validação vs solução analítica (apenas quando a fonte é a canônica "x")
    analytic_max = None
    error_vs_analytic = None
    if src_name == "x":
        analytic_max = 1.0 / (9.0 * math.sqrt(3.0))   # ≈ 0.06415
        error_vs_analytic = abs(field_max - analytic_max)
    # amostra da malha (10 pontos) p/ visualização/relatório
    step = max(1, n // 10)
    xs = [round((i + 1) * h, 6) for i in range(0, n, step)]
    us = [round(u[i], 8) for i in range(0, n, step)]
    return {
        "equation": "poisson_1d", "scheme": "fdm_central_thomas",
        "n": n, "h": round(h, 8),
        "field_max": round(field_max, 8), "field_min": round(field_min, 8),
        "field_at_mid": round(mid, 8),
        "linear_residual": round(residual, 12),
        "analytic_max": round(analytic_max, 8) if analytic_max is not None else None,
        "error_vs_analytic": round(error_vs_analytic, 8) if error_vs_analytic is not None else None,
        "grid_x": xs, "grid_u": us,
        "mode": "real-numeric-stdlib",
    }


def _fdm_advection(p: dict) -> dict:
    """Resolve u_t + a·u_x = 0 em [0,1] periódico, esquema upwind (1ª ordem), N passos no tempo.
    Stdlib `math` puro. Condição inicial: bump senoidal. Retorna estatísticas do campo final."""
    n = int(p.get("n", 80))
    steps = int(p.get("steps", 200))
    cfl = float(p.get("cfl", 0.8))
    a = 1.0                                  # velocidade de advecção (advecção linear canônica)
    h = 1.0 / n
    dt = cfl * h / a                         # CFL = a·dt/h
    u = [math.sin(2.0 * math.pi * i * h) + 1.0 for i in range(n)]  # IC: seno deslocado ∈ [0,2]
    for _ in range(steps):
        un = u[:]
        for i in range(n):
            upstream = u[i - 1]              # periódico (Python: índice -1 = último)
            un[i] = u[i] - (a * dt / h) * (u[i] - upstream)
        u = un
    field_max = max(u)
    field_min = min(u)
    mean = sum(u) / n
    return {
        "equation": "advection_1d", "scheme": "upwind",
        "n": n, "steps": steps, "cfl": cfl, "dt": round(dt, 8),
        "field_max": round(field_max, 8),
        "field_min": round(field_min, 8),
        "field_mean": round(mean, 8),
        "mass_drift": round(abs(mean - 1.0), 8),   # IC tem média 1; drift mede conservação
        "mode": "real-numeric-stdlib",
    }


# Termo fonte da PDE como DADO (registry). O nome vem de params_json.source — valor-de-coluna.
_SOURCES = {
    "x": lambda t: t,
    "const1": lambda _: 1.0,
    "quadratic": lambda t: t * t,
}

_KERNELS = {"fdm_poisson": _fdm_poisson, "fdm_advection": _fdm_advection}


# ═══════════════════════ RESOLUÇÃO + EXECUÇÃO ═══════════════════════
def resolve_kernel(conn, method_id: str | None) -> tuple[str, dict] | None:
    """Lê a ponte method_id→kernel do DB. Retorna (kernel_kind, params) ou None se não mapeado.
    Tudo do DB — zero hardcode de qual método usa qual kernel."""
    if not method_id:
        return None
    row = conn.execute(
        "SELECT kernel,params_json FROM method_kernel WHERE method_id=?", (method_id,)
    ).fetchone()
    if not row:
        return None
    try:
        params = json.loads(row[1]) if row[1] else {}
    except (json.JSONDecodeError, TypeError):
        params = {}
    return row[0], params


def run_numeric(conn, agent: dict) -> dict | None:
    """Executa o kernel mapeado ao method_id do agente. Retorna o payload numérico (dict) ou
    None se não houver kernel / solver desconhecido / erro. Fail-safe: nunca lança."""
    resolved = resolve_kernel(conn, agent.get("method_id"))
    if not resolved:
        return None
    kind, params = resolved
    fn = _KERNELS.get(kind)
    if fn is None:
        return None
    try:
        return fn(params)
    except (KeyError, ValueError, TypeError, ZeroDivisionError, OverflowError):
        return None
