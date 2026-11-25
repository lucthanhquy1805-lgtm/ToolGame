"""Choose the hunt map whose YOLOX weights this account will load."""
import tkinter as tk
from tkinter import ttk

from ... import hunt_maps, monsters
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
        hunt = hunt_maps.get(hunt_maps.base_key(self.account.hunt_map))  # a model variant shows its ground
        self.selected.set(self.tab.translator.map_name(hunt))

    def store(self):
        label = self.selected.get()
        for hunt in hunt_maps.all_maps():
            if self.tab.translator.map_name(hunt) == label:
                if hunt.key != hunt_maps.base_key(self.account.hunt_map):  # same ground: keep the chosen model
                    self.account.hunt_map = hunt.key
                    # PLAN 0.39 / 7: the zone (chat kill lines, names) follows the ground picked here
                    zone = monsters.for_real_map(self.account.record.real_map)
                    new = monsters.for_hunt_map(hunt.key)
                    if new is not None and (zone is None or zone.hunt_map != hunt.key):
                        self.account.record.real_map = new.zone_name
                        zone_panel = getattr(self.tab, "zone", None)
                        if zone_panel is not None:
                            zone_panel.load()
                return

    def _on_pick(self, _event=None):
        self.store()
        self.tab.request_save()
        self.tab.scan.load_model()
        self.tab.notify_map_selected()

    def apply_language(self):
        self.frame.config(text=f" {self.t('sec_map')} ")
        self.lbl_map.config(text=self.t("map_label"))
        self.load()

    def set_busy(self, running):
        self.combo.config(state="disabled" if running else "readonly")
