#!/usr/bin/env bash
# scripts/verify.sh — gate de continuidade CCG (iron rule #6: testes são a底线).
# Roda lint + types + testes. Falha (exit != 0) se qualquer um falhar.
# Uso: bash scripts/verify.sh
set -euo pipefail

cd "$(dirname "$0")/.."

if [[ -f .venv/bin/activate ]]; then
  # shellcheck disable=SC1091
  source .venv/bin/activate
fi

echo "── 1/3 ruff ───────────────────────────────────────────"
ruff check lab_db/ tests/

echo "── 2/3 pyright ───────────────────────────────────────"
pyright lab_db/ tests/

echo "── 3/3 tests ─────────────────────────────────────────"
python3 -m tests

echo "── gitnexus status ───────────────────────────────────"
gitnexus status 2>/dev/null || echo "(gitnexus não disponível — skip)"

echo ""
echo "✅ verify.sh: TUDO PASSOU"
