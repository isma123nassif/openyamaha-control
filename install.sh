#!/bin/sh
# Instala el lanzador y el icono para el usuario actual (sin sudo).
#   ./install.sh               lanzador en el menú de aplicaciones
#   ./install.sh --autostart   además arranca minimizado en la bandeja al iniciar sesión
#   ./install.sh --uninstall   quita todo lo anterior
set -e
DIR=$(cd "$(dirname "$0")" && pwd)
APPS="$HOME/.local/share/applications"
ICONS="$HOME/.local/share/icons/hicolor/scalable/apps"
AUTOSTART="$HOME/.config/autostart"

if [ "$1" = "--uninstall" ]; then
    rm -f "$APPS/yamaha-control.desktop" "$ICONS/yamaha-control.svg" "$AUTOSTART/yamaha-control.desktop"
    echo "Desinstalado."
    exit 0
fi

python3 -c 'import PyQt6.QtSvgWidgets' 2>/dev/null || {
    echo "Falta PyQt6 (Arch: sudo pacman -S python-pyqt6 · Debian/Ubuntu: sudo apt install python3-pyqt6 python3-pyqt6.qtsvg · pip: pip install PyQt6)"
    exit 1
}

mkdir -p "$APPS" "$ICONS"
cp "$DIR/data/yamaha-control.svg" "$ICONS/"
desktop() {
    cat <<EOT
[Desktop Entry]
Type=Application
Name=Yamaha RX-V4A
GenericName=Control del receptor AV
Comment=Volumen, entradas, sonido y mando del Yamaha
Exec=python3 "$DIR/yamaha_control.py" $1
Icon=yamaha-control
Categories=AudioVideo;Audio;
Keywords=yamaha;musiccast;receptor;av;volumen;mando;
StartupWMClass=yamaha-control
EOT
}
desktop "" > "$APPS/yamaha-control.desktop"
if [ "$1" = "--autostart" ]; then
    mkdir -p "$AUTOSTART"
    desktop "--tray" > "$AUTOSTART/yamaha-control.desktop"
fi
command -v update-desktop-database >/dev/null && update-desktop-database "$APPS" 2>/dev/null || true
echo "Instalado. Búscalo como «Yamaha RX-V4A» en el menú de aplicaciones."
