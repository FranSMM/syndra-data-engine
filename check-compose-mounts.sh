#!/bin/bash
#
# Verify that every host path a compose file bind-mounts actually exists, and is
# the same kind of thing (file or directory) as its destination implies.
#
# This exists because of a specific, expensive failure. Docker does not refuse a
# bind mount whose source is missing: it silently creates an empty *directory*
# there, then fails to mount that directory onto a file. The container never
# starts and reports exit code 127, which means "command not found" and sends
# you looking for a broken entrypoint. The real message is buried in
# `docker inspect -f '{{.State.Error}}'`, which nobody reads first.
#
# The local development stack sat dead for four weeks that way.
#
# Usage:
#   ./check-compose-mounts.sh                       # the local development stack
#   ./check-compose-mounts.sh some-compose.yml      # any other file
#
# Deliberately does NOT check infra/docker-compose.prod.yml by default. That
# file's relative paths resolve against the deploy directory on the VPS, where
# deploy.sh has placed them and where streamlit-secrets.toml lives. Checking it
# from a laptop reports a missing secret that is not missing, and a checker that
# cries wolf gets ignored, which is worse than not having one.
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
    # Relative paths in a compose file resolve against the file's own directory,
    # not against the shell's working directory. Getting that wrong here would
    # make the checker disagree with docker for the most interesting cases.
    base=$(cd "$(dirname "$compose")" && pwd)

    # Only ./ and ../ entries are host paths. A leading name with no slash is a
    # named volume, which docker creates on demand and which cannot fail this way.
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
            # An extension on the destination's *basename* suggests it wants a
            # file. Checking the whole path would flag /root/.cache/huggingface,
            # where the dot belongs to a directory name. Not conclusive either
            # way, so it warns rather than failing.
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
