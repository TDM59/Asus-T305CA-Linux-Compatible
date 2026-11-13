#!/usr/bin/python3
import json
import os
from pathlib import Path
import signal
import subprocess
from threading import Thread
import unicodedata
from datetime import datetime

import cairo
import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
gi.require_version("Wnck", "3.0")
from gi.repository import Gdk, GdkPixbuf, Gio, GLib, Gtk, Pango, Wnck


FAVORITES = (
    ("firefox.desktop", "Internet", "web-browser"),
    ("thunar.desktop", "Fichiers", "system-file-manager"),
    ("asus-camera-avant.desktop", "Caméra avant", "camera-photo"),
    ("asus-camera-arriere.desktop", "Caméra arrière", "camera-photo"),
    ("t305ca-dessin-stylet.desktop", "Dessin", "applications-graphics"),
    ("xfce-settings-manager.desktop", "Paramètres", "preferences-system"),
)
ROTATION_LOCK = Path(GLib.get_user_runtime_dir()) / "t305ca-rotation-locked"
DRAWING_MODE = ROTATION_LOCK.with_name("t305ca-mode-dessin")
READING_MODE = ROTATION_LOCK.with_name("t305ca-mode-lecture")
FAVORITES_FILE = Path(GLib.get_user_config_dir()) / "t305ca" / "favoris-tablette.json"
MAX_FAVORITES = 6
QUICK_SETTINGS_WIDTH = 700
QUICK_SETTINGS_SIDE_MARGIN = 24

APP_DOMAINS = (
    ("Internet et réseau", {"Network"}),
    ("Bureautique", {"Office"}),
    ("Graphisme et photo", {"Graphics"}),
    ("Multimédia", {"AudioVideo", "Audio", "Video"}),
    ("Jeux", {"Game"}),
    ("Éducation et sciences", {"Education", "Science"}),
    ("Développement", {"Development"}),
    ("Paramètres", {"Settings"}),
    ("Système", {"System", "Emulator"}),
    ("Accessoires", {"Utility", "Accessibility", "Core", "Legacy"}),
)

STYLE = b"""
.home { background-color: #10262d; color: #ffffff; font-family: Inter, sans-serif; }
.home button, .shade button {
  border: 1px solid #49696c; border-radius: 20px; color: #f2faf9;
  background: #20383e; background-image: none; text-shadow: none;
}
.home button:hover, .shade button:hover { background: #345b61; }
.home button { padding: 12px; }
.shade button { min-height: 40px; padding: 5px 12px; }
.shade { background: #172d32; color: #f2faf9; }
.edge, .edge button, .edge button:hover, .edge button:active {
  background: transparent; background-image: none;
  border: none; box-shadow: none; padding: 0;
}
.pull-strip { background-color: transparent; }
.pull-strip-opaque { background-color: #20383e; }
.pull-handle { background-color: #d1f3ed; border: 1px solid #29474b; border-radius: 4px; }
.title { font-size: 32px; font-weight: 600; }
.clock { font-size: 58px; font-weight: 600; }
.hint { color: #dbefeb; }
.app-domain { font-size: 21px; font-weight: 600; }
.connection-name { font-size: 0.88em; color: #cae3df; }
.favorites-dock { background-color: rgba(16, 38, 45, 0.88); border-radius: 24px; padding: 8px; }
"""


def read_command(*args):
    try:
        return subprocess.run(args, capture_output=True, text=True, timeout=1, check=True,
                              env={**os.environ, "LC_ALL": "C"}).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return ""


def button(text, callback):
    widget = Gtk.Button(label=text)
    widget.connect("clicked", callback)
    return widget


def label(text, style=None):
    widget = Gtk.Label(label=text)
    if style:
        widget.get_style_context().add_class(style)
    return widget


