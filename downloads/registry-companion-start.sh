#!/bin/sh
dir=$(CDPATH= cd -P "$(dirname "$0")" && pwd) || exit 2
if [ ! -f "$dir/registry_companion_launcher.py" ]; then
    echo "Extract all files from registry-companion-kit.zip into the same folder." >&2
    exit 2
fi
for python in python3 python; do
    if "$python" -I -c 'import sys; sys.exit(sys.version_info < (3, 11))' 2>/dev/null; then
        exec "$python" -I "$dir/registry_companion_launcher.py" "$0" "$@"
    fi
done
echo "Install Python 3.11 or later and put python3 or python on PATH, then reopen this launcher." >&2
exit 2
