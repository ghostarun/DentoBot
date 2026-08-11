#!/usr/bin/env bash
set -euo pipefail

repository_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
backend_python="${DENTOBOT_BACKEND_PYTHON:-}"

cd "${repository_root}"

git diff --check

python3 - <<'PY'
import ast
from pathlib import Path

root = Path.cwd()
python_files = sorted(
    path for path in root.rglob("*.py")
    if not any(part in {".git", ".venv", "build", "dist"} for part in path.parts)
)
for path in python_files:
    ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
print(f"Python AST: {len(python_files)} files passed")
PY

python3 - <<'PY'
from pathlib import Path
import xml.etree.ElementTree as ET

ui_files = sorted(Path.cwd().rglob("*.ui"))
for path in ui_files:
    ET.parse(path)
print(f"Qt UI XML: {len(ui_files)} files passed")
PY

python3 - <<'PY'
from pathlib import Path

markdown_files = sorted(Path("docs").glob("*.md"))
for path in markdown_files:
    fences = sum(
        1 for line in path.read_text(encoding="utf-8").splitlines()
        if line.lstrip().startswith("```")
    )
    if fences % 2:
        raise SystemExit(f"Unbalanced Markdown fences: {path}")
print(f"Markdown fences: {len(markdown_files)} files passed")
PY

if [[ -n "${backend_python}" ]]; then
  PIP_NO_CACHE_DIR=1 "${backend_python}" -m pip check
  "${backend_python}" -m pytest -p no:cacheprovider -q \
    "${repository_root}/Inference/tests"
  "${backend_python}" -m pytest -p no:cacheprovider -q \
    "${repository_root}/Testing/test_platform_contract.py"
else
  echo "Backend tests: skipped (set DENTOBOT_BACKEND_PYTHON)"
fi

echo "Close-day static checks passed."
