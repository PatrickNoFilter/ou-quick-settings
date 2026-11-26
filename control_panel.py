#!/usr/bin/env python3
"""OU OS Quick Settings - Android-style tray control panel."""

import gi
import cairo
import os
import re
import shlex
import subprocess
import threading
from datetime import datetime

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, Gdk, GLib, Pango

APP_TITLE = "OU Quick Settings"
REFRESH_SECONDS = 3


def sh(command, timeout=4):
    try:
        proc = subprocess.run(command, shell=True, stdout=subprocess.PIPE,
                              stderr=subprocess.DEVNULL, text=True, timeout=timeout)
        return proc.stdout.strip()
    except Exception:
        return ""


def argv(args, timeout=4):
    try:
        proc = subprocess.run(args, stdout=subprocess.PIPE,
                              stderr=subprocess.DEVNULL, text=True, timeout=timeout)
        return proc.stdout.strip()
    except Exception:
        return ""


def device_of(kind):
    for line in sh("nmcli -t -f DEVICE,TYPE device status").splitlines():
        parts = line.split(":")
        if len(parts) >= 2 and parts[1] == kind and parts[0] != "lo":
            return parts[0]
    return ""


def wifi_enabled():
    return sh("nmcli -t -f WIFI radio").lower() == "enabled"


def wifi_detail():
    dev = device_of("wifi")
    if not dev:
        return "No adapter"
    conn = sh("nmcli -g GENERAL.CONNECTION device show " + shlex.quote(dev))
    return conn if conn and conn != "--" else "Not connected"


def set_wifi(enabled):
    sh("nmcli radio wifi " + ("on" if enabled else "off"))


def eth_device():
    return device_of("ethernet")


def eth_connected(dev=""):
    dev = dev or eth_device()
    return bool(dev) and "connected" in sh(
        "nmcli -g GENERAL.STATE device show " + shlex.quote(dev)).lower()


def eth_detail(dev="", connected=None):
    dev = dev or eth_device()
    if not dev:
        return "No adapter"
    if connected is None:
        connected = eth_connected(dev)
    if not connected:
        return "Disconnected"
    ip = sh("nmcli -g IP4.ADDRESS device show " + shlex.quote(dev)).split("\n")[0]
    return ip.split("/")[0] if ip and ip != "--" else "Connected"


def set_eth(enabled, dev=""):
    dev = dev or eth_device()
    if not dev:
        return
    if enabled:
        sh("nmcli device connect " + shlex.quote(dev))
        if not eth_connected(dev):
            names = [l.split(":", 1)[0] for l in
                     sh("nmcli -t -f NAME,TYPE con show").splitlines()
                     if l.endswith(":802-3-ethernet")]
            if names:
                sh("nmcli con up " + shlex.quote(names[0]))
    else:
        sh("nmcli device disconnect " + shlex.quote(dev))


BT_OBJECT = "/org/bluez/hci0"


def bt_powered():
    out = argv(["gdbus", "call", "--system", "--dest", "org.bluez",
                "--object-path", BT_OBJECT,
                "--method", "org.freedesktop.DBus.Properties.Get",
                "org.bluez.Adapter1", "Powered"], timeout=3)
    if "true" in out.lower():
        return True
    if "false" in out.lower():
        return False
    match = re.search(r"Powered:\s*(\w+)", sh("bluetoothctl show", timeout=3))
    return bool(match and match.group(1).lower() == "yes")


def bt_detail(powered=None):
    if powered is None:
        powered = bt_powered()
    lines = [l for l in sh("bluetoothctl devices Connected", timeout=3).splitlines()
             if l.strip()]
    return "%d connected" % len(lines) if lines else ("On" if powered else "Off")


def set_bt(enabled):
    out = argv(["gdbus", "call", "--system", "--dest", "org.bluez",
                "--object-path", BT_OBJECT,
                "--method", "org.freedesktop.DBus.Properties.Set",
                "org.bluez.Adapter1", "Powered",
                "<%s>" % ("true" if enabled else "false")], timeout=3)
    if "error" in out.lower():
        sh("bluetoothctl power " + ("on" if enabled else "off"), timeout=3)


def bt_scan_devices(seconds=10):
    """Discover nearby devices; return (newly seen, all) as (mac, name) lists."""
    before = {mac for mac, _name in bt_devices()}
    sh("timeout %d bluetoothctl scan on" % seconds, timeout=seconds + 4)
    devices = bt_devices()
    new = [(mac, name) for mac, name in devices if mac not in before]
    return new, devices


def sound_muted():
    return "yes" in sh("pactl get-sink-mute @DEFAULT_SINK@").lower()


