"""One account = one set of pages (UI v7): a ttk.Notebook with 7 tabs + a bottom bar that is always visible.

Panels keep their own logic and config keys; only the frame they are built in changed. Each page scrolls only
when its content does not fit (it fits at the default 440x640)."""
import tkinter as tk
from tkinter import messagebox, ttk

from .. import hunt_maps, monsters
from ..config.models import UI_TABS
from .panels import (
    ClassPanel,
    ControlPanel,
    CursorPanel,
    GridPanel,
    HealthPanel,
    LootPanel,
    MapPanel,
    RecordPanel,
    ScanPanel,
    SkillSetupPanel,
    StatsPanel,
    StatusPanel,
    WindowPanel,
    ZonePanel,
)

MIN_CONTENT_WIDTH = 400  # below this a page scrolls sideways instead of being squeezed
WARN_MARK = " ⚠"


class ScrollPage:
    """A notebook page whose scroll bars appear only when the content overflows."""

    def __init__(self, notebook):
        self.outer = ttk.Frame(notebook)
        self.canvas = tk.Canvas(self.outer, highlightthickness=0)
        self.ybar = ttk.Scrollbar(self.outer, orient="vertical", command=self.canvas.yview)
        self.xbar = ttk.Scrollbar(self.outer, orient="horizontal", command=self.canvas.xview)
        self.body = ttk.Frame(self.canvas)
        self._win = self.canvas.create_window((0, 0), window=self.body, anchor="nw")
        self.canvas.configure(yscrollcommand=self.ybar.set, xscrollcommand=self.xbar.set)
        self.canvas.grid(row=0, column=0, sticky="nsew")
        self.outer.rowconfigure(0, weight=1)
        self.outer.columnconfigure(0, weight=1)
        self.body.bind("<Configure>", lambda _e: self._fit())
        self.canvas.bind("<Configure>", lambda _e: self._fit())
        self.canvas.bind("<Enter>", lambda _e: self.canvas.bind_all("<MouseWheel>", self._wheel))
        self.canvas.bind("<Leave>", lambda _e: self.canvas.unbind_all("<MouseWheel>"))

    def _fit(self):
        width = max(self.canvas.winfo_width(), MIN_CONTENT_WIDTH)
        self.canvas.itemconfigure(self._win, width=width)
        self.canvas.configure(scrollregion=(0, 0, width, self.body.winfo_reqheight()))
        tall = self.body.winfo_reqheight() > self.canvas.winfo_height() > 1
        wide = width > self.canvas.winfo_width() > 1
        for bar, show, where in ((self.ybar, tall, dict(row=0, column=1, sticky="ns")),
                                 (self.xbar, wide, dict(row=1, column=0, sticky="ew"))):
            if show and not bar.winfo_ismapped():
                bar.grid(**where)
            elif not show and bar.winfo_ismapped():
                bar.grid_remove()

    def _wheel(self, event):
        if self.body.winfo_reqheight() > self.canvas.winfo_height():
            self.canvas.yview_scroll(int(-event.delta / 120), "units")


