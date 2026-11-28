#!/bin/sh
# Build an architecture-independent Debian package for OU Quick Settings.
set -eu
VERSION="${1:-0.1.0}"
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
OUT="$ROOT/dist"
STAGE="$ROOT/build/ou-quick-settings_${VERSION}_all"
PKGDIR=/usr/share/ou-quick-settings

rm -rf "$STAGE"
mkdir -p "$STAGE/DEBIAN" "$STAGE$PKGDIR" \
         "$STAGE/usr/share/applications" "$STAGE/etc/xdg/autostart" \
         "$STAGE/usr/share/doc/ou-quick-settings"

install -m 0755 "$ROOT/control_panel.py" "$STAGE$PKGDIR/control_panel.py"
install -m 0755 "$ROOT/launch.sh" "$STAGE$PKGDIR/launch.sh"

cat > "$STAGE/usr/share/applications/ou-quick-settings.desktop" <<DESKTOP
[Desktop Entry]
Type=Application
Name=OU Quick Settings
GenericName=Quick Settings
Comment=Android-style tray panel for LAN, Wi-Fi, Bluetooth and Sound
Exec=$PKGDIR/launch.sh
Icon=preferences-system-symbolic
Terminal=false
NoDisplay=false
Categories=Utility;Settings;
DESKTOP
cp "$STAGE/usr/share/applications/ou-quick-settings.desktop" \
   "$STAGE/etc/xdg/autostart/ou-quick-settings.desktop"

cat > "$STAGE/DEBIAN/control" <<CONTROL
Package: ou-quick-settings
Version: $VERSION
Section: x11
Priority: optional
Architecture: all
Depends: python3, python3-gi, python3-cairo, gir1.2-gtk-3.0, network-manager, bluez, pulseaudio-utils, libglib2.0-bin, xfce4-panel
Maintainer: PatrickNoFilter <trayhartred@gmail.com>
Description: Android-style quick settings tray panel for XFCE
 A small GTK3 system-tray control panel for Wi-Fi, Ethernet, Bluetooth and
 sound, with a live clock, inline month calendar and adjustable opacity.
CONTROL

cat > "$STAGE/usr/share/doc/ou-quick-settings/copyright" <<'COPYRIGHT'
Format: https://www.debian.org/doc/packaging-manuals/copyright-format/1.0/
Upstream-Name: ou-quick-settings
Source: https://github.com/PatrickNoFilter/ou-quick-settings

Files: *
Copyright: 2026 PatrickNoFilter
License: other
 See the upstream repository for licensing terms.
COPYRIGHT

mkdir -p "$OUT"
dpkg-deb --build --root-owner-group "$STAGE" \
  "$OUT/ou-quick-settings_${VERSION}_all.deb"
echo "Built: $OUT/ou-quick-settings_${VERSION}_all.deb"