def sound_volume():
    match = re.search(r"(\d+)%", sh("pactl get-sink-volume @DEFAULT_SINK@"))
    return int(match.group(1)) if match else 0


def set_sound_muted(muted):
    sh("pactl set-sink-mute @DEFAULT_SINK@ %s" % ("1" if muted else "0"))


def set_sound_volume(value):
    sh("pactl set-sink-volume @DEFAULT_SINK@ %d%%" % max(0, min(100, int(value))))


# ---- detail data / actions (used by right-click menus) --------------------- #
def wifi_networks():
    lines = sh("nmcli -t -f IN-USE,SSID,SIGNAL device wifi list").splitlines()
    networks, seen = [], set()
    for line in lines:
        parts = line.split(":")
        if len(parts) < 3:
            continue
        used, ssid, signal = parts[0], parts[1], parts[2]
        if not ssid or ssid in seen:
            continue
        seen.add(ssid)
        networks.append((ssid, signal, used == "*"))
    return networks[:10]


def wifi_connect(ssid):
    sh("nmcli device wifi connect " + shlex.quote(ssid), timeout=12)


def bt_devices():
    devices = []
    for line in sh("bluetoothctl devices", timeout=3).splitlines():
        match = re.match(r"Device\s+([0-9A-Fa-f:]+)\s+(.+)", line)
        if match:
            devices.append((match.group(1), match.group(2).strip()))
    return devices


def bt_action(action, mac):
    sh("bluetoothctl %s %s" % (action, shlex.quote(mac)), timeout=8)


def eth_connections():
    return [l.split(":", 1)[0] for l in sh("nmcli -t -f NAME,TYPE con show").splitlines()
            if l.endswith(":802-3-ethernet")]


def eth_connection_action(action, name):
    sh("nmcli con %s %s" % (action, shlex.quote(name)))


def sound_sinks():
    sinks, name, desc = [], None, None
    for line in sh("pactl list sinks").splitlines():
        text = line.strip()
        if text.startswith("Sink #"):
            if name:
                sinks.append((name, desc or name))
            name, desc = None, None
        elif text.startswith("Name:") and name is None:
            name = text.split(":", 1)[1].strip()
        elif text.startswith("Description:") and desc is None:
            desc = text.split(":", 1)[1].strip()
    if name:
        sinks.append((name, desc or name))
    return sinks


def set_default_sink(name):
    sh("pactl set-default-sink " + shlex.quote(name))
    for line in sh("pactl list short sink-inputs").splitlines():
        index = line.split("\t")[0]
        sh("pactl move-sink-input %s %s" % (shlex.quote(index), shlex.quote(name)))


DARK_PALETTE = {
    "panel_bg": "#1c1c20", "panel_border": "#3a3a42",
    "tile_bg": "#2c2c33", "tile_hover": "#3a3a44",
    "accent": "#0a84ff", "accent_hover": "#2b95ff",
    "text": "#f5f5f7", "sub": "#a1a1aa", "muted": "#8e8e99",
    "clock_color": "#ffffff",
    "on_sub": "rgba(255,255,255,0.85)",
    "trough": "#3a3a42", "slider_bg": "#ffffff",
    "close_bg": "#2c2c33", "close_hover": "#3a3a44", "close_text": "#c9c9d1",
}

LIGHT_PALETTE = {
    "panel_bg": "#f2f2f7", "panel_border": "#d1d1d6",
    "tile_bg": "#e5e5ea", "tile_hover": "#d8d8de",
    "accent": "#007aff", "accent_hover": "#1f8cff",
    "text": "#1c1c1e", "sub": "#6d6d72", "muted": "#6d6d72",
    "clock_color": "#000000",
    "on_sub": "rgba(255,255,255,0.9)",
    "trough": "#d1d1d6", "slider_bg": "#ffffff",
    "close_bg": "#e5e5ea", "close_hover": "#d8d8de", "close_text": "#3c3c43",
}

