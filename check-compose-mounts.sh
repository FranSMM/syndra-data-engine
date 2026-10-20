#!/bin/bash
#
# Checks that every host path a compose file bind-mounts exists and has the expected type.
# Docker turns a missing source into an empty directory, and the container fails with a misleading exit 127.
#
# Usage:
#   ./check-compose-mounts.sh                       # the local development stack
#   ./check-compose-mounts.sh some-compose.yml      # any other file
#
# infra/docker-compose.prod.yml is not checked by default: its paths resolve on the VPS.
set -uo pipefail

FILES=("$@")
if [ ${#FILES[@]} -eq 0 ]; then
    FILES=("docker-compose.yml")
fi

PROBLEMS_FILE=$(mktemp)
trap 'rm -f "$PROBLEMS_FILE"' EXIT

for compose in "${FILES[@]}"; do
    if [ ! -f "$compose" ]; then
        echo "  [SKIP] $compose no existe"
        continue
    fi

    echo "== $compose"
    # Relative paths resolve against the compose file's directory, as Docker does.
    base=$(cd "$(dirname "$compose")" && pwd)

    # Only ./ and ../ entries are host paths; named volumes are created on demand.
    grep -oE '^[[:space:]]*-[[:space:]]+\.{1,2}/[^:]+:[^:]+' "$compose" \
    | sed -E 's/^[[:space:]]*-[[:space:]]+//' \
    | while IFS= read -r entry; do
        src="${entry%%:*}"
        dst="${entry#*:}"
        abs="$base/$src"

        if [ ! -e "$abs" ]; then
            echo "  [FALTA]  $src"
            echo "           docker creara un directorio vacio aqui y el contenedor no arrancara"
            echo "$compose:$src" >> "$PROBLEMS_FILE"
        elif [ -d "$abs" ] && [[ "$(basename "$dst")" == ?*.* ]]; then
            # An extension in the destination name suggests a file; only a hint, so it warns.
            echo "  [OJO]    $src es un directorio y se monta en $dst"
        else
            echo "  [ok]     $src"
        fi
    done
done

if [ -s "$PROBLEMS_FILE" ]; then
    echo
    echo "$(wc -l < "$PROBLEMS_FILE") ruta(s) inexistente(s). Arreglalas antes de levantar nada."
    exit 1
fi

echo
echo "Todas las rutas montadas existen."
