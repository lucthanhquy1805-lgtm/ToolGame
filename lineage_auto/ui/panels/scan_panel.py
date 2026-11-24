"""Target scan tuning (AccountSettings.scan, PLAN 0.1)."""
import tkinter as tk
from tkinter import ttk

from ...config.models import INPUT_SIZES, MAX_PROBE_POINTS
from .base import Panel

# (settings field, i18n key, from, to, step, ui scale). Timings in ms, conf in 1/100.
FIELDS = (
    ("misses_before_wander", "scan_misses", 1, 10, 1, 1),
    ("max_probe_points", "scan_points", 1, MAX_PROBE_POINTS, 1, 1),
    ("miss_ttl", "scan_miss_ttl", 0, 30, 1, 1),
    ("hover_settle", "scan_settle_ms", 0, 300, 10, 1000),
    ("hover_retry", "scan_retry_ms", 0, 300, 10, 1000),
    ("hover_reads", "scan_reads", 1, 6, 1, 1),
    ("detect_conf", "scan_conf", 0, 50, 1, 100),
    ("detect_fps", "scan_fps", 1, 15, 1, 1),  # PLAN 0.31
    ("input_size", "scan_input", INPUT_SIZES[0], INPUT_SIZES[-1], 0, 1),  # step 0 = one of INPUT_SIZES
    ("detect_roi", "scan_roi", 0, 1, 1, 1),
    ("melee_max_sec", "scan_melee_max", 5, 120, 1, 1),
)


# Shown at once; the rest (timings, threshold) sits in the collapsed "Advanced" box (UI v7).
BASIC = ("misses_before_wander", "max_probe_points")


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
            span = dict(values=INPUT_SIZES) if not step else dict(from_=lo, to=hi, increment=step)
            spin = ttk.Spinbox(parent, width=5, textvariable=self.vars[name], command=self.tab.request_save, **span)
            spin.grid(row=row, column=1, sticky="w", pady=1)
            self.spins.append(spin)

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

    def store(self):
        scan = self.account.scan
        for name, _key, lo, hi, _step, scale in FIELDS:
            try:
                value = min(hi, max(lo, int(self.vars[name].get())))
            except (tk.TclError, ValueError):
                continue  # half-typed box: keep the saved value
            if name == "input_size":
                value = min(INPUT_SIZES, key=lambda v: abs(v - value))  # typed by hand: nearest exported size
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
        self.btn_adv.config(text=("▾ " if self._adv_open else "▸ ") + self.t("scan_advanced"))

    def set_busy(self, running):
        for spin in self.spins:
            spin.config(state="disabled" if running else "normal")