class Tablet:
    def __init__(self):
        self.display = Gdk.Display.get_default()
        self.provider = Gtk.CssProvider()
        self.provider.load_from_data(STYLE)
        Gtk.StyleContext.add_provider_for_screen(
            Gdk.Screen.get_default(), self.provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
        self.home = self.window("Accueil tablette", "home")
        self.home.connect("delete-event", lambda *_: True)
        self.shade = self.window("Réglages rapides", "shade")
        self.shade.connect("delete-event", self.hide_shade)
        self.shade.connect("key-press-event", self.escape_shade)
        self.shade.connect("focus-out-event", self.shade_lost_focus)
        self.shade.connect("show", self.start_connection_refresh)
        self.shade.connect("hide", self.stop_connection_refresh)
        self.connection_timer = 0
        self.connection_refresh_running = False
        self.last_workarea = None
        self.window_history = []
        self.portrait_maximized = set()
        self.keyboard_maximized = set()
        self.fit_pending = 0
        self.wm = Wnck.Screen.get_default()
        self.wm.force_update()
        self.system_bus = Gio.bus_get_sync(Gio.BusType.SYSTEM, None)
        self.session_bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
        self.build_home()
        self.build_shade()
        self.top = self.build_pull_strip()
        self.bottom = self.build_navigation()
        self.position_edges()
        self.wm.connect("active-window-changed", self.active_window_changed)
        self.wm.connect("window-closed", self.window_closed)
        self.wm.connect("window-opened", self.screen_changed)
        self.active_window_changed(self.wm, None)
        Gdk.Screen.get_default().connect("size-changed", self.screen_changed)
        Gdk.Screen.get_default().connect("monitors-changed", self.screen_changed)
        GLib.timeout_add(250, self.position_edges)
        GLib.timeout_add_seconds(30, self.update_clock)

    def window(self, title, style):
        window = Gtk.Window(title=title)
        window.set_decorated(False)
        window.set_skip_taskbar_hint(True)
        window.set_skip_pager_hint(True)
        window.get_style_context().add_class(style)
        return window

    def build_home(self):
        overlay = Gtk.Overlay()
        background = Gtk.DrawingArea()
        wallpaper = read_command("xfconf-query", "-c", "xfce4-desktop", "-p",
                                 "/backdrop/screen0/monitoreDP-1/workspace0/last-image")
        if wallpaper and Path(wallpaper).is_file():
            try:
                picture = GdkPixbuf.Pixbuf.new_from_file(wallpaper)
                background.connect("draw", self.draw_wallpaper, picture)
            except GLib.Error:
                pass
        overlay.add(background)
        self.pages = Gtk.Stack(transition_type=Gtk.StackTransitionType.CROSSFADE)
        overlay.add_overlay(self.pages)
        self.home.add(overlay)

        front = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16, margin=24)
        center = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=22,
                         halign=Gtk.Align.CENTER, valign=Gtk.Align.CENTER)
        self.clock = label("", "clock")
        center.pack_start(self.clock, False, False, 0)
        center.pack_start(button("Toutes les applications  ↑", self.show_apps), False, False, 0)
        front.pack_start(center, True, True, 0)
        self.favorites_dock = Gtk.Box(spacing=8, halign=Gtk.Align.CENTER, margin_bottom=38)
        self.favorites_dock.get_style_context().add_class("favorites-dock")
        front.pack_end(self.favorites_dock, False, False, 0)
        self.favorites_editor = None
        self.favorite_ids = self.read_favorites()
        self.render_favorites()
        self.pages.add_named(front, "home")

        apps_page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12, margin=30)
        apps_page.pack_start(button("←  Accueil", self.show_home), False, False, 0)
        self.app_search = Gtk.SearchEntry(placeholder_text="Rechercher une application")
        self.app_search.connect("search-changed", self.filter_apps)
        apps_page.pack_start(self.app_search, False, False, 0)
        self.app_sections = []
        scroller = Gtk.ScrolledWindow()
        scroller.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scroller.set_kinetic_scrolling(True)
        self.apps_scroller = scroller
        apps_page.pack_start(scroller, True, True, 0)
        self.no_apps = label("Aucune application trouvée")
        self.no_apps.set_no_show_all(True)
        apps_page.pack_start(self.no_apps, False, False, 0)
        self.pages.add_named(apps_page, "apps")

        recent_page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14, margin=30)
        recent_page.pack_start(label("Fenêtres ouvertes", "title"), False, False, 0)
        recent_scroll = Gtk.ScrolledWindow()
        recent_scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self.recent = Gtk.ListBox(selection_mode=Gtk.SelectionMode.NONE)
        recent_scroll.add(self.recent)
        recent_page.pack_start(recent_scroll, True, True, 0)
        self.pages.add_named(recent_page, "recent")
        gesture = Gtk.GestureDrag.new(self.home)
        gesture.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
        gesture.connect("drag-end", self.home_drag)
        self.home.tablet_swipe = gesture
        self.update_clock()

    def read_favorites(self):
        try:
            saved = json.loads(FAVORITES_FILE.read_text())
            if isinstance(saved, list) and all(isinstance(item, str) for item in saved):
                return list(dict.fromkeys(saved))[:MAX_FAVORITES]
        except (OSError, ValueError):
            pass
        return [app_id for app_id, _, _ in FAVORITES if Gio.DesktopAppInfo.new(app_id)]

    def render_favorites(self):
        for child in self.favorites_dock.get_children():
            child.destroy()
        for app_id in self.favorite_ids:
            app = Gio.DesktopAppInfo.new(app_id)
            if not app:
                continue
            name = app.get_display_name()
            control = Gtk.Button()
            icon = app.get_icon() or Gio.ThemedIcon.new("application-x-executable")
            picture = Gtk.Image.new_from_gicon(icon, Gtk.IconSize.DIALOG)
            picture.set_pixel_size(30)
            control.add(picture)
            control.set_tooltip_text(name)
            control.get_accessible().set_name(name)
            control.connect("clicked", lambda _, target=app: self.launch(target))
            self.favorites_dock.pack_start(control, False, False, 0)
        self.favorites_dock.show_all()

    def show_favorites_editor(self, *_):
        if self.favorites_editor is not None:
            self.favorites_editor.destroy()
        page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12, margin=30)
        self.favorites_editor = page
        selected = [item for item in self.favorite_ids if Gio.DesktopAppInfo.new(item)]
        heading = label("", "app-domain")
        page.pack_start(heading, False, False, 0)
        search = Gtk.SearchEntry(placeholder_text="Rechercher une application")
        page.pack_start(search, False, False, 0)
        scroller = Gtk.ScrolledWindow()
        scroller.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scroller.set_kinetic_scrolling(True)
        items = Gtk.ListBox(selection_mode=Gtk.SelectionMode.NONE)
        scroller.add(items)
        page.pack_start(scroller, True, True, 0)
        status = label("")
        page.pack_start(status, False, False, 0)
        controls = Gtk.Box(spacing=10, homogeneous=True, margin_bottom=38)
        controls.pack_start(button("Annuler", self.show_home), True, True, 0)
        page.pack_end(controls, False, False, 0)

        def update_count():
            heading.set_text(f"Favoris · {len(selected)}/{MAX_FAVORITES}")

        def toggle(control, app_id):
            if not control.get_active():
                if app_id in selected:
                    selected.remove(app_id)
            elif len(selected) < MAX_FAVORITES:
                selected.append(app_id)
            else:
                control.set_active(False)
                status.set_text("Décoche un favori pour libérer une place.")
                return
            status.set_text("")
            update_count()

        def save(*_):
            try:
                FAVORITES_FILE.parent.mkdir(parents=True, exist_ok=True)
                temporary = FAVORITES_FILE.with_suffix(".tmp")
                temporary.write_text(json.dumps(selected) + "\n")
                temporary.replace(FAVORITES_FILE)
            except OSError as error:
                status.set_text(str(error))
                return
            self.favorite_ids = selected
            self.render_favorites()
            self.show_home()

        controls.pack_start(button("Enregistrer", save), True, True, 0)
        apps = {app.get_id(): app.get_display_name() for app in Gio.AppInfo.get_all()
                if app.get_id() and (app.should_show() or app.get_id() in selected)}
        for app_id, name in sorted(apps.items(), key=lambda item: item[1].casefold()):
            control = Gtk.CheckButton(label=name, active=app_id in selected)
            control.set_size_request(-1, 42)
            control.connect("toggled", toggle, app_id)
            items.add(control)
        items.set_filter_func(lambda row: search.get_text().casefold() in
                              row.get_child().get_label().casefold())
        search.connect("search-changed", lambda *_: items.invalidate_filter())
        update_count()
        self.pages.add_named(page, "favorites")
        self.present_page("favorites")

    def build_app_domains(self):
        sections = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=18)
        groups = {domain: [] for domain, _ in APP_DOMAINS}
        groups["Autres applications"] = []
        for app in Gio.AppInfo.get_all():
            if not app.should_show():
                continue
            categories = set((app.get_categories() or "").split(";"))
            domain = next((name for name, tags in APP_DOMAINS if categories & tags),
                          "Autres applications")
            groups[domain].append(app)

        for domain, entries in groups.items():
            if not entries:
                continue
            section = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
            heading = label(domain, "app-domain")
            heading.set_xalign(0)
            section.pack_start(heading, False, False, 0)
            apps = Gtk.FlowBox(selection_mode=Gtk.SelectionMode.NONE, homogeneous=True,
                               min_children_per_line=2, max_children_per_line=6,
                               row_spacing=10, column_spacing=10)
            matches = []
            for app in sorted(entries, key=lambda entry: entry.get_display_name().casefold()):
                name = app.get_display_name()
                apps.add(self.app_button(app, name))
                matches.append((apps.get_child_at_index(len(matches)),
                                self.search_key(f"{name} {domain}")))
            self.app_sections.append((section, matches))
            section.pack_start(apps, False, False, 0)
            sections.pack_start(section, False, False, 0)
        return sections

    @staticmethod
    def search_key(text):
        return "".join(char for char in unicodedata.normalize("NFD", text.casefold())
                       if not unicodedata.combining(char))

    def filter_apps(self, *_):
        terms = self.search_key(self.app_search.get_text()).split()
        found = False
        for section, entries in self.app_sections:
            visible = False
            for tile, key in entries:
                match = all(term in key for term in terms)
                tile.set_visible(match)
                visible |= match
            section.set_visible(visible)
            found |= visible
        self.no_apps.set_visible(not found)

    def draw_wallpaper(self, widget, cr, picture):
        width, height = widget.get_allocated_width(), widget.get_allocated_height()
        ratio = max(width / picture.get_width(), height / picture.get_height())
        cr.save()
        cr.translate((width - picture.get_width() * ratio) / 2,
                     (height - picture.get_height() * ratio) / 2)
        cr.scale(ratio, ratio)
        Gdk.cairo_set_source_pixbuf(cr, picture, 0, 0)
        cr.paint()
        cr.restore()
        cr.set_source_rgba(0.04, 0.13, 0.16, 0.34)
        cr.paint()
        return False

    def app_button(self, app, name, icon=None):
        widget = Gtk.Button()
        item = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=7)
        picture = (Gtk.Image.new_from_icon_name(icon, Gtk.IconSize.DIALOG) if icon
                   else Gtk.Image.new_from_gicon(app.get_icon() or Gio.ThemedIcon.new("application-x-executable"),
                                                 Gtk.IconSize.DIALOG))
        picture.set_pixel_size(36)
        item.pack_start(picture, False, False, 0)
        caption = label(name)
        caption.set_line_wrap(True)
        caption.set_max_width_chars(14)
        caption.set_justify(Gtk.Justification.CENTER)
        item.pack_start(caption, False, False, 0)
        widget.add(item)
        widget.connect("clicked", lambda *_: self.launch(app))
        return widget

    def launch(self, app):
        try:
            app.launch([], self.display.get_app_launch_context())
        except GLib.Error as error:
            self.status.set_text(str(error))
            self.shade.show_all()
            self.shade.present()
            return
        self.shade.hide()

    def update_clock(self):
        self.clock.set_text(datetime.now().strftime("%H:%M"))
        return GLib.SOURCE_CONTINUE

    def is_app_window(self, window):
        return (window is not None and not window.is_skip_tasklist()
                and window.get_window_type() in (Wnck.WindowType.NORMAL, Wnck.WindowType.DIALOG))

    def active_window_changed(self, screen, _):
        active = screen.get_active_window()
        if self.is_app_window(active):
            xid = active.get_xid()
            if xid in self.window_history:
                self.window_history.remove(xid)
            self.window_history.append(xid)
            self.home.hide()
            self.schedule_fit()
        elif not self.home.get_visible() and not self.shade.get_visible():
            workspace = screen.get_active_workspace()
            visible = any(self.is_app_window(window) and not window.is_minimized()
                          and workspace is not None and window.is_on_workspace(workspace)
                          for window in screen.get_windows())
            if not visible:
                self.show_home()

    def window_closed(self, screen, window):
        self.screen_changed()
        xid = window.get_xid()
        self.portrait_maximized.discard(xid)
        if xid in self.window_history:
            self.window_history.remove(xid)
        if self.home.get_visible() and self.pages.get_visible_child_name() == "recent":
            self.fill_recent()

    def present_page(self, page):
        self.shade.hide()
        if page == "home":
            self.update_clock()
        self.home.show_all()
        self.pages.set_visible_child_name(page)
        self.home.maximize()
        self.home.present()

    def show_home(self, *_):
        self.present_page("home")

    def activate_window(self, window):
        when = Gtk.get_current_event_time()
        workspace = window.get_workspace()
        if workspace and workspace != self.wm.get_active_workspace():
            workspace.activate(when)
        window.activate(when)
        self.home.hide()

    def fill_recent(self):
        for child in self.recent.get_children():
            self.recent.remove(child)
        windows = [window for window in reversed(self.wm.get_windows_stacked())
                   if self.is_app_window(window) and window.get_transient() is None]
        for window in windows:
            item = Gtk.Button()
            row = Gtk.Box(spacing=14, margin=4)
            icon = Gtk.Image.new_from_pixbuf(window.get_mini_icon())
            row.pack_start(icon, False, False, 0)
            title = label(window.get_name())
            title.set_xalign(0)
            title.set_ellipsize(Pango.EllipsizeMode.END)
            row.pack_start(title, True, True, 0)
            item.add(row)
            item.connect("clicked", lambda _, target=window: self.activate_window(target))
            self.recent.add(item)
        if not windows:
            self.recent.add(label("Aucune fenêtre ouverte."))
        self.recent.show_all()

    def show_recent(self, *_):
        self.wm.force_update()
        self.fill_recent()
        self.present_page("recent")

    def go_back(self, *_):
        if self.shade.get_visible():
            self.hide_shade()
            return
        if self.home.get_visible() and self.pages.get_visible_child_name() != "home":
            self.show_home()
            return
        active = self.wm.get_active_window()
        current = active.get_xid() if self.is_app_window(active) else None
        windows = {window.get_xid(): window for window in self.wm.get_windows()
                   if self.is_app_window(window)}
        for xid in reversed(self.window_history):
            if xid != current and xid in windows:
                self.activate_window(windows[xid])
                return
        self.show_home()

    def show_apps(self, *_):
        if self.apps_scroller.get_child() is None:
            self.apps_scroller.add(self.build_app_domains())
            self.apps_scroller.show_all()
        self.pages.set_visible_child_name("apps")
        self.app_search.set_text("")
        self.filter_apps()

    def home_drag(self, gesture, x, y):
        if abs(y) < 34 or abs(y) <= abs(x):
            return
        started, _, start_y = gesture.get_start_point()
        if not started:
            return
        if y > 0 and start_y < 105:
            self.show_shade()
        elif y < 0 and self.pages.get_visible_child_name() == "home":
            self.show_apps()

    def swipe(self, widget, direction, callback):
        gesture = Gtk.GestureDrag.new(widget)
        gesture.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
        gesture.connect("drag-end", lambda _, x, y: callback()
                        if direction * y > max(34, abs(x)) else None)
        widget.tablet_swipe = gesture

    def build_pull_strip(self):
        window = self.window("Zone de glissement des réglages rapides", "pull-strip")
        screen = window.get_screen()
        visual = screen.get_rgba_visual()
        if visual and screen.is_composited():
            window.set_visual(visual)
        else:
            window.get_style_context().add_class("pull-strip-opaque")
        window.set_type_hint(Gdk.WindowTypeHint.DOCK)
        window.set_keep_above(True)
        window.set_accept_focus(False)
        window.stick()
        zone = Gtk.EventBox()
        zone.set_size_request(400, 24)
        handle = Gtk.DrawingArea()
        handle.set_size_request(72, 6)
        handle.set_halign(Gtk.Align.CENTER)
        handle.set_valign(Gtk.Align.CENTER)
        handle.get_style_context().add_class("pull-handle")
        zone.add(handle)
        window.add(zone)
        self.swipe(window, 1, self.show_shade)
        window.show_all()
        return window

    def build_navigation(self):
        window = self.window("Navigation tablette", "edge")
        visual = window.get_screen().get_rgba_visual()
        if visual:
            window.set_visual(visual)
        window.set_type_hint(Gdk.WindowTypeHint.DOCK)
        window.set_keep_above(True)
        window.set_accept_focus(False)
        window.stick()
        self.navigation_timeout = 0
        overlay = Gtk.Overlay()
        overlay.add(Gtk.DrawingArea())
        overlay.set_size_request(252, 52)
        self.navigation = Gtk.Revealer(
            transition_type=Gtk.RevealerTransitionType.SLIDE_UP,
            transition_duration=180, valign=Gtk.Align.END)
        overlay.add_overlay(self.navigation)
        row = Gtk.Box(homogeneous=True)
        for icon, name, action in (("recent", "Fenêtres", self.show_recent),
                                   ("home", "Accueil", self.show_home),
                                   ("back", "Précédent", self.go_back)):
            control = Gtk.Button(relief=Gtk.ReliefStyle.NONE)
            control.set_size_request(84, 48)
            control.set_tooltip_text(name)
            control.get_accessible().set_name(name)
            drawing = Gtk.DrawingArea()
            drawing.connect("draw", self.draw_navigation_icon, icon)
            control.add(drawing)
            control.connect("clicked", self.navigation_clicked, action)
            row.pack_start(control, True, True, 0)
        self.navigation.add(row)
        window.add(overlay)
        window.connect("size-allocate", self.navigation_input_shape)
        gesture = Gtk.GestureDrag.new(window)
        gesture.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
        gesture.connect("drag-update", self.navigation_drag)
        window.tablet_swipe = gesture
        window.show_all()
        return window

    def draw_navigation_icon(self, widget, cr, icon):
        cr.translate((widget.get_allocated_width() - 24) / 2,
                     (widget.get_allocated_height() - 24) / 2)
        if icon == "recent":
            for x in (6, 12, 18):
                cr.move_to(x, 5)
                cr.line_to(x, 19)
        elif icon == "home":
            cr.rectangle(5, 5, 14, 14)
        else:
            cr.move_to(15, 5)
            cr.line_to(8, 12)
            cr.line_to(15, 19)
        cr.set_line_cap(cairo.LINE_CAP_ROUND)
        cr.set_line_join(cairo.LINE_JOIN_ROUND)
        cr.set_source_rgb(0, 0, 0)
        cr.set_line_width(5)
        cr.stroke_preserve()
        cr.set_source_rgb(1, 1, 1)
        cr.set_line_width(2.6)
        cr.stroke()
        return False

    def navigation_input_shape(self, window, allocation):
        height = allocation.height if self.navigation.get_reveal_child() else min(16, allocation.height)
        shape = cairo.Region(cairo.RectangleInt(
            0, allocation.height - height, allocation.width, height))
        window.input_shape_combine_region(shape)

    def navigation_drag(self, gesture, x, y):
        if abs(y) <= max(30, abs(x)):
            return
        gesture.set_state(Gtk.EventSequenceState.CLAIMED)
        if y < 0:
            self.show_navigation()
        else:
            self.hide_navigation()

    def navigation_clicked(self, _, action):
        action()
        self.show_navigation()

    def show_navigation(self):
        if self.navigation_timeout:
            GLib.source_remove(self.navigation_timeout)
        self.navigation.set_reveal_child(True)
        self.navigation_input_shape(self.bottom, self.bottom.get_allocation())
        self.navigation_timeout = GLib.timeout_add_seconds(4, self.navigation_expired)

    def navigation_expired(self):
        self.navigation_timeout = 0
        return self.hide_navigation()

    def hide_navigation(self):
        if self.navigation_timeout:
            GLib.source_remove(self.navigation_timeout)
            self.navigation_timeout = 0
        self.navigation.set_reveal_child(False)
        self.navigation_input_shape(self.bottom, self.bottom.get_allocation())
        return GLib.SOURCE_REMOVE

    def schedule_fit(self):
        if self.fit_pending:
            GLib.source_remove(self.fit_pending)
        self.fit_pending = GLib.timeout_add(65, self.fit_active_window)

    def restore_window_sizes(self, resized=None):
        if resized is None:
            resized = self.portrait_maximized | self.keyboard_maximized
        resized = resized.copy()
        for window in self.wm.get_windows():
            if window.get_xid() in resized and window.is_maximized():
                window.unmaximize()
        self.portrait_maximized.difference_update(resized)
        self.keyboard_maximized.difference_update(resized)

    def keyboard_is_visible(self):
        return any(window.get_window_type() == Wnck.WindowType.DOCK
                   and window.get_class_instance_name() == "onboard"
                   for window in self.wm.get_windows())

    def fit_active_window(self):
        self.fit_pending = 0
        monitor = self.display.get_primary_monitor() or self.display.get_monitor(0)
        area = monitor.get_workarea()
        screen = monitor.get_geometry()
        portrait = screen.width < screen.height
        self.wm.force_update()
        keyboard_visible = self.keyboard_is_visible()
        if not keyboard_visible and not portrait:
            return GLib.SOURCE_REMOVE
        window = self.wm.get_active_window()
        if (not self.is_app_window(window) or window.get_window_type() != Wnck.WindowType.NORMAL
                or window.is_fullscreen() or window.is_maximized()):
            return GLib.SOURCE_REMOVE

        scale = monitor.get_scale_factor()
        x, y, width, height = window.get_geometry()
        left, top = area.x * scale, area.y * scale
        right, bottom = left + area.width * scale, top + area.height * scale
        if (x < left - 4 or y < top - 4 or x + width > right + 4 or y + height > bottom + 4):
            if window.get_actions() & Wnck.WindowActions.MAXIMIZE:
                resized = self.keyboard_maximized if keyboard_visible else self.portrait_maximized
                resized.add(window.get_xid())
                window.maximize()
        return GLib.SOURCE_REMOVE

    def screen_changed(self, *_):
        GLib.idle_add(self.reposition)

    def reposition(self):
        self.position_edges()
        return GLib.SOURCE_REMOVE

    def position_edges(self):
        monitor = self.display.get_primary_monitor() or self.display.get_monitor(0)
        area = monitor.get_workarea()
        geometry = (area.x, area.y, area.width, area.height)
        if geometry != self.last_workarea:
            self.last_workarea = geometry
            screen = monitor.get_geometry()
            self.wm.force_update()
            if not self.keyboard_is_visible():
                self.restore_window_sizes(self.keyboard_maximized)
            if screen.width >= screen.height:
                self.restore_window_sizes(self.portrait_maximized)
            self.schedule_fit()
            for window, bottom in ((self.top, False), (self.bottom, True)):
                width, height = window.get_size()
                window.move(area.x + (area.width - width) // 2,
                            area.y + area.height - height if bottom else area.y)
            if self.shade.get_visible():
                self.position_shade()
        return GLib.SOURCE_CONTINUE

    def build_shade(self):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14, margin=22)
        self.shade.add(box)
        box.pack_start(label("Réglages rapides", "title"), False, False, 0)
        row = Gtk.Grid(row_spacing=10, column_spacing=10, column_homogeneous=True)
        self.quick_grid = row
        self.quick_columns = 0
        self.wifi, self.wifi_connection = self.connection_button("Wi-Fi", self.toggle_wifi)
        self.bluetooth, self.bluetooth_connection = self.connection_button(
            "Bluetooth", self.toggle_bluetooth)
        self.rotation, self.rotation_status = self.connection_button("Rotation", self.toggle_rotation)
        self.drawing, self.drawing_status = self.connection_button("Mode dessin", self.toggle_drawing)
        self.reading, self.reading_status = self.connection_button("Mode lecture", self.toggle_reading)
        self.power_profile, self.power_status = self.connection_button(
            "Profil batterie", self.toggle_power_profile)
        self.quick_buttons = (self.wifi, self.bluetooth,
                                  button("Couper / rétablir le son", lambda *_: self.command(
                                      "pactl", "set-sink-mute", "@DEFAULT_SINK@", "toggle")),
                                  button("Clavier à l’écran", self.keyboard),
                                  button("Lumière nocturne", lambda *_: self.command(
                                      "pkill", "-USR1", "-u", str(os.getuid()), "-x", "redshift")),
                                  button("Paramètres Mint", self.open_settings),
                                  self.rotation,
                                  button("Modifier les favoris", self.show_favorites_editor),
                                  self.power_profile, self.drawing, self.reading)
        self.layout_quick_buttons(3)
        box.pack_start(row, False, False, 0)
        self.brightness = self.slider(box, "Luminosité", 10, 100, self.set_brightness)
        self.volume = self.slider(box, "Volume", 0, 100, self.set_volume)
        self.status = label("")
        self.status.set_line_wrap(True)
        box.pack_start(self.status, False, False, 0)
        box.pack_start(button("Fermer  ↑", self.hide_shade), False, False, 0)
        self.swipe(self.shade, -1, self.hide_shade)

    def layout_quick_buttons(self, columns):
        if columns == self.quick_columns:
            return
        for index, item in enumerate(self.quick_buttons):
            if item.get_parent() is not None:
                self.quick_grid.remove(item)
            self.quick_grid.attach(item, index % columns, index // columns, 1, 1)
        self.quick_columns = columns

    def slider(self, box, title, minimum, maximum, callback):
        box.pack_start(label(title), False, False, 0)
        slider = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, minimum, maximum, 1)
        slider.set_size_request(-1, 38)
        slider.set_value_pos(Gtk.PositionType.RIGHT)
        handler = slider.connect("value-changed", callback)
        box.pack_start(slider, False, False, 0)
        return slider, handler

    def connection_button(self, title, callback):
        widget = Gtk.Button()
        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=3)
        content.pack_start(label(title), False, False, 0)
        status = label("", "connection-name")
        status.set_ellipsize(Pango.EllipsizeMode.END)
        status.set_max_width_chars(20)
        content.pack_start(status, False, False, 0)
        widget.add(content)
        widget.connect("clicked", callback)
        return widget, status

    def refresh_connections(self):
        if self.connection_refresh_running:
            return
        self.connection_refresh_running = True
        Thread(target=self.read_connections, daemon=True).start()

    def read_connections(self):
        wifi = read_command("nmcli", "radio", "wifi")
        bluetooth = read_command("bluetoothctl", "show")
        wifi_name = ""
        if wifi == "enabled":
            networks = read_command("nmcli", "-t", "-e", "no", "-f", "IN-USE,SSID",
                                    "device", "wifi", "list", "--rescan", "no")
            wifi_name = next((line[2:] for line in networks.splitlines() if line.startswith("*:")), "")
        devices = []
        bluetooth_enabled = "Powered: yes" in bluetooth
        if bluetooth_enabled:
            for line in read_command("bluetoothctl", "devices", "Connected").splitlines():
                fields = line.split(maxsplit=2)
                if len(fields) == 3 and fields[0] == "Device":
                    devices.append(fields[2])
        wifi_status = wifi_name or ("Non connecté" if wifi == "enabled" else "Désactivé")
        bluetooth_status = " · ".join(devices) or ("Non connecté" if bluetooth_enabled else "Désactivé")
        GLib.idle_add(self.show_connections, wifi_status, bluetooth_status, bool(wifi), bool(bluetooth))

    def show_connections(self, wifi_status, bluetooth_status, wifi_available, bluetooth_available):
        self.connection_refresh_running = False
        self.wifi_connection.set_text(wifi_status)
        self.wifi.set_tooltip_text(wifi_status)
        self.bluetooth_connection.set_text(bluetooth_status)
        self.bluetooth.set_tooltip_text(bluetooth_status)
        self.wifi.set_sensitive(wifi_available)
        self.bluetooth.set_sensitive(bluetooth_available)
        return GLib.SOURCE_REMOVE

    def start_connection_refresh(self, *_):
        if not self.connection_timer:
            self.connection_timer = GLib.timeout_add_seconds(3, self.refresh_visible_connections)

    def stop_connection_refresh(self, *_):
        if self.connection_timer:
            GLib.source_remove(self.connection_timer)
            self.connection_timer = 0

    def refresh_visible_connections(self):
        self.refresh_connections()
        return GLib.SOURCE_CONTINUE

    def refresh(self):
        self.refresh_power_profile()
        self.refresh_rotation()
        self.refresh_connections()
        self.status.set_text("")
        try:
            path = Path("/sys/class/backlight/intel_backlight")
            self.max_brightness = int((path / "max_brightness").read_text())
            percent = 100 * int((path / "actual_brightness").read_text()) / self.max_brightness
            self.refresh_slider(self.brightness, percent)
        except (OSError, ValueError, ZeroDivisionError):
            self.brightness[0].set_sensitive(False)
        levels = read_command("pactl", "get-sink-volume", "@DEFAULT_SINK@").split()
        percent = next((int(level[:-1]) for level in levels if level.endswith("%") and level[:-1].isdigit()), None)
        if percent is not None:
            self.refresh_slider(self.volume, percent)

    def refresh_slider(self, control, value):
        widget, handler = control
        widget.handler_block(handler)
        widget.set_value(value)
        widget.handler_unblock(handler)

    def refresh_power_profile(self):
        profile = read_command("powerprofilesctl", "get")
        names = {"balanced": "Équilibré", "power-saver": "Économie", "performance": "Performance"}
        self.power_status.set_text(names.get(profile, "Indisponible"))
        self.power_profile.set_sensitive(profile in names)

    def toggle_power_profile(self, *_):
        profile = read_command("powerprofilesctl", "get")
        if profile:
            target = "balanced" if profile == "power-saver" else "power-saver"
            self.command("powerprofilesctl", "set", target, refresh=True)

    def refresh_rotation(self):
        drawing = DRAWING_MODE.exists()
        reading = READING_MODE.exists()
        self.rotation_status.set_text("Verrouillée" if drawing or reading or ROTATION_LOCK.exists() else "Automatique")
        self.rotation.set_sensitive(not (drawing or reading))
        self.drawing.set_sensitive(not reading)
        self.reading.set_sensitive(not drawing)
        self.drawing_status.set_text("Actif · stylet seul" if drawing else "Désactivé")
        self.reading_status.set_text("Actif · portrait" if reading else "Désactivé")

    def toggle_reading(self, *_):
        try:
            if READING_MODE.exists():
                READING_MODE.unlink()
            elif not DRAWING_MODE.exists():
                READING_MODE.touch()
        except OSError as error:
            self.status.set_text(str(error))
        self.refresh_rotation()

    def toggle_drawing(self, *_):
        try:
            if DRAWING_MODE.exists():
                DRAWING_MODE.unlink(missing_ok=True)
            else:
                DRAWING_MODE.touch()
        except OSError as error:
            self.status.set_text(str(error))
        self.refresh_rotation()

    def toggle_rotation(self, *_):
        try:
            if ROTATION_LOCK.exists():
                ROTATION_LOCK.unlink(missing_ok=True)
            else:
                ROTATION_LOCK.touch()
        except OSError as error:
            self.status.set_text(str(error))
        self.refresh_rotation()

    def position_shade(self):
        x, y, width, _ = self.last_workarea
        shade_width = min(QUICK_SETTINGS_WIDTH, max(1, width - 2 * QUICK_SETTINGS_SIDE_MARGIN))
        self.layout_quick_buttons(3 if shade_width >= 640 else 2)
        _, height = self.shade.get_child().get_preferred_height_for_width(shade_width)
        self.shade.resize(shade_width, max(1, height))
        self.shade.move(x + max(0, (width - shade_width) // 2), y + self.top.get_size()[1] + 8)

    def show_shade(self, *_):
        if not self.shade.get_visible():
            self.refresh()
            self.shade.show_all()
        self.position_shade()
        self.shade.deiconify()
        self.shade.present_with_time(Gtk.get_current_event_time())

    def shade_lost_focus(self, *_):
        self.hide_shade()
        return False

    def hide_shade(self, *_):
        self.shade.hide()
        return True

    def escape_shade(self, _, event):
        return self.hide_shade() if event.keyval == Gdk.KEY_Escape else False

    def command(self, *args, refresh=False):
        try:
            process = Gio.Subprocess.new(args, Gio.SubprocessFlags.STDOUT_SILENCE |
                                         Gio.SubprocessFlags.STDERR_SILENCE)
        except GLib.Error as error:
            self.status.set_text(str(error))
            return

        def completed(proc, result):
            try:
                proc.wait_check_finish(result)
            except GLib.Error:
                self.status.set_text("Le réglage n’a pas pu être appliqué.")
            else:
                if refresh:
                    self.refresh()
        process.wait_check_async(None, completed)

    def toggle_wifi(self, *_):
        wifi = read_command("nmcli", "radio", "wifi")
        if wifi:
            self.command("nmcli", "radio", "wifi", "off" if wifi == "enabled" else "on", refresh=True)

    def toggle_bluetooth(self, *_):
        info = read_command("bluetoothctl", "show")
        if info:
            self.command("bluetoothctl", "power", "off" if "Powered: yes" in info else "on", refresh=True)

    def set_volume(self, scale):
        self.command("pactl", "set-sink-volume", "@DEFAULT_SINK@", f"{int(scale.get_value())}%")

    def set_brightness(self, scale):
        raw = round(self.max_brightness * scale.get_value() / 100)
        self.system_bus.call("org.freedesktop.login1", "/org/freedesktop/login1/session/auto",
                             "org.freedesktop.login1.Session", "SetBrightness",
                             GLib.Variant("(ssu)", ("backlight", "intel_backlight", raw)),
                             None, Gio.DBusCallFlags.NONE, 1000, None, None)

    def open_settings(self, *_):
        app = Gio.DesktopAppInfo.new("xfce-settings-manager.desktop")
        if app:
            self.launch(app)

    def keyboard(self, *_):
        self.shade.hide()
        self.session_bus.call("org.onboard.Onboard", "/org/onboard/Onboard/Keyboard",
                              "org.onboard.Onboard.Keyboard", "Show", None, None,
                              Gio.DBusCallFlags.NO_AUTO_START, 1500, None, None)


if __name__ == "__main__":
    app = Tablet()
    GLib.unix_signal_add(GLib.PRIORITY_DEFAULT, signal.SIGTERM, lambda: Gtk.main_quit() or False)
    try:
        Gtk.main()
    finally:
        app.restore_window_sizes()
