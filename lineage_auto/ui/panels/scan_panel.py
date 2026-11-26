"""Target scan tuning (AccountSettings.scan, PLAN 0.1)."""
import tkinter as tk
from tkinter import ttk

from ... import hunt_maps
from ...config.models import HUNT_RANGES, INPUT_SIZES, MAX_PROBE_POINTS
from .base import Panel

# (settings field, i18n key, from, to, step, ui scale). Timings in ms, conf in 1/100;
# a tuple instead of a step = the only allowed values.
FIELDS = (
    ("misses_before_wander", "scan_misses", 1, 10, 1, 1),
    ("max_probe_points", "scan_points", 1, MAX_PROBE_POINTS, 1, 1),
    ("hunt_range", "scan_range", 0, HUNT_RANGES[-1], HUNT_RANGES, 1),  # PLAN 1.2
    ("miss_ttl", "scan_miss_ttl", 0, 30, 1, 1),
    ("hover_settle", "scan_settle_ms", 0, 300, 10, 1000),
    ("hover_retry", "scan_retry_ms", 0, 300, 10, 1000),
    ("hover_reads", "scan_reads", 1, 6, 1, 1),
    ("detect_conf", "scan_conf", 0, 50, 1, 100),
    ("detect_fps", "scan_fps", 1, 15, 1, 1),  # PLAN 0.31
    ("input_size", "scan_input", INPUT_SIZES[0], INPUT_SIZES[-1], INPUT_SIZES, 1),
    ("detect_roi", "scan_roi", 0, 1, 1, 1),
    ("detect_threads", "scan_threads", 1, 8, 1, 1),  # PLAN 0.33: onnxruntime intra_op threads
    ("search_threads", "scan_search_threads", 1, 8, 1, 1),  # PLAN 0.34
    ("adaptive_detect", "scan_adaptive", 0, 1, 1, 1),
    ("melee_max_sec", "scan_melee_max", 5, 120, 1, 1),
)


# Shown at once; the rest (timings, threshold) sits in the collapsed "Advanced" box (UI v7).
BASIC = ("misses_before_wander", "max_probe_points", "hunt_range")


class ScanPanel(Panel):
    def build(self):
        self.vars = {}
        self.labels = {}
        self.spins = []
        self.frame = ttk.LabelFrame(self.parent, text=" Scan ", padding=6)
        self.frame.pack(fill="x", padx=8, pady=3)
        basic = ttk.Frame(self.frame)
        basic.pack(fill="x")
        self.btn_adv = ttk.Button(self.frame, text="", command=self.toggle_advanced)
        self.btn_adv.pack(anchor="w", pady=(4, 0))
        self.advanced = ttk.Frame(self.frame)
        self._adv_open = False
        rows = {"basic": 0, "adv": 0}
        for name, key, lo, hi, step, _scale in FIELDS:
            where = "basic" if name in BASIC else "adv"
            parent = basic if where == "basic" else self.advanced
            row = rows[where]
            rows[where] += 1
            self.vars[name] = tk.IntVar()
            self.labels[key] = ttk.Label(parent, text="")
            self.labels[key].grid(row=row, column=0, sticky="w", padx=(0, 6))
            span = (dict(values=step) if isinstance(step, tuple)
                    else dict(from_=lo, to=hi, increment=step))
            spin = ttk.Spinbox(parent, width=5, textvariable=self.vars[name], command=self.tab.request_save, **span)
            spin.grid(row=row, column=1, sticky="w", pady=1)
            self.spins.append(spin)
        # PLAN 0.36: which model of this ground (orc_v1 / orc_v2), switchable without a new build
        self.model = tk.StringVar()
        self.labels["scan_model"] = ttk.Label(self.advanced, text="")
        self.labels["scan_model"].grid(row=rows["adv"], column=0, sticky="w", padx=(0, 6))
        self.combo_model = ttk.Combobox(self.advanced, textvariable=self.model, state="readonly", width=8)
        self.combo_model.grid(row=rows["adv"], column=1, sticky="w", pady=1)
        self.combo_model.bind("<<ComboboxSelected>>", self._on_model)

    def load_model(self):
        options = hunt_maps.variants(self.account.hunt_map)
        self.combo_model["values"] = [m.variant or m.key for m in options]
        hunt = hunt_maps.get(self.account.hunt_map)
        self.model.set(hunt.variant or hunt.key)
        self.combo_model.config(state="readonly" if len(options) > 1 else "disabled")

    def _on_model(self, _event=None):
        for m in hunt_maps.variants(self.account.hunt_map):
            if (m.variant or m.key) == self.model.get():
                self.account.hunt_map = m.key
        self.load()
        self.tab.request_save()

    def toggle_advanced(self):
        self._adv_open = not self._adv_open
        if self._adv_open:
            self.advanced.pack(fill="x", pady=(2, 0), after=self.btn_adv)
        else:
            self.advanced.pack_forget()
        self.btn_adv.config(text=("▾ " if self._adv_open else "▸ ") + self.t("scan_advanced"))

    def load(self):
        scan = self.account.scan
        for name, _key, _lo, _hi, _step, scale in FIELDS:
            value = scan.conf_for(self.account.hunt_map) if name == "detect_conf" else getattr(scan, name)
            self.vars[name].set(int(round(value * scale)))
        self.load_model()

    def store(self):
        scan = self.account.scan
        for name, _key, lo, hi, step, scale in FIELDS:
            try:
                value = min(hi, max(lo, int(self.vars[name].get())))
            except (tk.TclError, ValueError):
                continue  # half-typed box: keep the saved value
            if isinstance(step, tuple):
                value = min(step, key=lambda v: abs(v - value))  # typed by hand: nearest allowed value
            value = value / scale if scale != 1 else type(getattr(scan, name))(value)
            if name == "detect_conf":
                if value == scan.conf_for(self.account.hunt_map):
                    continue  # untouched: keep following the zone's threshold
                scan.conf_map = self.account.hunt_map  # PLAN 0.27: typed for this hunting ground only
            setattr(scan, name, value)

    def apply_language(self):
        self.frame.config(text=f" {self.t('sec_scan')} ")
        for _name, key, *_ in FIELDS:
            self.labels[key].config(text=self.t(key))
        self.labels["scan_model"].config(text=self.t("scan_model"))
        self.btn_adv.config(text=("▾ " if self._adv_open else "▸ ") + self.t("scan_advanced"))

    def set_busy(self, running):
        for spin in self.spins:
            spin.config(state="disabled" if running else "normal")
        if running:
            self.combo_model.config(state="disabled")
        else:
            self.load_model()
