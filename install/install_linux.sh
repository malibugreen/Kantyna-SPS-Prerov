#!/usr/bin/env bash

# Zajištění UTF-8
export LC_ALL=C.UTF-8
export LANG=C.UTF-8

echo "========================================================"
echo "  Instalace potřebných knihoven pro Raspberry Pi / Linux"
echo "========================================================"
echo

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# 1. Zajištění systémových balíčků (zejména python3-tk pro grafické rozhraní)
echo "[1/3] Kontrola systémových závislostí (Tkinter a pip)..."
if command -v apt-get >/dev/null 2>&1; then
    sudo apt-get update -y
    sudo apt-get install -y python3-tk python3-pip python3-pil python3-pil.imagetk
else
    echo "Upozornění: apt-get nenalezen, přeskakuji instalaci systémových balíčků."
fi

echo
echo "[2/3] Instalace Python balíčků přes pip..."

# Raspberry Pi OS (Debian 12 Bookworm) chrání systémové prostředí (PEP 668),
# proto zkoušíme standardní pip, a v případě potřeby použijeme --break-system-packages.
if python3 -m pip install -r "$SCRIPT_DIR/requirements.txt" 2>/dev/null; then
    echo "Instalace balíčků proběhla v pořádku."
else
    echo "Používám přepínač --break-system-packages pro novější Raspberry Pi OS..."
    python3 -m pip install -r "$SCRIPT_DIR/requirements.txt" --break-system-packages
fi

echo
echo "========================================================"
echo "  [HOTOVO] Knihovny pro Raspberry Pi byly nainstalovány!"
echo "========================================================"
echo "Aplikaci můžete spustit příkazem:"
echo "  python3 kiosk_app.py"
echo "nebo:"
echo "  python3 cashier_app.py"
echo
echo "Klikněte jakékoliv tlačítko pro dokončení..."
read -n 1 -s -r
echo