CSS_TEMPLATE = """
.panel-window {
    background-color: __panel_bg__;
    border-radius: 20px;
    border: 1px solid __panel_border__;
}
.tile {
    background-color: __tile_bg__;
    color: __text__;
    border-radius: 14px;
    border: none;
    min-width: 148px;
    min-height: 92px;
    padding: 8px;
    box-shadow: none;
}
.tile:hover { background-color: __tile_hover__; background-image: none; }
.tile:checked, .tile.on { background-color: __accent__; background-image: none; color: #ffffff; }
.tile:checked:hover, .tile.on:hover { background-color: __accent_hover__; background-image: none; }
.tile .tile-title { font-size: 13px; font-weight: bold; }
.tile .tile-sub { font-size: 10px; color: __sub__; }
.tile:checked .tile-sub, .tile.on .tile-sub { color: __on_sub__; }
.header-label { font-size: 11px; font-weight: bold; color: __muted__; }
.clock-label { font-size: 20px; font-weight: bold; color: __clock_color__; }
.date-label { font-size: 10px; color: __muted__; }
.close-button {
    background-color: __close_bg__; color: __close_text__;
    border-radius: 14px; min-width: 28px; min-height: 28px; padding: 0;
}
.close-button:hover { background-color: __close_hover__; }
.volume-icon { color: __sub__; }
.volume-value { font-size: 12px; color: __sub__; min-width: 38px; }
.footer-label { font-size: 10px; color: __muted__; }
scale trough { background-color: __trough__; border-radius: 4px; min-height: 6px; }
scale highlight { background-color: __accent__; border-radius: 4px; }
scale slider {
    background-color: __slider_bg__; border-radius: 8px;
    min-width: 16px; min-height: 16px; margin: -5px;
}
calendar { background-color: transparent; color: __text__; }
calendar:selected { background-color: __accent__; color: #ffffff; }
"""


def quick_settings_opacity():
    """Opacity set from OU Setting > Opacity (100 = solid)."""
    value = sh("xfconf-query -c xfce4-panel -p /quick-settings/opacity", 2)
    try:
        return max(0, min(100, int(value.strip().splitlines()[0])))
    except Exception:
        return 100


def with_alpha(color, alpha):
    if color.startswith("#") and len(color) == 7:
        r = int(color[1:3], 16)
        g = int(color[3:5], 16)
        b = int(color[5:7], 16)
        return "rgba(%d,%d,%d,%.2f)" % (r, g, b, alpha)
    return color


def build_css(dark):
    palette = DARK_PALETTE if dark else LIGHT_PALETTE
    alpha = quick_settings_opacity() / 100.0
    background_keys = {
        "panel_bg", "tile_bg", "tile_hover", "accent", "accent_hover",
        "trough", "slider_bg", "close_bg", "close_hover",
    }
    css = CSS_TEMPLATE
    for key, value in palette.items():
        if key in background_keys:
            value = with_alpha(value, alpha)
        css = css.replace("__%s__" % key, value)
    return css


def dark_mode_enabled():
    """Follow the day/night choice made in OU Setting / XFCE."""
    # GTK's "Night mode" switch (gtk-application-prefer-dark-theme).
    try:
        settings = Gtk.Settings.get_default()
        if settings and settings.get_property("gtk-application-prefer-dark-theme"):
            return True
    except Exception:
        pass
    # XFCE panel dark mode, toggled by OU Setting's panel preferences.
    try:
        if sh("xfconf-query -c xfce4-panel -p /panels/dark-mode", 2).lower() == "true":
            return True
    except Exception:
        pass
    # Persisted GTK setting, if present.
    try:
        ini = os.path.expanduser("~/.config/gtk-3.0/settings.ini")
        if os.path.isfile(ini):
            with open(ini, "r", encoding="utf-8", errors="ignore") as handle:
                for line in handle:
                    if line.strip().lower() == "gtk-application-prefer-dark-theme=true":
                        return True
    except Exception:
        pass
    return False


class Tile(Gtk.ToggleButton):
    def __init__(self, title, icon_on, icon_off, on_toggled, detail_key, on_detail):
        super().__init__()
        self.set_relief(Gtk.ReliefStyle.NONE)
        self.set_can_focus(False)
        self._syncing = False
        self.icon_on = icon_on
        self.icon_off = icon_off
        self.on_toggled = on_toggled
        self.detail_key = detail_key
        self.on_detail = on_detail
        self.get_style_context().add_class("tile")
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        box.set_halign(Gtk.Align.CENTER)
        box.set_valign(Gtk.Align.CENTER)
        self.image = Gtk.Image.new_from_icon_name(icon_off, Gtk.IconSize.DIALOG)
        self.image.set_pixel_size(28)
        lbl = Gtk.Label(label=title)
        lbl.get_style_context().add_class("tile-title")
        self.subtitle = Gtk.Label(label="")
        self.subtitle.get_style_context().add_class("tile-sub")
        self.subtitle.set_ellipsize(Pango.EllipsizeMode.END)
        self.subtitle.set_max_width_chars(18)
        box.pack_start(self.image, False, False, 0)
        box.pack_start(lbl, False, False, 0)
        box.pack_start(self.subtitle, False, False, 0)
        self.add(box)
        self.connect("toggled", self._toggled)
        self.connect("button-press-event", self._button_press)

    def _button_press(self, _widget, event):
        if event.button == Gdk.BUTTON_SECONDARY:
            self.on_detail(self, event)
            return True
        return False

    def set_state(self, active, subtitle):
        self._syncing = True
        self.set_active(bool(active))
        self._syncing = False
        ctx = self.get_style_context()
        if active:
            ctx.add_class("on")
        else:
            ctx.remove_class("on")
        icon = self.icon_on if active else self.icon_off
        if self.image.get_icon_name() != (icon, Gtk.IconSize.DIALOG):
            self.image.set_from_icon_name(icon, Gtk.IconSize.DIALOG)
        self.subtitle.set_label(subtitle or "")

    def _toggled(self, _button):
        if not self._syncing:
            self.on_toggled(self.get_active())


