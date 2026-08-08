#!/bin/bash
# Установка «Замыкание контуров DXF» на macOS и Linux.
#
#   curl -fsSL https://raw.githubusercontent.com/SKLFIR/dxf-close/main/install.sh | bash
#
# Кладёт программу в отдельное окружение и создаёт ярлык на рабочем столе.

set -euo pipefail

REPO='https://github.com/SKLFIR/dxf-close/archive/refs/heads/main.zip'

if [ "$(uname)" = "Darwin" ]; then
    APP_DIR="$HOME/Library/Application Support/dxf-close"
else
    APP_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/dxf-close"
fi
VENV="$APP_DIR/venv"

red()   { printf '\033[31m%s\033[0m\n' "$*"; }
green() { printf '\033[32m%s\033[0m\n' "$*"; }
gray()  { printf '\033[90m%s\033[0m\n' "$*"; }

echo
printf '\033[36m%s\033[0m\n' '=== Замыкание контуров DXF — установка ==='
echo

# --- 1. Python с поддержкой Tk ---------------------------------------------
find_python() {
    for cand in python3.13 python3.12 python3.11 python3.10 python3 python; do
        exe="$(command -v "$cand" 2>/dev/null || true)"
        [ -n "$exe" ] || continue
        if "$exe" -c 'import sys,tkinter; sys.exit(0 if sys.version_info[:2]>=(3,9) else 1)' 2>/dev/null; then
            echo "$exe"
            return 0
        fi
    done
    return 1
}

PYTHON="$(find_python || true)"

if [ -z "$PYTHON" ]; then
    echo "Подходящий Python не найден, пробую поставить…"
    if [ "$(uname)" = "Darwin" ]; then
        if command -v brew >/dev/null 2>&1; then
            brew install python-tk || brew install python3 || true
        else
            red 'Нужен Python 3.9+ с поддержкой Tk.'
            echo 'Поставьте одним из способов и повторите команду:'
            echo '  · Homebrew:  brew install python-tk'
            echo '  · python.org: https://www.python.org/downloads/macos/'
            exit 1
        fi
    else
        if command -v apt-get >/dev/null 2>&1; then
            sudo apt-get update && sudo apt-get install -y python3 python3-venv python3-tk
        elif command -v dnf >/dev/null 2>&1; then
            sudo dnf install -y python3 python3-tkinter
        else
            red 'Поставьте python3 с модулем tkinter и повторите команду.'
            exit 1
        fi
    fi
    PYTHON="$(find_python || true)"
    [ -n "$PYTHON" ] || { red 'Python с поддержкой Tk так и не найден.'; exit 1; }
fi
green "Python: $PYTHON"

# --- 2. окружение -----------------------------------------------------------
if [ -d "$VENV" ]; then
    echo 'Обновляю существующую установку…'
else
    echo 'Создаю окружение…'
    mkdir -p "$APP_DIR"
    "$PYTHON" -m venv "$VENV"
fi

echo 'Ставлю программу и зависимости…'
"$VENV/bin/python" -m pip install --upgrade pip --quiet
"$VENV/bin/python" -m pip install --upgrade --force-reinstall "$REPO" --quiet

# --- 3. ярлык ---------------------------------------------------------------
echo 'Создаю ярлык на рабочем столе…'
"$VENV/bin/python" -m dxf_close --install-shortcut

echo
green 'Готово. Ярлык «Замыкание контуров DXF» лежит на рабочем столе.'
gray  "Из терминала: \"$VENV/bin/dxf-close\" файл.dxf -r 0.2 --save"
echo
