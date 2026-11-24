"""Pick which game client this account drives."""
import tkinter as tk
from tkinter import ttk

from ...winapi.window import WindowPicker
from .base import Panel


class WindowPanel(Panel):
    def build(self):
        self.selected = tk.StringVar()
        self.windows = {}

        self.frame = ttk.LabelFrame(self.parent, text=" Game ", padding=6)
        self.frame.pack(fill="x", padx=8, pady=3)

        row = ttk.Frame(self.frame)
        row.pack(fill="x")
        self.combo = ttk.Combobox(row, textvariable=self.selected, state="readonly")
        self.combo.pack(side="left", fill="x", expand=True, padx=(0, 6))
        self.combo.bind("<<ComboboxSelected>>", self._on_pick)
        self.btn_refresh = ttk.Button(row, text="Refresh", command=self.refresh)
        self.btn_refresh.pack(side="right")

        self.lbl_info = ttk.Label(self.frame, text="", foreground="gray")
        self.lbl_info.pack(anchor="w", pady=(2, 0))

    def load(self):
        self.refresh(auto_pick=True)

    def store(self):
        self.account.window_title = self.selected.get()

    def refresh(self, auto_pick=True):
        self.windows = WindowPicker.list_windows()
        games = WindowPicker.guess_game_titles(self.windows)
        # Game clients first so the right window is on top of the list.
        self.combo["values"] = games + [label for label in self.windows if label not in games]

        saved = self.account.window_title
        if saved and saved in self.windows:
            self.selected.set(saved)
            self._attach()
            return

        if auto_pick:
            for label in games:
                if self.tab.window_taken(label):
                    continue
                self.selected.set(label)
                self._attach()
                return
        self._update_info()

    def _on_pick(self, _event=None):
        self._attach()

    def _attach(self):
        label = self.selected.get()
        hwnd = self.windows.get(label)
        if hwnd:
            self.tab.session.attach_window(hwnd, label)
        self._update_info()
        self.tab.request_save()

    def _update_info(self):
        window = self.tab.session.window
        if window.attached and window.is_alive():
            rect = window.client_rect()
            self.lbl_info.config(text=self.t("win_ok", w=rect.w, h=rect.h), foreground="green")
        else:
            self.lbl_info.config(text=self.t("win_none"), foreground="gray")

    def apply_language(self):
        self.frame.config(text=f" {self.t('sec_window')} ")
        self.btn_refresh.config(text=self.t("refresh"))
        self._update_info()

    def set_busy(self, running):
        state = "disabled" if running else "readonly"
        self.combo.config(state=state)
        self.btn_refresh.config(state="disabled" if running else "normal")
