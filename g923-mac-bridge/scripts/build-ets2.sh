#!/bin/sh
set -eu
g923_project=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
# The same source build supplies both accepted game integrations. Toolchains
# come from PATH or ZIG / G923_RUSTC / G923_MINGW; the Wine export source is explicit.
exec python3 "$g923_project/scripts/build-release-components.py" "$@"
