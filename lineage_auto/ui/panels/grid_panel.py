"""Hunt tab (UI v7): grid cursor scan (record.grid_*, PLAN 0.6, moved from the record panel) and the
place kept for the hunting range (PLAN 1.2)."""
import tkinter as tk
from tkinter import ttk

from .base import Panel


class GridPanel(Panel):
    def build(self):
        self.grid_scan = tk.BooleanVar(value=False)
        self.grid_step = tk.IntVar(value=40)
        self.grid_radius = tk.IntVar(value=200)
        save = self.tab.request_save

        self.frame = ttk.LabelFrame(self.parent, text=" Grid ", padding=6)
        self.frame.pack(fill="x", padx=8, pady=3)
        self.chk_grid = ttk.Checkbutton(self.frame, text="", variable=self.grid_scan, command=save)
        self.chk_grid.pack(anchor="w")
        row = ttk.Frame(self.frame)
        row.pack(fill="x")
        self.lbl_grid_step = ttk.Label(row, text="")
        self.lbl_grid_step.pack(side="left")
        self.spin_grid_step = ttk.Spinbox(row, from_=10, to=200, increment=10, width=4,
                                          textvariable=self.grid_step, command=save)
        self.spin_grid_step.pack(side="left", padx=4)
        self.lbl_grid_radius = ttk.Label(row, text="")
        self.lbl_grid_radius.pack(side="left", padx=(12, 0))
        self.spin_grid_radius = ttk.Spinbox(row, from_=40, to=600, increment=20, width=4,
                                            textvariable=self.grid_radius, command=save)
        self.spin_grid_radius.pack(side="left", padx=4)


    def load(self):
        rec = self.account.record
        self.grid_scan.set(rec.grid_scan)
        self.grid_step.set(rec.grid_step)
        self.grid_radius.set(rec.grid_radius)

    def store(self):
        rec = self.account.record
        rec.grid_scan = bool(self.grid_scan.get())
        try:
            rec.grid_step = max(10, min(200, int(self.grid_step.get())))
            rec.grid_radius = max(40, min(600, int(self.grid_radius.get())))
        except (tk.TclError, ValueError):
            pass  # half-typed box: keep the saved value

    def apply_language(self):
        self.frame.config(text=f" {self.t('sec_grid')} ")
        self.chk_grid.config(text=self.t("rec_grid"))
        self.lbl_grid_step.config(text=self.t("rec_grid_step"))
        self.lbl_grid_radius.config(text=self.t("rec_grid_radius"))

    def set_busy(self, running):
        for widget in (self.chk_grid, self.spin_grid_step, self.spin_grid_radius):
            widget.config(state="disabled" if running else "normal")
