#!/usr/bin/env bash
set -euo pipefail
cd ..
cur_dir=$(pwd)

echo 'Linting code...'
echo 'Testing directory: '"$cur_dir"

echo '-------------'
echo 'Black:'
black .
echo '-------------'
echo 'mypy:'
mypy --explicit-package-bases .
echo '-------------'
echo 'Ruff:'
python -m ruff check . --fix
