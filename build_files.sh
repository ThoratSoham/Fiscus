#!/bin/bash

echo "BUILD START"

# Vercel's build image ships python3.12 for the Python runtime; fall back to
# plain `python3` if it is not available.
if command -v python3.12 >/dev/null 2>&1; then
    PYTHON_BIN=python3.12
else
    PYTHON_BIN=python3
fi
echo "Using: $PYTHON_BIN"

$PYTHON_BIN -m pip install --upgrade pip
$PYTHON_BIN -m pip install -r requirements.txt
$PYTHON_BIN manage.py collectstatic --noinput --clear

echo "BUILD END"
