"""Drops after each kill (AccountSettings.loot, PLAN 1.5 + 0.27 / 7): pick-up mode, key, auto-detect button."""
import tkinter as tk
from tkinter import ttk

from ...characters.base import HOTKEYS
from ...config.models import LOOT_MODES
from ...features.loot import MIN_KILLS_TO_SUGGEST, suggest_mode
from .base import Panel

LOOT_KEYS = ("F4",) + tuple(HOTKEYS)


class LootPanel(Panel):
    def build(self):
        self.mode = tk.StringVar(value="")
        self.key = tk.StringVar(value="F4")
        self.presses = tk.IntVar(value=2)
        self.result = tk.StringVar(value="")

        self.frame = ttk.LabelFrame(self.parent, text=" Loot ", padding=6)
        self.frame.pack(fill="x", padx=8, pady=3)
        row = ttk.Frame(self.frame)
        row.pack(fill="x")
        self.lbl_mode = ttk.Label(row, text="")
        self.lbl_mode.pack(side="left")
        self.cmb_mode = ttk.Combobox(row, textvariable=self.mode, width=26, state="readonly")
        self.cmb_mode.pack(side="left", padx=6)
        self.cmb_mode.bind("<<ComboboxSelected>>", lambda _e: self.tab.request_save())
        row2 = ttk.Frame(self.frame)
        row2.pack(fill="x", pady=(3, 0))
        ttk.Combobox(row2, textvariable=self.key, values=LOOT_KEYS, width=5, state="readonly").pack(side="left")
        ttk.Label(row2, text="×").pack(side="left", padx=(6, 0))
        ttk.Spinbox(
            row2, from_=1, to=10, increment=1, textvariable=self.presses,
            width=4, command=self.tab.request_save,
        ).pack(side="left", padx=4)
        self.btn_detect = ttk.Button(row2, text="", command=self.detect)
        self.btn_detect.pack(side="left", padx=(10, 0))
        ttk.Label(self.frame, textvariable=self.result, foreground="#555", wraplength=380).pack(anchor="w")

    def _labels(self):
        return [self.t(f"loot_mode_{m}") for m in LOOT_MODES]

    def load(self):
        loot = self.account.loot
        self.mode.set(self.t(f"loot_mode_{loot.mode}"))
        self.key.set(loot.key)
        self.presses.set(loot.presses)

    def store(self):
        loot = self.account.loot
        labels = self._labels()
        if self.mode.get() in labels:
            loot.mode = LOOT_MODES[labels.index(self.mode.get())]
            loot.enabled = loot.mode != "auto"
        loot.key = self.key.get()
        try:
            loot.presses = min(10, max(1, int(self.presses.get())))
        except (tk.TclError, ValueError):
            pass  # half-typed box: keep the saved value

    def detect(self):
        """Suggest the mode from the kills of the running (or last) hunt: kill lines at the kill = auto."""
        session = getattr(self.tab, "session", None)
        if session is None:
            return
        if getattr(session.targeting, "kill_watch", None) is None:
            self.result.set(self.t("loot_detect_nochat"))
            return
        n = session.ctx.state.get("kills", 0)
        c = session.ctx.state.get("kills_chat", 0)
        mode = suggest_mode(n, c)
        if mode is None:
            self.result.set(self.t("loot_detect_none", n=n, min=MIN_KILLS_TO_SUGGEST))
            return
        self.result.set(self.t(f"loot_detect_{'auto' if mode == 'auto' else 'walk'}", n=n, c=c))
        self.mode.set(self.t(f"loot_mode_{mode}"))
        self.tab.request_save()

    def apply_language(self):
        self.frame.config(text=f" {self.t('sec_loot')} ")
        self.lbl_mode.config(text=self.t("loot_mode"))
        self.btn_detect.config(text=self.t("loot_detect"))
        self.cmb_mode.config(values=self._labels())
        self.mode.set(self.t(f"loot_mode_{self.account.loot.mode}"))

    def set_busy(self, running):
        self.cmb_mode.config(state="disabled" if running else "readonly")
