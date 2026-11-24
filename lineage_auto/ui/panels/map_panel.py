"""Choose the hunt map whose YOLOX weights this account will load."""
import tkinter as tk
from tkinter import ttk

from ... import hunt_maps
from .base import Panel


class MapPanel(Panel):
    def build(self):
        self.selected = tk.StringVar()

        self.frame = ttk.LabelFrame(self.parent, text=" Map ", padding=6)
        self.frame.pack(fill="x", padx=8, pady=3)

        row = ttk.Frame(self.frame)
        row.pack(fill="x")
        self.lbl_map = ttk.Label(row, text="")
        self.lbl_map.pack(side="left")
        self.combo = ttk.Combobox(
            row, textvariable=self.selected, state="readonly", width=28
        )
        self.combo.pack(side="left", fill="x", expand=True, padx=8)
        self.combo.bind("<<ComboboxSelected>>", self._on_pick)

    def _labels(self):
        return [self.tab.translator.map_name(m) for m in hunt_maps.all_maps()]

    def load(self):
        self.combo["values"] = self._labels()
        hunt = hunt_maps.get(self.account.hunt_map)
        self.selected.set(self.tab.translator.map_name(hunt))

    def store(self):
        label = self.selected.get()
        for hunt in hunt_maps.all_maps():
            if self.tab.translator.map_name(hunt) == label:
                self.account.hunt_map = hunt.key
                return

    def _on_pick(self, _event=None):
        self.store()
        self.tab.request_save()
        self.tab.notify_map_selected()

    def apply_language(self):
        self.frame.config(text=f" {self.t('sec_map')} ")
        self.lbl_map.config(text=self.t("map_label"))
        self.load()

    def set_busy(self, running):
        self.combo.config(state="disabled" if running else "readonly")