class ControlPanel:
    def __init__(self):
        self.window = Gtk.Window(type=Gtk.WindowType.TOPLEVEL)
        self.window.set_title(APP_TITLE)
        self.window.set_decorated(False)
        self.window.set_skip_taskbar_hint(True)
        self.window.set_skip_pager_hint(True)
        self.window.set_type_hint(Gdk.WindowTypeHint.POPUP_MENU)
        self.window.set_keep_above(True)
        visual = Gdk.Screen.get_default().get_rgba_visual()
        if visual:
            self.window.set_visual(visual)
        self.window.connect("delete-event", self._on_delete)
        self.window.connect("key-press-event", self._on_key)
        self.window.get_style_context().add_class("panel-window")

        # Transparent fullscreen window shown only while the panel is open.
        # It sits behind the panel and catches any click outside of it, so the
        # panel behaves like a menu: click away to dismiss.
        self._click_catcher = None

        # Month calendar shown inside the panel above the tiles.
        self.calendar_box = None
        self.gtk_calendar = None

        self.theme_override = None  # None = follow OU Setting's day/night mode
        self._is_dark = None
        self._css_opacity = None
        self.css_provider = Gtk.CssProvider()
        Gtk.StyleContext.add_provider_for_screen(
            Gdk.Screen.get_default(), self.css_provider,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
        try:
            Gtk.Settings.get_default().connect(
                "notify::gtk-application-prefer-dark-theme",
                lambda *_: GLib.idle_add(self._apply_theme))
        except Exception:
            pass

        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        root.set_margin_top(16)
        root.set_margin_bottom(14)
        root.set_margin_left(16)
        root.set_margin_right(16)
        self.window.add(root)

        header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        title = Gtk.Label(label="QUICK SETTINGS")
        title.get_style_context().add_class("header-label")
        title.set_halign(Gtk.Align.START)
        clockbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        clockbox.set_hexpand(True)
        clockbox.set_halign(Gtk.Align.END)
        self.clock = Gtk.Label(label="")
        self.clock.get_style_context().add_class("clock-label")
        self.clock.set_halign(Gtk.Align.END)
        self.date = Gtk.Label(label="")
        self.date.get_style_context().add_class("date-label")
        self.date.set_halign(Gtk.Align.END)
        clock_event = Gtk.EventBox()
        clock_event.add(self.clock)
        date_event = Gtk.EventBox()
        date_event.add(self.date)
        for header_widget in (clock_event, date_event):
            header_widget.add_events(Gdk.EventMask.BUTTON_PRESS_MASK)
            header_widget.connect("button-press-event", self._on_header_click)
        clockbox.pack_start(clock_event, False, False, 0)
        clockbox.pack_start(date_event, False, False, 0)
        close = Gtk.Button(label="✕")
        close.get_style_context().add_class("close-button")
        close.set_relief(Gtk.ReliefStyle.NONE)
        close.connect("clicked", lambda *_: self._hide_panel())
        header.pack_start(title, False, False, 0)
        header.pack_start(clockbox, True, True, 0)
        header.pack_start(close, False, False, 0)
        root.pack_start(header, False, False, 0)

        # Hidden until the clock/date area is left-clicked.
        self.calendar_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        self.calendar_box.set_no_show_all(True)
        self.gtk_calendar = Gtk.Calendar()
        self.gtk_calendar.set_display_options(
            Gtk.CalendarDisplayOptions.SHOW_DAY_NAMES |
            Gtk.CalendarDisplayOptions.SHOW_HEADING)
        self.calendar_box.pack_start(self.gtk_calendar, False, False, 0)
        root.pack_start(self.calendar_box, False, False, 0)

        grid = Gtk.Grid(column_spacing=10, row_spacing=10)
        grid.set_column_homogeneous(True)
        self.wifi = Tile("Wi-Fi", "network-wireless-symbolic",
                         "network-wireless-offline-symbolic",
                         lambda active: self._act(set_wifi, active),
                         "wifi", self._tile_detail)
        self.bluetooth = Tile("Bluetooth", "bluetooth-symbolic", "bluetooth-symbolic",
                              lambda active: self._act(set_bt, active),
                              "bluetooth", self._tile_detail)
        self.lan = Tile("LAN", "network-wired-symbolic", "network-wired-symbolic",
                        lambda active: self._act(set_eth, active),
                        "lan", self._tile_detail)
        self.sound = Tile("Sound", "audio-volume-high-symbolic",
                          "audio-volume-muted-symbolic",
                          lambda active: self._act(set_sound_muted, active),
                          "sound", self._tile_detail)
        grid.attach(self.wifi, 0, 0, 1, 1)
        grid.attach(self.bluetooth, 1, 0, 1, 1)
        grid.attach(self.lan, 0, 1, 1, 1)
        grid.attach(self.sound, 1, 1, 1, 1)
        root.pack_start(grid, False, False, 0)

        volbox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        volicon = Gtk.Image.new_from_icon_name("audio-volume-high-symbolic", Gtk.IconSize.BUTTON)
        volicon.get_style_context().add_class("volume-icon")
        self.scale = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 0, 100, 1)
        self.scale.set_draw_value(False)
        self.scale.set_hexpand(True)
        self.scale.connect("value-changed", self._on_volume)
        self.volvalue = Gtk.Label(label="")
        self.volvalue.get_style_context().add_class("volume-value")
        volbox.pack_start(volicon, False, False, 0)
        volbox.pack_start(self.scale, True, True, 0)
        volbox.pack_start(self.volvalue, False, False, 0)
        root.pack_start(volbox, False, False, 0)

        self.footer = Gtk.Label(label="")
        self.footer.get_style_context().add_class("footer-label")
        self.footer.set_ellipsize(Pango.EllipsizeMode.END)
        self.footer.set_max_width_chars(52)
        root.pack_start(self.footer, False, False, 0)

        self.tray = Gtk.StatusIcon.new_from_icon_name("preferences-system-symbolic")
        self.tray.set_title(APP_TITLE)
        self.tray.connect("activate", self._on_tray)
        self.tray.connect("popup-menu", self._on_tray_menu)

        self._syncing_volume = False
        self._apply_theme()
        self.refresh()
        GLib.timeout_add_seconds(REFRESH_SECONDS, self._periodic)

    def _act(self, action, value):
        action(value)
        GLib.timeout_add(250, self.refresh)

    def _apply_theme(self, *_args):
        dark = (self.theme_override == "dark" or
                (self.theme_override != "light" and dark_mode_enabled()))
        opacity = quick_settings_opacity()
        if dark == self._is_dark and opacity == self._css_opacity:
            return
        self._is_dark = dark
        self._css_opacity = opacity
        try:
            self.css_provider.load_from_data(build_css(dark).encode("utf-8"))
        except Exception:
            pass
        clock = getattr(self, "clock", None)
        if clock is not None:
            try:
                color = Gdk.RGBA()
                color.parse("#000000" if not dark else "#ffffff")
                clock.override_color(Gtk.StateFlags.NORMAL, color)
            except Exception:
                pass
        if self.window.get_visible():
            self.window.queue_draw()

    def _set_theme(self, choice):
        self.theme_override = choice
        self._apply_theme()

    def _get_click_catcher(self):
        """Fullscreen transparent click-catcher, created once and reused."""
        if self._click_catcher is None:
            win = Gtk.Window(type=Gtk.WindowType.POPUP)
            win.set_decorated(False)
            win.set_app_paintable(True)
            win.set_accept_focus(False)
            win.set_focus_on_map(False)
            win.set_skip_taskbar_hint(True)
            win.set_skip_pager_hint(True)
            win.set_type_hint(Gdk.WindowTypeHint.POPUP_MENU)
            screen = Gdk.Screen.get_default()
            visual = screen.get_rgba_visual()
            if visual:
                win.set_visual(visual)
            win.set_default_size(screen.get_width(), screen.get_height())
            win.move(0, 0)
            # Draw nothing at all: with an RGBA visual the window is invisible.
            win.connect("draw", lambda *_: True)
            win.connect("button-press-event", self._on_outside_click)
            self._click_catcher = win
        return self._click_catcher

    def _set_catcher_input(self, active):
        """Enable click-away, or let every click through while a menu is open."""
        if self._click_catcher is None:
            return
        win = self._click_catcher.get_window()
        if win is None:
            return
        if not active:
            win.input_shape_combine_region(cairo.Region(), 0, 0)
            return
        screen = Gdk.Screen.get_default()
        area = cairo.Region(cairo.RectangleInt(
            0, 0, screen.get_width(), screen.get_height()))
        x, y = self.window.get_position()
        width, height = self.window.get_size()
        area.subtract(cairo.Region(cairo.RectangleInt(x, y, width, height)))
        win.input_shape_combine_region(area, 0, 0)

    def _update_catcher_input_shape(self):
        """Punch the panel's rectangle out of the catcher's input area.

        The catcher stays above every other window, so a click anywhere else
        dismisses the panel; the hole lets clicks through to the panel itself.
        """
        self._set_catcher_input(True)

    def _suspend_catcher_for_menu(self, menu):
        """Menus pop outside the panel hole; give them all pointer events."""
        self._set_catcher_input(False)

        def restore(*_args):
            if self.window.get_visible():
                self._set_catcher_input(True)

        menu.connect("deactivate", restore)

    def _on_header_click(self, _widget, event):
        """Left-clicking the clock or date toggles the month calendar."""
        if event.button == Gdk.BUTTON_PRIMARY:
            self._toggle_calendar()
            return True
        return False

    def _toggle_calendar(self):
        show = not self.calendar_box.get_visible()
        if show:
            now = datetime.now()
            self.gtk_calendar.select_month(now.month - 1, now.year)
            self.gtk_calendar.select_day(now.day)
            self.gtk_calendar.mark_day(now.day)
            self.calendar_box.show()
            self.gtk_calendar.show()
        else:
            self.calendar_box.hide()
        # GTK does not shrink a window on its own after a child is hidden.
        GLib.idle_add(self._fit_panel)

    def _fit_panel(self):
        """Resize to the current content and keep the click-away hole in sync."""
        try:
            _minimum, natural = self.window.get_preferred_size()
            if natural and natural.width > 0 and natural.height > 0:
                self.window.resize(natural.width, natural.height)
        except Exception:
            pass
        self._update_catcher_input_shape()
        screen = Gdk.Screen.get_default()
        x, y = self.window.get_position()
        _width, height = self.window.get_size()
        if y + height > screen.get_height() - 4:
            self.window.move(x, max(4, screen.get_height() - height - 4))

    def _on_outside_click(self, _win, _event):
        self._hide_panel()
        return True  # consume the click; do not pass it to the app underneath

    def _hide_panel(self):
        if self.calendar_box is not None:
            self.calendar_box.hide()
        self.window.hide()
        if self._click_catcher is not None:
            self._click_catcher.hide()

    def _on_delete(self, _window, _event):
        self._hide_panel()
        return True

    def _on_key(self, _window, event):
        if event.keyval == Gdk.KEY_Escape:
            if self.calendar_box.get_visible():
                self._toggle_calendar()
            else:
                self._hide_panel()
            return True
        return False

    def _on_tray(self, *_args):
        if self.window.get_visible():
            self._hide_panel()
        else:
            self.refresh()
            self._get_click_catcher().show_all()
            self.window.show_all()
            self._place()
            self.window.present()
            # Keep the real panel (including its WM frame) above the catcher.
            try:
                gdkwin = self.window.get_window()
                parent = gdkwin.get_parent()
                if parent:
                    parent.raise_()
                gdkwin.raise_()
            except Exception:
                pass
            self._update_catcher_input_shape()

    def _place(self):
        screen = Gdk.Screen.get_default()
        width, height = self.window.get_size()
        x, y = screen.get_width() - width - 24, screen.get_height() - height - 48
        # Prefer the tray icon's own geometry so the panel opens beside it.
        try:
            ok, _screen, rect, _hint = self.tray.get_geometry()
            if ok and rect:
                x = rect.x + rect.width // 2 - width // 2
                y = rect.y + rect.height + 8
                if rect.y > height + 20:  # panel sits at the bottom of screen
                    y = rect.y - height - 8
        except Exception:
            pass
        # Fallback: place it above the mouse pointer.
        if self.tray.get_geometry()[0] is False:
            try:
                root = Gdk.get_default_root_window()
                if root:
                    px, py, _mask = root.get_pointer()
                    x, y = px - width // 2, py - height - 12
            except Exception:
                pass
        x = max(4, min(x, screen.get_width() - width - 4))
        y = max(4, min(y, screen.get_height() - height - 4))
        self.window.move(x, y)

    def _on_tray_menu(self, _icon, button, time):
        menu = Gtk.Menu()
        self._suspend_catcher_for_menu(menu)
        item = Gtk.MenuItem(label="Open panel")
        item.connect("activate", lambda *_: self._on_tray())
        menu.append(item)
        theme_item = Gtk.MenuItem(label="Theme")
        theme_menu = Gtk.Menu()
        for label, value in (("Follow OU Setting", None), ("Dark", "dark"),
                             ("Light", "light")):
            mark = "● " if self.theme_override == value else "   "
            choice = Gtk.MenuItem(label=mark + label)
            choice.connect("activate", lambda *_a, v=value: self._set_theme(v))
            theme_menu.append(choice)
        theme_item.set_submenu(theme_menu)
        menu.append(theme_item)
        menu.append(Gtk.SeparatorMenuItem())
        quit_item = Gtk.MenuItem(label="Quit")
        quit_item.connect("activate", lambda *_: Gtk.main_quit())
        menu.append(quit_item)
        menu.show_all()
        menu.popup(None, None, self.tray.position_menu, self.tray, button, time)

    def _on_bt_menu_key(self, menu, event, search_item):
        """Tab activates Search Devices in the Bluetooth menu."""
        if event.keyval == Gdk.KEY_Tab:
            search_item.activate()
            return True
        return False

    def _start_bt_scan(self, tile):
        """Run discovery off the UI thread, then show the found devices."""
        self._bt_scanning = True
        self.bluetooth.subtitle.set_label("Scanning…")

        def worker():
            try:
                new, devices = bt_scan_devices(10)
            except Exception:
                new, devices = [], []
            GLib.idle_add(self._show_bt_scan_results, tile, new, devices)

        threading.Thread(target=worker, daemon=True).start()

    def _show_bt_scan_results(self, tile, new, devices):
        self._bt_scanning = False
        menu = Gtk.Menu()
        if not bt_powered():
            self._add_item(menu, "Bluetooth is off", sensitive=False)
        found = new or devices
        if found:
            self._add_item(menu, "Found %d device(s)" % len(found), sensitive=False)
            for mac, name in found:
                item = self._add_item(menu, name or mac)
                submenu = Gtk.Menu()
                self._add_item(submenu, "Connect", lambda m=mac: bt_action("connect", m))
                self._add_item(submenu, "Pair", lambda m=mac: bt_action("pair", m))
                self._add_item(submenu, "Disconnect",
                               lambda m=mac: bt_action("disconnect", m))
                item.set_submenu(submenu)
        else:
            self._add_item(menu, "No nearby devices found", sensitive=False)
        menu.append(Gtk.SeparatorMenuItem())
        again = self._add_item(menu, "Search Again",
                               lambda t=tile: self._start_bt_scan(t))
        menu.connect("key-press-event", self._on_bt_menu_key, again)
        self._suspend_catcher_for_menu(menu)
        menu.show_all()
        menu.attach_to_widget(tile)
        event = getattr(self, "_bt_event", None)
        try:
            menu.popup_at_widget(tile, Gdk.Gravity.SOUTH_WEST,
                                 Gdk.Gravity.NORTH_WEST, event)
        except Exception:
            menu.popup(None, None, None, None, 0, Gtk.get_current_event_time())
        self.refresh()

    def _add_item(self, menu, label, action=None, sensitive=True):
        item = Gtk.MenuItem(label=label)
        if action:
            item.connect("activate", lambda *_: (
                action(), GLib.timeout_add(200, self.refresh)))
        item.set_sensitive(sensitive)
        menu.append(item)
        return item

    def _tile_detail(self, tile, event):
        """Build and show a right-click detail menu for the given tile."""
        key = tile.detail_key
        menu = Gtk.Menu()

        if key == "wifi":
            enabled = wifi_enabled()
            self._add_item(menu, "Wi-Fi — " + wifi_detail(), sensitive=False)
            self._add_item(menu, "Turn Wi-Fi " + ("off" if enabled else "on"),
                           lambda s=enabled: set_wifi(not s))
            menu.append(Gtk.SeparatorMenuItem())
            self._add_item(menu, "Networks", sensitive=False)
            networks = wifi_networks()
            if not networks:
                self._add_item(menu, "  No networks found", sensitive=False)
            for ssid, signal, used in networks:
                mark = "✓ " if used else "   "
                self._add_item(menu, "%s%s (%s%%)" % (mark, ssid, signal),
                               lambda s=ssid: wifi_connect(s))

        elif key == "bluetooth":
            try:
                self._bt_event = event.copy()
            except Exception:
                self._bt_event = event
            powered = bt_powered()
            self._add_item(menu, "Bluetooth — " + ("On" if powered else "Off"),
                           sensitive=False)
            self._add_item(menu, "Turn Bluetooth " + ("off" if powered else "on"),
                           lambda s=powered: set_bt(not s))
            search_item = self._add_item(
                menu, "Search Devices",
                lambda t=tile: self._start_bt_scan(t))
            menu.connect("key-press-event", self._on_bt_menu_key, search_item)
            menu.append(Gtk.SeparatorMenuItem())
            self._add_item(menu, "Devices", sensitive=False)
            devices = bt_devices()
            if not devices:
                self._add_item(menu, "  No paired devices", sensitive=False)
            for mac, name in devices:
                item = self._add_item(menu, name)
                submenu = Gtk.Menu()
                self._add_item(submenu, "Connect", lambda m=mac: bt_action("connect", m))
                self._add_item(submenu, "Disconnect",
                               lambda m=mac: bt_action("disconnect", m))
                item.set_submenu(submenu)

        elif key == "lan":
            dev = eth_device()
            connected = eth_connected(dev)
            active = sh("nmcli -g GENERAL.CONNECTION device show " + shlex.quote(dev))
            self._add_item(menu, "Ethernet — " + eth_detail(dev, connected),
                           sensitive=False)
            self._add_item(menu, "Disconnect Ethernet" if connected else "Connect Ethernet",
                           lambda s=connected, d=dev: set_eth(not s, d))
            menu.append(Gtk.SeparatorMenuItem())
            self._add_item(menu, "Connections", sensitive=False)
            names = eth_connections()
            if not names:
                self._add_item(menu, "  No Ethernet connections", sensitive=False)
            for name in names:
                is_active = name == active
                label = ("✓ " if is_active else "   ") + name
                self._add_item(
                    menu, label,
                    lambda n=name, a=is_active: eth_connection_action(
                        "down" if a else "up", n))

        elif key == "sound":
            muted = sound_muted()
            volume = sound_volume()
            self._add_item(menu, "Sound — " + ("Muted" if muted else "%d%%" % volume),
                           sensitive=False)
            self._add_item(menu, "Unmute" if muted else "Mute",
                           lambda m=muted: set_sound_muted(not m))
            for level in (25, 50, 100):
                self._add_item(menu, "Set volume %d%%" % level,
                               lambda v=level: set_sound_volume(v))
            menu.append(Gtk.SeparatorMenuItem())
            self._add_item(menu, "Output device", sensitive=False)
            default = sh("pactl get-default-sink")
            sinks = sound_sinks()
            if not sinks:
                self._add_item(menu, "  No output devices", sensitive=False)
            for name, description in sinks:
                mark = "✓ " if name == default else "   "
                self._add_item(menu, mark + description,
                               lambda n=name: set_default_sink(n))

        self._suspend_catcher_for_menu(menu)
        menu.show_all()
        menu.attach_to_widget(tile)
        try:
            menu.popup_at_widget(tile, Gdk.Gravity.SOUTH_WEST,
                                 Gdk.Gravity.NORTH_WEST, event)
        except Exception:
            menu.popup(None, None, None, None, event.button, event.time)

    def _on_volume(self, scale):
        if self._syncing_volume:
            return
        value = int(round(scale.get_value()))
        set_sound_volume(value)
        self.volvalue.set_label("%d%%" % value)
        if sound_muted():
            set_sound_muted(False)
        GLib.timeout_add(300, self.refresh)

    def _periodic(self):
        self.refresh()
        return True

    def refresh(self):
        wifi_on = wifi_enabled()
        self.wifi.set_state(wifi_on, wifi_detail() if wifi_on else "Off")

        bt_on = bt_powered()
        if not getattr(self, "_bt_scanning", False):
            self.bluetooth.set_state(bt_on, bt_detail(bt_on))

        dev = eth_device()
        lan_on = eth_connected(dev)
        self.lan.set_state(lan_on, eth_detail(dev, lan_on))

        muted = sound_muted()
        volume = sound_volume()
        self.sound.set_state(not muted, "Muted" if muted else "%d%%" % volume)
        self._syncing_volume = True
        self.scale.set_value(volume)
        self._syncing_volume = False
        self.volvalue.set_label("%d%%" % volume)

        self._apply_theme()  # follow OU Setting day/night changes
        now = datetime.now()
        self.clock.set_label(now.strftime("%H:%M:%S"))
        self.date.set_label(now.strftime("%a, %d %b %Y"))
        self.footer.set_label(
            "Wi-Fi: %s  •  LAN: %s  •  BT: %s  •  Vol: %s"
            % ("on" if wifi_on else "off", "on" if lan_on else "off",
               "on" if bt_on else "off", "muted" if muted else str(volume) + "%"))
        self.tray.set_tooltip_text(
            "%s\nWi-Fi: %s | LAN: %s | Bluetooth: %s | Sound: %s"
            % (APP_TITLE, "on" if wifi_on else "off", "on" if lan_on else "off",
               "on" if bt_on else "off", "muted" if muted else str(volume) + "%"))


if __name__ == "__main__":
    ControlPanel()
    Gtk.main()