class AccountTab:
    """The settings pages for one account. Parent is a Notebook or a Frame."""

    def __init__(self, parent, app, account):
        self.app = app
        self.account = account
        self.session = app.manager.session_for(account)
        self.last_hp = None
        self.last_mp = None
        self._tab_titles = {}

        self.frame = ttk.Frame(parent)
        # Packed first with side="bottom" so it always stays visible.
        self.control = ControlPanel(self.frame, self)

        self.notebook = ttk.Notebook(self.frame)
        self.notebook.pack(fill="both", expand=True, padx=4, pady=(4, 0))
        self.pages = {}
        for key in UI_TABS:
            page = ScrollPage(self.notebook)
            self.notebook.add(page.outer, text=key)
            self.pages[key] = page.body

        main, hunt, heal = self.pages["main"], self.pages["hunt"], self.pages["heal"]
        self.window = WindowPanel(main, self)
        self.character = ClassPanel(main, self)
        self.zone = ZonePanel(main, self)
        self.hunt_map = MapPanel(main, self)
        self.status = StatusPanel(main, self)
        self.scan = ScanPanel(hunt, self)
        self.loot = LootPanel(hunt, self)
        self.grid = GridPanel(hunt, self)
        self.health = HealthPanel(heal, self)
        self.skill_setup = SkillSetupPanel(self.pages["skills"], self)
        self.cursor = CursorPanel(self.pages["cursor"], self)
        self.record = RecordPanel(self.pages["data"], self)
        self.stats = StatsPanel(self.pages["stats"], self)  # PLAN 4.1

        self.select_page(app.settings.ui.tab)
        self.notebook.bind("<<NotebookTabChanged>>", self._page_changed)
        self.apply_language()

    def select_page(self, key):
        if key in UI_TABS:
            self.notebook.select(UI_TABS.index(key))

    def current_page(self):
        try:
            return UI_TABS[self.notebook.index(self.notebook.select())]
        except (tk.TclError, ValueError, IndexError):
            return "main"

    def _page_changed(self, _event=None):
        self.app.settings.ui.tab = self.current_page()

    def update_tab_titles(self):
        """Tab names in the current language, with a mark where something needs attention."""
        cursors = self.session.ctx.cursors
        attention = {
            "main": bool(self.status.update_status()),
            "cursor": not cursors.ready or bool(cursors.duplicate_kinds()),
        }
        for index, key in enumerate(UI_TABS):
            title = self.t(f"tab_{key}") + (WARN_MARK if attention.get(key) else "")
            if self._tab_titles.get(key) != title:
                self.notebook.tab(index, text=title)
                self._tab_titles[key] = title

    @property
    def translator(self):
        # Tests may inject a translator without a full MainWindow.
        override = self.__dict__.get("_translator_override")
        if override is not None:
            return override
        return self.app.translator

    @translator.setter
    def translator(self, value):
        self._translator_override = value

    def t(self, translation_key, **kwargs):
        return self.translator.t(translation_key, **kwargs)

    def request_save(self):
        self.app.request_save()

    def window_taken(self, label):
        """True when another account already drives this window."""
        return self.app.window_taken(label, exclude=self.account.id)

    def on_class_changed(self):
        self.refresh_skill_summary()
        self.cursor.apply_language()

    def refresh_skill_summary(self):
        self.skill_setup.refresh_summary()

    def show_skill_warning(self, text):
        """Show a conflict as a modal popup (no inline banner)."""
        messagebox.showwarning(self.t("warn_title"), text)

    def notify_map_selected(self):
        """Tell the user whether this map's ONNX is on disk."""
        hunt = hunt_maps.get(self.account.hunt_map)
        name = self.translator.map_name(hunt)
        if hunt_maps.model_exists(self.account.hunt_map):
            messagebox.showinfo(self.t("warn_title"), self.t("map_loaded", map=name))
        else:
            messagebox.showwarning(self.t("warn_title"), self.t("warn_map_model", map=name))

    def panels(self):
        return (
            self.window,
            self.character,
            self.zone,
            self.hunt_map,
            self.status,
            self.scan,
            self.loot,
            self.grid,
            self.health,
            self.skill_setup,
            self.cursor,
            self.record,
            self.control,
        )

    def store(self):
        for panel in self.panels():
            panel.store()
        self.account.enforce_skill_exclusivity()

    def apply_language(self):
        for panel in self.panels():
            panel.apply_language()
        self._tab_titles = {}
        self.update_tab_titles()

    def refresh_state(self):
        running = self.session.running
        self.control.show_state(self.session.state, running)
        self.stats.refresh()  # PLAN 4.1
        learned = self.account.scan.attack_range_px_learned
        if learned != getattr(self, "_learned_shown", learned):  # 3.0-L v2: the hunt learned a shorter reach
            self.scan.range_label()
            self.request_save()
        self._learned_shown = learned
        try:
            for panel in self.panels():
                panel.set_busy(running)
            self.update_tab_titles()
        except tk.TclError:
            return

    def show_hp(self, percent):
        self.last_hp = percent
        self.control.show_hp(percent, self.session.ctx.state.get("hp_abs") if percent is not None else None)

    def show_mp(self, percent):
        self.last_mp = percent
        self.control.show_mp(percent, self.session.ctx.state.get("mp_abs") if percent is not None else None)

    def run_selected(self):
        """Big button: stop whatever runs, else start the mode picked on the Main tab."""
        if self.session.running:
            print("[ENGINE] stop: Stop button")  # PLAN 0.28
            self.session.stop()
            self.refresh_state()
            return None
        if self.app.settings.ui.mode == "observe":
            return self.toggle_observe()
        return self.toggle_session()

    def toggle_session(self):
        if self.session.running:
            self.session.stop()
            self.refresh_state()
            return None

        self.store()
        self.request_save()

        if not self.session.window.attached:
            messagebox.showwarning(self.t("warn_title"), self.t("warn_window"))
            return None
        if not self.session.ctx.cursors.ready:
            messagebox.showwarning(self.t("warn_title"), self.t("warn_cursor"))
            return None
        if not hunt_maps.model_exists(self.account.hunt_map):
            hunt = hunt_maps.get(self.account.hunt_map)
            messagebox.showwarning(
                self.t("warn_title"),
                self.t("warn_map_model", map=self.translator.map_name(hunt)),
            )
            return None

        zone = monsters.for_real_map(self.account.record.real_map)
        if zone is not None and not zone.has_model and not messagebox.askyesno(
                self.t("warn_title"), self.t("warn_zone_no_model", zone=zone.real_map)):
            return None  # PLAN 0.16: this zone has no model of its own yet -> collect data instead

        started = self.session.start()
        self.refresh_state()
        return started

    def toggle_observe(self):
        """PLAN 0.6 mode 1: record frames + detections, no input. Cursor not needed."""
        if self.session.running:
            self.session.stop()
            self.refresh_state()
            return None
        self.store()
        self.request_save()
        if not self.session.window.attached:
            messagebox.showwarning(self.t("warn_title"), self.t("warn_window"))
            return None
        if not self.account.record.no_model and not hunt_maps.model_exists(self.account.hunt_map):
            hunt = hunt_maps.get(self.account.hunt_map)
            messagebox.showwarning(
                self.t("warn_title"),
                self.t("warn_map_model", map=self.translator.map_name(hunt)),
            )
            return None
        started = self.session.start_observe()
        self.refresh_state()
        return started

    def stop(self):
        self.session.stop()
        self.refresh_state()
