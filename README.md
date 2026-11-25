# OU Quick Settings

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
- **Bluetooth** – power on/off, per-device Connect / Disconnect submenu
- **LAN** – connect/disconnect Ethernet, activate/deactivate saved connections
- **Sound** – mute/unmute, volume presets, choose the default output sink

Right-click the tray icon for **Open panel** / a **Theme** submenu /
**Quit**. Theme defaults to **Follow OU Setting** (the day/night switch in
OU Setting / XFCE); you can force **Dark** or **Light** there.
`Esc` or the ✕ button closes the panel. Clicking the tray icon again toggles it.

State refreshes every 3 seconds and immediately after each action.

## Opacity

The popup background opacity is controlled from **OU Setting > Opacity >
Quick settings opacity**. The value is stored at `/quick-settings/opacity` on
the `xfce4-panel` xfconf channel and is applied automatically without a restart.

## Run

```sh
./launch.sh
```

It is also installed to `~/.config/autostart/`, so it starts on login.

## Requirements

GTK 3 (`python3-gi`), XFCE notification area plugin, `nmcli`, `gdbus`,
`bluetoothctl`, `pactl`.
