#!/usr/bin/env bash
set -euo pipefail

# Portfolio Universal Local Validation Contract
# Repository: ha-smart-oil-gauge
# Gate: 96% component statement coverage

echo "==> [1/6] Verifying toolchain and interpreter"
command -v uv >/dev/null 2>&1 || { echo "Error: uv is required but not installed"; exit 1; }
python_version=$(uv run --locked python --version)
echo "Using $python_version"

echo "==> [2/6] Verifying dependency lockfile freshness"
uv lock --check

echo "==> [3/6] Running pre-commit hooks on all files"
uv run --locked pre-commit run --all-files

echo "==> [4/6] Running Ruff lint and formatting checks"
uv run --locked ruff check .
uv run --locked ruff format --check .

echo "==> [5/6] Running Python test suite (>=96% coverage gate)"
uv run --locked pytest

echo "==> [6/6] Verifying clean git working tree"
git diff --exit-code

echo "==> Local validation passed successfully!"
