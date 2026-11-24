"""Main tab (UI v7): what the big Start button does (hunt / observe), state, kills, run time, warnings."""
import time
import tkinter as tk
from tkinter import ttk

from ... import hunt_maps, monsters
from .base import Panel
from .control_panel import STATE_LABELS


def format_duration(seconds):
    seconds = int(max(0, seconds))
    return f"{seconds // 3600}:{seconds // 60 % 60:02d}:{seconds % 60:02d}"


class StatusPanel(Panel):
    def build(self):
        self.mode = tk.StringVar(value="hunt")
        self.frame = ttk.LabelFrame(self.parent, text=" Status ", padding=6)
        self.frame.pack(fill="x", padx=8, pady=3)
        row = ttk.Frame(self.frame)
        row.pack(fill="x")
        self.lbl_mode = ttk.Label(row, text="")
        self.lbl_mode.pack(side="left")
        self.radios = {}
        for value in ("hunt", "observe"):
            radio = ttk.Radiobutton(row, variable=self.mode, value=value, command=self._mode_changed)
            radio.pack(side="left", padx=6)
            self.radios[value] = radio
        info = ttk.Frame(self.frame)
        info.pack(fill="x", pady=(4, 0))
        self.lbl_state = ttk.Label(info, text="")
        self.lbl_state.pack(side="left")
        self.lbl_time = ttk.Label(info, text="", foreground="gray")
        self.lbl_time.pack(side="right")
        self.lbl_kills = ttk.Label(info, text="", foreground="gray")
        self.lbl_kills.pack(side="right", padx=10)
        self.lbl_warn = ttk.Label(self.frame, text="", foreground="#c62828", wraplength=380, justify="left")
        self.lbl_warn.pack(anchor="w", pady=(4, 0))

    @property
    def ui(self):
        return self.tab.app.settings.ui

    def load(self):
        self.mode.set(self.ui.mode)

    def store(self):
        self.ui.mode = self.mode.get()

    def _mode_changed(self):
        self.store()
        self.tab.request_save()
        self.tab.control.show_state(self.tab.session.state, self.tab.session.running)

    def warnings(self):
        """Short lines for what blocks or weakens a run. Empty = all good."""
        session = self.tab.session
        out = []
        if not session.window.attached:
            out.append(self.t("wline_window"))
        if self.mode.get() == "hunt":
            if not session.ctx.cursors.ready:
                out.append(self.t("wline_cursor"))
            if not hunt_maps.model_exists(self.account.hunt_map):
                out.append(self.t("wline_model", map=self.tab.translator.map_name(hunt_maps.get(self.account.hunt_map))))
            if not self.tab.app.manager.input_trusted:
                out.append(self.t("wline_driver"))
        zone = monsters.for_real_map(self.account.record.real_map)
        if zone is not None and not zone.has_model:
            out.append(self.t("wline_zone", zone=zone.real_map))
        return out

    def update_status(self):
        session = self.tab.session
        key, colour = STATE_LABELS.get(session.state, ("state_stopped", "gray"))
        self.lbl_state.config(text=self.t(key), foreground=colour)
        self.lbl_kills.config(text=self.t("status_kills", n=session.ctx.state.get("kills", 0)))
        start = session.started_at if session.running else None
        self.lbl_time.config(text=self.t("status_time", t=format_duration(time.monotonic() - start) if start else "-"))
        warns = self.warnings()
        self.lbl_warn.config(text="\n".join(warns) or self.t("status_no_warn"),
                             foreground="#c62828" if warns else "green")
        return warns

    def apply_language(self):
        self.frame.config(text=f" {self.t('sec_status')} ")
        self.lbl_mode.config(text=self.t("sec_mode"))
        self.radios["hunt"].config(text=self.t("mode_hunt"))
        self.radios["observe"].config(text=self.t("mode_observe"))
        self.update_status()

    def set_busy(self, running):
        for radio in self.radios.values():
            radio.config(state="disabled" if running else "normal")
