"""Field data recording (PLAN 0.6): observe-only mode, record while hunting, zip.
Also the remote-safe stop options (PLAN 0.7): auto stop minutes and the second stop key.
UI v7: the zone (real_map) lives in ZonePanel (Main tab), the grid scan in GridPanel (Hunt tab)."""
import os
import tkinter as tk
from tkinter import messagebox, ttk

from ...config.models import STOP_KEYS
from ...runtime import recorder
from ...runtime.session import SessionState
from .base import Panel


class RecordPanel(Panel):
    def build(self):
        self.while_hunting = tk.BooleanVar(value=False)
        self.interval = tk.IntVar(value=3)
        self.max_frames = tk.IntVar(value=0)
        self.no_model = tk.BooleanVar(value=False)
        self.auto_stop = tk.IntVar(value=0)
        self.max_gb = tk.IntVar(value=5)
        self.stop_key = tk.StringVar(value="Pause")
        save = self.tab.request_save

        self.frame = ttk.LabelFrame(self.parent, text=" Record ", padding=6)
        self.frame.pack(fill="x", padx=8, pady=3)

        self.chk_hunt = ttk.Checkbutton(self.frame, text="", variable=self.while_hunting, command=save)
        self.chk_hunt.pack(anchor="w")
        top = ttk.Frame(self.frame)
        top.pack(fill="x", pady=(4, 0))
        self.lbl_interval = ttk.Label(top, text="")
        self.lbl_interval.pack(side="left")
        self.spin_interval = ttk.Spinbox(top, from_=1, to=60, width=4, textvariable=self.interval, command=save)
        self.spin_interval.pack(side="left", padx=4)
        self.lbl_max = ttk.Label(top, text="")
        self.lbl_max.pack(side="left", padx=(12, 4))
        self.spin_max = ttk.Spinbox(top, from_=0, to=5000, increment=50, width=6, textvariable=self.max_frames,
                                    command=save)
        self.spin_max.pack(side="left")
        self.lbl_max_auto = ttk.Label(top, text="", foreground="gray")  # "0" = automatic, shows the number
        self.lbl_max_auto.pack(side="left", padx=(4, 0))
        row_gb = ttk.Frame(self.frame)  # PLAN 0.38: oldest recordings are deleted past this
        row_gb.pack(fill="x", pady=(4, 0))
        self.lbl_max_gb = ttk.Label(row_gb, text="")
        self.lbl_max_gb.pack(side="left")
        self.spin_max_gb = ttk.Spinbox(row_gb, from_=1, to=500, width=4, textvariable=self.max_gb, command=save)
        self.spin_max_gb.pack(side="left", padx=4)
        self.chk_no_model = ttk.Checkbutton(self.frame, text="", variable=self.no_model, command=save)
        self.chk_no_model.pack(anchor="w", pady=(4, 0))

        self.stop_frame = ttk.LabelFrame(self.parent, text=" Stop ", padding=6)
        self.stop_frame.pack(fill="x", padx=8, pady=3)
        row_stop = ttk.Frame(self.stop_frame)
        row_stop.pack(fill="x")
        self.lbl_auto_stop = ttk.Label(row_stop, text="")
        self.lbl_auto_stop.pack(side="left")
        self.spin_auto_stop = ttk.Spinbox(row_stop, from_=0, to=600, increment=5, width=4,
                                          textvariable=self.auto_stop, command=save)
        self.spin_auto_stop.pack(side="left", padx=4)
        row_key = ttk.Frame(self.stop_frame)
        row_key.pack(fill="x", pady=(4, 0))
        self.lbl_stop_key = ttk.Label(row_key, text="")
        self.lbl_stop_key.pack(side="left")
        self.combo_stop_key = ttk.Combobox(row_key, textvariable=self.stop_key, values=tuple(STOP_KEYS),
                                           state="readonly", width=10)
        self.combo_stop_key.pack(side="left", padx=4)
        self.combo_stop_key.bind("<<ComboboxSelected>>", lambda _e: save())

        self.files_frame = ttk.LabelFrame(self.parent, text=" Files ", padding=6)
        self.files_frame.pack(fill="x", padx=8, pady=3)
        bottom = ttk.Frame(self.files_frame)
        bottom.pack(fill="x")
        self.btn_observe = ttk.Button(bottom, text="", command=self.tab.toggle_observe)
        self.btn_observe.pack(side="left")
        self.btn_zip = ttk.Button(bottom, text="", command=self._zip_latest)
        self.btn_zip.pack(side="left", padx=6)
        self.lbl_info = ttk.Label(self.files_frame, text="", foreground="gray", wraplength=380)
        self.lbl_info.pack(anchor="w", pady=(4, 0))
        self.lbl_last = ttk.Label(self.files_frame, text="", foreground="gray", wraplength=380, justify="left")
        self.lbl_last.pack(anchor="w")

    def load(self):
        rec = self.account.record
        self.while_hunting.set(rec.while_hunting)
        self.interval.set(int(rec.interval_sec))
        self.max_frames.set(rec.max_frames)
        self._show_cap()
        self.no_model.set(rec.no_model)
        self.auto_stop.set(rec.auto_stop_min)
        self.max_gb.set(int(round(rec.max_gb)))
        self.stop_key.set(rec.stop_key)

    def store(self):
        rec = self.account.record
        rec.while_hunting = bool(self.while_hunting.get())
        rec.no_model = bool(self.no_model.get())
        if self.stop_key.get() in STOP_KEYS:
            rec.stop_key = self.stop_key.get()
        try:
            rec.interval_sec = float(max(1, min(60, int(self.interval.get()))))
            frames = int(self.max_frames.get())
            rec.max_frames = 0 if frames <= 0 else max(10, min(5000, frames))
            rec.auto_stop_min = max(0, min(600, int(self.auto_stop.get())))
            rec.max_gb = float(max(1, min(500, int(self.max_gb.get()))))
        except (tk.TclError, ValueError):
            pass  # half-typed box: keep the saved value
        self._show_cap()

    def _show_cap(self):
        rec = self.account.record
        cap = rec.frame_cap()
        self.lbl_max_auto.config(text=self.t("rec_max_auto", n="∞" if cap is None else cap) if rec.max_frames == 0 else "")

    def show_last(self):
        path = recorder.latest_record()
        self.lbl_last.config(text=self.t("rec_last", path=path) if path else self.t("rec_last_none"))

    def _zip_latest(self):
        path = recorder.latest_record()
        if path is None:
            messagebox.showinfo(self.t("warn_title"), self.t("rec_none"))
            return
        try:
            archive = recorder.zip_record(path)
        except OSError as exc:
            messagebox.showwarning(self.t("warn_title"), str(exc))
            return
        self.lbl_info.config(text=os.path.basename(archive))
        messagebox.showinfo(self.t("warn_title"), self.t("rec_zipped", path=archive))
        try:
            os.startfile(os.path.dirname(archive))  # open the folder for TeamViewer file transfer
        except (AttributeError, OSError):
            pass

    def apply_language(self):
        self.frame.config(text=f" {self.t('sec_record')} ")
        self.stop_frame.config(text=f" {self.t('sec_stop')} ")
        self.files_frame.config(text=f" {self.t('sec_files')} ")
        self.chk_hunt.config(text=self.t("rec_while_hunting"))
        self.lbl_interval.config(text=self.t("rec_interval"))
        self.lbl_max.config(text=self.t("rec_max_frames"))
        self.lbl_max_gb.config(text=self.t("rec_max_gb"))
        self.btn_zip.config(text=self.t("rec_zip"))
        self.chk_no_model.config(text=self.t("rec_no_model"))
        self.lbl_auto_stop.config(text=self.t("rec_auto_stop"))
        self.lbl_stop_key.config(text=self.t("rec_stop_key"))
        self.set_busy(self.tab.session.running)

    def set_busy(self, running):
        observing = running and self.tab.session.state == SessionState.OBSERVING
        self.btn_observe.config(
            text=self.t("rec_observe_stop" if observing else "rec_observe"),
            state="normal" if observing or not running else "disabled",
        )
        state = "disabled" if running else "normal"
        for widget in (self.chk_hunt, self.spin_interval, self.spin_max, self.btn_zip,
                       self.chk_no_model, self.spin_auto_stop, self.spin_max_gb):
            widget.config(state=state)
        self.combo_stop_key.config(state="disabled" if running else "readonly")
        self.show_last()
