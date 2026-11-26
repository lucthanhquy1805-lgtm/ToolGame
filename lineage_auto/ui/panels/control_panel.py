"""Bottom bar, always visible outside the tabs (UI v7): big Start/Stop for the mode chosen on the Main tab,
a separate Observe button, live HP/MP, short state, stop-key hint."""
import tkinter as tk
from tkinter import ttk

from ... import hunt_maps
from ...runtime.session import SessionState
from .base import Panel

STATE_LABELS = {
    SessionState.STOPPED: ("state_stopped", "gray"),
    SessionState.RUNNING: ("state_running", "green"),
    SessionState.OBSERVING: ("state_observing", "#1565c0"),
    SessionState.DEAD: ("state_dead", "#c62828"),
    SessionState.HUD_LOST: ("state_hud_lost", "#f9a825"),
    SessionState.RETURNED: ("state_returned", "#e65100"),
    SessionState.ERROR: ("state_error", "#c62828"),
}


class ControlPanel(Panel):
    def build(self):
        self.frame = ttk.Frame(self.parent, padding=(8, 4, 8, 6))
        self.frame.pack(side="bottom", fill="x")
        ttk.Separator(self.frame).pack(fill="x", pady=(0, 4))

        buttons = ttk.Frame(self.frame)
        buttons.pack(fill="x")
        self.button = tk.Button(
            buttons, text="Start", bg="#4CAF50", fg="white",
            font=("Segoe UI", 12, "bold"), height=1, command=self.tab.run_selected,
        )
        self.button.pack(side="left", fill="x", expand=True)
        self.btn_observe = tk.Button(buttons, text="Observe", bg="#1565c0", fg="white",
                                     font=("Segoe UI", 10, "bold"), width=12, command=self.tab.toggle_observe)
        self.btn_observe.pack(side="left", fill="y", padx=(6, 0))

        live = ttk.Frame(self.frame)
        live.pack(fill="x", pady=(4, 0))
        self.lbl_live = ttk.Label(live, text="", foreground="#c62828", font=("Segoe UI", 10, "bold"))
        self.lbl_live.pack(side="left")
        self.lbl_mp_live = ttk.Label(live, text="", foreground="#1565c0", font=("Segoe UI", 10, "bold"))
        self.lbl_mp_live.pack(side="left", padx=(12, 0))
        self.lbl_state = ttk.Label(live, text="", foreground="gray")
        self.lbl_state.pack(side="right")
        self.lbl_esc = ttk.Label(self.frame, text="", foreground="gray", wraplength=420)
        self.lbl_esc.pack(anchor="w")
        # PLAN 0.32: without the game minimap the bot cannot score directions; say so while it hunts.
        self.lbl_warn = ttk.Label(self.frame, text="", foreground="#e65100", wraplength=420)
        self.lbl_warn.pack(anchor="w")

    def show_hp(self, percent, value=None):
        if percent is None:
            self.lbl_live.config(text=self.t("hp_idle"))
        elif value:  # PLAN 0.15: "HP 156/190 (82%)" when the HUD text was read
            self.lbl_live.config(text=f"HP {value[0]}/{value[1]} ({percent}%)")
        else:
            self.lbl_live.config(text=self.t("hp_live", hp=percent))

    def show_mp(self, percent, value=None):
        if percent is None:
            self.lbl_mp_live.config(text=self.t("mp_idle"))
        elif value:
            self.lbl_mp_live.config(text=f"MP {value[0]}/{value[1]} ({percent}%)")
        else:
            self.lbl_mp_live.config(text=self.t("mp_live", mp=percent))

    def show_state(self, state, running):
        try:
            # The widget may already be destroyed while the app is closing.
            observing = running and state == SessionState.OBSERVING
            if running:
                self.button.config(text=self.t("stop"), bg="#F44336")
            else:
                mode = self.tab.app.settings.ui.mode
                self.button.config(text=self.t("start_observe" if mode == "observe" else "start_hunt"), bg="#4CAF50")
            self.btn_observe.config(text=self.t("bar_observe_stop" if observing else "bar_observe"),
                                    state="disabled" if running and not observing else "normal")
            key, colour = STATE_LABELS.get(state, ("state_stopped", "gray"))
            self.lbl_state.config(text=self.t(key), foreground=colour)
            warnings = []
            if running and self.tab.session.ctx.state.get("minimap") is False:
                # PLAN 1.2: without the minimap there is no position, so the hunt range cannot work at all.
                warnings.append(self.t("warn_range_minimap" if self.account.scan.hunt_range
                                       else "warn_no_minimap"))
            # PLAN 0.40: on an MP-hungry ground the heal spell empties the MP bar (20261126_101941: 84 -> 2 %).
            if hunt_maps.get(self.account.hunt_map).mp_hungry and not any(
                    p.enabled and p.stat == "mp" for p in self.account.health.potions):
                warnings.append(self.t("warn_no_mp_potion"))
            # PLAN 0.34: without the aiming cursor the bot cannot tell an armed spell from a dead key press.
            if self.account.cast_order != "click_key" and any(
                    self.account.attack(k).enabled for k in self.account.attack_skills
            ) and not self.tab.session.ctx.cursors.is_registered("cast"):
                warnings.append(self.t("warn_no_cast_cursor"))
            self.lbl_warn.config(text="  ".join(warnings))
        except tk.TclError:
            return

    def apply_language(self):
        self.lbl_esc.config(text=self.t("bar_hint"))
        self.show_hp(self.tab.last_hp, self.tab.session.ctx.state.get("hp_abs") if self.tab.last_hp is not None else None)
        self.show_mp(self.tab.last_mp, self.tab.session.ctx.state.get("mp_abs") if self.tab.last_mp is not None else None)
        self.show_state(self.tab.session.state, self.tab.session.running)
