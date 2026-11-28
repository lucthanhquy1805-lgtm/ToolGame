"""Main tab (UI v7): what the big Start button does (hunt / observe), state, kills, run time, warnings."""
import time
import tkinter as tk
from tkinter import ttk

from ... import hunt_maps, monsters
from .base import Panel
from .control_panel import STATE_LABELS

# PLAN 1.10: worst-case cost of one cursor read, over which the UI says so. The shipped default is
# 0.04 + 3 x 0.04 = 160 ms; the G1RN30H config (6 reads / 50 ms settle) is 250 ms, x max_probe_points a scan.
HOVER_SLOW_MS = 200


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
        # PLAN 1.10 B6: where the model runs + how fast + the attack range in use (the game PC has no console).
        self.lbl_detect = ttk.Label(self.frame, text="", foreground="gray")
        self.lbl_detect.pack(anchor="w", pady=(2, 0))
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
            # PLAN 1.10 B6: a CPU-only machine at input 640 costs ~80-140 ms per detect (PLAN 0.48 table) and
            # the game stutters. Not lowered automatically: 0.32/0.39 measured that 416 loses ~1/4 of the boxes.
            info = session.ctx.state.get("detect_info") or {}
            device = info.get("device") or ""
            if device and "dml" not in device.lower() and self.account.scan.input_size >= 640:
                out.append(self.t("wline_cpu640", ms=int(info.get("ms") or 0)))
            # PLAN 1.10: "no model" saved while the chosen ground HAS one - observe mode then skips the
            # detector entirely and nothing on screen tied it back to this box (G1RN30H, 28/11).
            if self.account.record.no_model and hunt_maps.model_exists(self.account.hunt_map):
                out.append(self.t("wline_no_model_off"))
            # PLAN 1.10: one hover costs hover_settle + (hover_reads - 1) x hover_retry, and a scan pays it
            # per probe point (_hash_after_hover stops early on a sword, so this is the worst case).
            scan = self.account.scan
            hover_ms = 1000 * (scan.hover_settle + max(0, scan.hover_reads - 1) * scan.hover_retry)
            if hover_ms > HOVER_SLOW_MS:
                out.append(self.t("wline_hover_slow", ms=int(hover_ms), n=scan.max_probe_points))
        zone = monsters.for_real_map(self.account.record.real_map)
        if zone is not None and not zone.has_model:
            out.append(self.t("wline_zone", zone=zone.real_map))
        return out

    def detect_line(self):
        """PLAN 1.10 B6: "Detect: GPU/CPU - 44 ms - attack range 15 steps"."""
        info = self.tab.session.ctx.state.get("detect_info") or {}
        device = info.get("device") or ""
        where = "GPU" if "dml" in device.lower() or "cuda" in device.lower() else "CPU" if device else "-"
        ms = info.get("ms")
        line = self.t("status_detect", where=where, ms="-" if ms is None else int(ms),
                      steps=self.account.attack_steps())
        # PLAN 1.10 B8: hunt range 0 has no start point, so nothing ever walks back - say so, it is a choice.
        return line + "  ·  " + self.t("status_free_hunt" if not self.account.scan.hunt_range
                                       else "status_home_range", steps=self.account.scan.hunt_range)

    def update_status(self):
        session = self.tab.session
        key, colour = STATE_LABELS.get(session.state, ("state_stopped", "gray"))
        self.lbl_state.config(text=self.t(key), foreground=colour)
        self.lbl_kills.config(text=self.t("status_kills", n=session.ctx.state.get("kills", 0)))
        start = session.started_at if session.running else None
        self.lbl_time.config(text=self.t("status_time", t=format_duration(time.monotonic() - start) if start else "-"))
        self.lbl_detect.config(text=self.detect_line())
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
