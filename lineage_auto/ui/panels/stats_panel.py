"""Statistics tab (PLAN 4.1): what this run / this day did.

Read-only: every value comes from ``BotContext.stats`` (runtime/stats.py), refreshed on the UI poll.
The same numbers are written to records/stats_<date>.json every 10 minutes by the session.
"""
import tkinter as tk
from tkinter import ttk

from ...runtime.stats import KEYS
from .base import Panel


def format_runtime(seconds):
    seconds = int(seconds)
    return f"{seconds // 3600}h {seconds % 3600 // 60:02d}m {seconds % 60:02d}s"


class StatsPanel(Panel):
    def build(self):
        self.frame = ttk.LabelFrame(self.parent, text=" Statistics ", padding=6)
        self.frame.pack(fill="x", padx=8, pady=3)

        self.lbl_runtime = ttk.Label(self.frame, text="", font=("Segoe UI", 10, "bold"))
        self.lbl_runtime.pack(anchor="w")
        self.lbl_kills = ttk.Label(self.frame, text="", font=("Segoe UI", 10, "bold"))
        self.lbl_kills.pack(anchor="w")

        self.lbl_monsters_title = ttk.Label(self.frame, text="")
        self.lbl_monsters_title.pack(anchor="w", pady=(6, 0))
        self.monsters = tk.Text(self.frame, height=6, width=46, state="disabled", wrap="none")
        self.monsters.pack(anchor="w", fill="x")

        self.lbl_counts_title = ttk.Label(self.frame, text="")
        self.lbl_counts_title.pack(anchor="w", pady=(6, 0))
        self.counts = tk.Text(self.frame, height=6, width=46, state="disabled", wrap="none")
        self.counts.pack(anchor="w", fill="x")

        self.lbl_file = ttk.Label(self.frame, text="", foreground="gray", wraplength=420)
        self.lbl_file.pack(anchor="w", pady=(6, 0))
        self.refresh()

    def _set(self, widget, text):
        widget.config(state="normal")
        widget.delete("1.0", "end")
        widget.insert("1.0", text)
        widget.config(state="disabled")

    def refresh(self):
        """Called on every UI poll; cheap (plain counters)."""
        try:
            snap = self.tab.session.ctx.stats.snapshot()
            self.lbl_runtime.config(text=self.t("stats_runtime", time=format_runtime(snap["runtime_sec"])))
            self.lbl_kills.config(text=self.t("stats_kills", kills=snap["kills"], per_hour=snap["kills_per_hour"]))
            by_name = snap["kills_by_name"]
            self._set(self.monsters, "\n".join(f"{n}  {c}" for n, c in by_name.items()) or "-")
            counts = snap["counts"]
            rows = [(k, counts[k]) for k in KEYS if counts.get(k)]
            rows += [(k, v) for k, v in counts.items() if k not in KEYS]
            # t() falls back to the key itself, so a counter nobody translated still shows up.
            text = "\n".join(f"{self.t('stats_' + k)}  {v}" for k, v in rows)
            self._set(self.counts, text or "-")
        except tk.TclError:
            return

    def apply_language(self):
        self.frame.config(text=f" {self.t('tab_stats')} ")
        self.lbl_monsters_title.config(text=self.t("stats_by_monster"))
        self.lbl_counts_title.config(text=self.t("stats_counts"))
        self.lbl_file.config(text=self.t("stats_file"))
        self.refresh()
