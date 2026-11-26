# OU Quick Settings

**Version:** 0.0.1

Android-style quick settings panel that lives in the XFCE system tray on OU OS.

## What it does

A tray icon sits in the notification area. Left-click it to pop up a panel
with a live clock (HH:MM:SS) + date, four tiles and a volume slider:

| Tile | Action | Backend |
|------|--------|---------|
| Wi-Fi | enable/disable radio, shows active connection | `nmcli radio wifi` |
| LAN | connect/disconnect Ethernet, shows IPv4 address | `nmcli device` |
| Bluetooth | power adapter on/off, shows connected device count | BlueZ D-Bus (`gdbus`) |
| Sound | mute/unmute, volume slider | `pactl` |

Right-click any tile for its detail menu:

- **Wi-Fi** – turn the radio on/off, pick a network from the scanned list to connect
- **Bluetooth** – power on/off, **Search Devices** to scan for nearby devices
  (with Connect / Pair / Disconnect actions), per-device Connect / Disconnect submenu
- **LAN** – connect/disconnect Ethernet, activate/deactivate saved connections
- **Sound** – mute/unmute, volume presets, choose the default output sink

Right-click the tray icon for **Open panel** / a **Theme** submenu /
**Quit**. Theme defaults to **Follow OU Setting** (the day/night switch in
OU Setting / XFCE); you can force **Dark** or **Light** there.
`Esc`, the ✕ button, or clicking anywhere outside the panel closes it.
Clicking the tray icon again toggles it.

Left-click the clock or date to show/hide a month calendar above the tiles.
Click it again to close; `Esc` closes the calendar first, then the panel.

State refreshes every 3 seconds and immediately after each action.

## Opacity

The popup background opacity is controlled from **OU Setting > Opacity >
Quick settings opacity**. The value is stored at `/quick-settings/opacity` on
the `xfce4-panel` xfconf channel and is applied automatically without a restart.

## Installed location in OU OS

In the OU OS live ISOs the application is installed at
`/opt/ou-control-panel/` and the launcher in this directory points to
`/opt/ou-control-panel/launch.sh`.

## Run

```sh
./launch.sh
```

It is also installed to `~/.config/autostart/`, so it starts on login.

## Requirements

GTK 3 (`python3-gi`), XFCE notification area plugin, `nmcli`, `gdbus`,
`bluetoothctl`, `pactl`.
