"""Main tab (UI v7): the real hunting zone (record.real_map, PLAN 0.16), moved here from the record panel."""
import tkinter as tk
from tkinter import ttk

from ... import hunt_maps, monsters
from ...config.models import REAL_MAPS
from .base import Panel


class ZonePanel(Panel):
    def build(self):
        self.real_map = tk.StringVar()
        self.frame = ttk.LabelFrame(self.parent, text=" Zone ", padding=6)
        self.frame.pack(fill="x", padx=8, pady=3)
        row = ttk.Frame(self.frame)
        row.pack(fill="x")
        self.lbl_real_map = ttk.Label(row, text="")
        self.lbl_real_map.pack(side="left")
        # Zones with a monster catalog (data/monsters/*.json) first, then the older plain names; typing is allowed.
        zones = monsters.zone_names()  # PLAN 0.37: by monster kind
        self.combo_map = ttk.Combobox(row, textvariable=self.real_map,
                                      values=zones + tuple(m for m in REAL_MAPS if m not in zones), width=30)
        self.combo_map.pack(side="left", fill="x", expand=True, padx=4)
        self.combo_map.bind("<<ComboboxSelected>>", lambda _e: self._zone_selected())
        self.combo_map.bind("<FocusOut>", lambda _e: self.tab.request_save())
        self.lbl_info = ttk.Label(self.frame, text="", foreground="gray", wraplength=380)
        self.lbl_info.pack(anchor="w")

    def load(self):
        self.real_map.set(self.account.record.real_map)

    def store(self):
        self.account.record.real_map = self.real_map.get().strip()

    def _zone_selected(self):
        """PLAN 0.16: a zone points to its catalog + model; without a model -> data collection (no model)."""
        self.store()
        zone = monsters.for_real_map(self.real_map.get())
        self.lbl_info.config(text="")
        if zone is not None and not zone.has_model:
            self.tab.record.no_model.set(True)
            self.lbl_info.config(text=self.t("rec_zone_collect"))
        elif zone is not None:
            # a zone that got its model drops the "no model" box ticked back when it had none
            self.tab.record.no_model.set(False)
            if zone.hunt_map != hunt_maps.base_key(self.account.hunt_map):  # PLAN 0.36: keep a chosen variant
                self.account.hunt_map = zone.hunt_map
                self.tab.hunt_map.load()
                self.tab.scan.load_model()
        self.tab.request_save()

    def apply_language(self):
        self.frame.config(text=f" {self.t('sec_zone')} ")
        self.lbl_real_map.config(text=self.t("rec_real_map"))

    def set_busy(self, running):
        self.combo_map.config(state="disabled" if running else "normal")
