#!/bin/sh
# Fetches the local models of the live setup as GGUF files into
# containers/live/models/, which the llama services mount read-only. The
# services themselves never reach the internet.
#
#   sh containers/live/fetch-models.sh                 # the default model
#   sh containers/live/fetch-models.sh qwen3.5-9b ...  # the models named
#   sh containers/live/fetch-models.sh all             # every model below
#   sh containers/live/fetch-models.sh list            # names and sizes
#
# Each file is checked against its size at the hub: a complete one is
# skipped, a partial one resumed. The names are the presets of
# llama/presets-gpu.ini and llama/presets-cpu.ini, and a model's file is
# named after its preset, so the routers list it under that name.

set -eu

here=$(cd "$(dirname "$0")" && pwd)
dir="${MODELS_DIR:-$here/models}"
hub=https://huggingface.co

# name | repository | file at the hub | approximate size
MODELS='
qwen3-4b-2507|unsloth/Qwen3-4B-Instruct-2507-GGUF|Qwen3-4B-Instruct-2507-Q4_K_M.gguf|2.5 GB
qwen3.5-4b|unsloth/Qwen3.5-4B-GGUF|Qwen3.5-4B-Q4_K_M.gguf|2.7 GB
gemma-4-e4b|unsloth/gemma-4-E4B-it-GGUF|gemma-4-E4B-it-Q4_K_M.gguf|5.0 GB
ministral-3-8b|mistralai/Ministral-3-8B-Instruct-2512-GGUF|Ministral-3-8B-Instruct-2512-Q4_K_M.gguf|5.2 GB
qwen3.5-9b|unsloth/Qwen3.5-9B-GGUF|Qwen3.5-9B-Q4_K_M.gguf|5.7 GB
gemma-4-12b|google/gemma-4-12b-it-qat-q4_0-gguf|gemma-4-12b-it-qat-q4_0.gguf|7.0 GB
qwen3.6-35b-a3b|unsloth/Qwen3.6-35B-A3B-GGUF|Qwen3.6-35B-A3B-UD-Q4_K_M.gguf|22.1 GB
'
DEFAULT=qwen3-4b-2507

say() { printf 'fetch-models: %s\n' "$1" >&2; }

# The size of a file at the hub. Content-Length is the redirect's, the
# file's own is in x-linked-size.
hub_size() {
    curl -sIL "$1" | grep -i '^x-linked-size:' | tail -1 | tr -d '\r' | awk '{print $2}'
}

fetch() {
    line=$(printf '%s\n' "$MODELS" | grep "^$1|") || { say "no model named $1"; exit 2; }
    repo=$(printf '%s' "$line" | cut -d'|' -f2)
    file=$(printf '%s' "$line" | cut -d'|' -f3)
    url="$hub/$repo/resolve/main/$file"
    target="$dir/$1.gguf"
    expected=$(hub_size "$url")
    if [ -z "$expected" ]; then
        say "no size at the hub for $repo/$file"
        exit 1
    fi
    if [ -f "$target" ]; then
        actual=$(stat -c%s "$target")
        if [ "$actual" = "$expected" ]; then
            say "$1 is there"
            return 0
        fi
        if [ "$actual" -gt "$expected" ]; then
            rm -f "$target"
        fi
    fi
    say "fetching $1 from $repo"
    # The hub redirects to a CDN, so -L. -C - resumes a partial file.
    curl -fsSL -C - -o "$target" "$url"
    actual=$(stat -c%s "$target")
    if [ "$actual" != "$expected" ]; then
        say "$1 has $actual bytes, the hub says $expected"
        exit 1
    fi
    if [ "$(head -c4 "$target")" != "GGUF" ]; then
        say "$1 is not a GGUF file"
        exit 1
    fi
}

mkdir -p "$dir"
if [ $# -eq 0 ]; then
    set -- "$DEFAULT"
fi
for name in "$@"; do
    case "$name" in
        list)
            printf '%s\n' "$MODELS" | awk -F'|' 'NF { printf "%-18s %-8s %s\n", $1, $4, $2 }'
            ;;
        all)
            for each in $(printf '%s\n' "$MODELS" | awk -F'|' 'NF { print $1 }'); do
                fetch "$each"
            done
            ;;
        *)
            fetch "$name"
            ;;
    esac
done
