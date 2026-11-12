#!/usr/bin/env bash
# Falla (exit != 0) si el arnés inmutable, su referencia o la fixture emparejada cambian.
#   - compara cada fichero con tests/HARNESS.sha256
#   - detecta ficheros añadidos o eliminados en tests/reference/
set -euo pipefail
cd "$(dirname "$0")/.."

if ! sha256sum --check --strict --quiet tests/HARNESS.sha256; then
  echo "ERROR: el arnés inmutable o su referencia han cambiado." >&2
  exit 1
fi

registered=$(grep -oE 'tests/reference/.*$' tests/HARNESS.sha256 | sort)
present=$(find tests/reference -type f | sort)
if [ "$registered" != "$present" ]; then
  echo "ERROR: se han añadido o eliminado ficheros en tests/reference/:" >&2
  diff <(echo "$registered") <(echo "$present") >&2 || true
  exit 1
fi

echo "OK: arnés y referencia intactos ($(wc -l < tests/HARNESS.sha256) ficheros verificados)."
