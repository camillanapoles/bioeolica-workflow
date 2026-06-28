"""tests/__main__.py — orquestrador de testes (Pytest-FREE, zero-PyPI).

Roda todos os módulos test_*.py via `python3 -m tests.test_X` em subprocessos
isolados (cada um cria seu DB temporário próprio no import-time). Agrega o
resultado e retorna exit code não-zero se qualquer teste falhar.

Uso:
    python3 -m tests                  # roda tudo
    python3 -m tests test_fsm         # roda um módulo específico

Honra o mandato zero-PyPI: apenas stdlib (subprocess, sys, pathlib, time).
"""
from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

# Budget por módulo. Falha estrutural (ImportError/syntax) → exit != 0 dentro deste prazo.
_MODULE_TIMEOUT_S = 120


def _discover() -> list[str]:
    """Lista módulos test_*.py em ordem determinística."""
    tests_dir = REPO / "tests"
    return sorted(p.stem for p in tests_dir.glob("test_*.py"))


def _run_module(mod: str) -> tuple[bool, str]:
    """Executa um módulo via `python -m tests.MOD` e captura saída.

    Inclui tail de stderr na falha — sem isto, ImportError/syntax/exit()
    ficam invisíveis (run_all só captura exceções de teste, não falhas
    estruturais que abortam antes do run_all).
    """
    proc = subprocess.run(
        [sys.executable, "-m", f"tests.{mod}"],
        cwd=str(REPO),
        capture_output=True,
        text=True,
        timeout=_MODULE_TIMEOUT_S,
    )
    tail = (proc.stdout or "").splitlines()[-6:]
    ok = proc.returncode == 0
    if not ok and (proc.stderr or "").strip():
        # Mostra o traceback/erro estrutural que stdout não revela.
        tail += ["--- stderr ---"] + (proc.stderr or "").splitlines()[-8:]
    return ok, "\n".join(tail)


def main(argv: list[str]) -> int:
    mods = argv[1:] if len(argv) > 1 else _discover()
    if not mods:
        print("Nenhum módulo test_*.py encontrado em tests/")
        return 2

    print("=" * 70)
    print(f"RUNNING {len(mods)} test module(s): {', '.join(mods)}")
    print("=" * 70)

    failures: list[str] = []
    for mod in mods:
        print(f"\n-- {mod} ".ljust(70, "-"))
        t0 = time.perf_counter()
        try:
            ok, tail = _run_module(mod)
        except subprocess.TimeoutExpired:
            print(f"  TIMEOUT ({_MODULE_TIMEOUT_S}s) em {mod}")
            failures.append(mod)
            continue
        dt = time.perf_counter() - t0
        print(tail)
        marker = "PASS" if ok else "FAIL"
        print(f"  [{marker}] {mod} ({dt:.2f}s)")
        if not ok:
            failures.append(mod)

    print("\n" + "=" * 70)
    total = len(mods)
    passed = total - len(failures)
    print(f"RESULT: {passed}/{total} modules passed")
    if failures:
        print(f"FAILED modules: {', '.join(failures)}")
    print("=" * 70)
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
