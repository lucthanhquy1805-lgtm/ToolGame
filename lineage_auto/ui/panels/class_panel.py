"""Choose the character class for this account.

Selecting a class does not touch the skill grid: all four classes currently
behave the same, so there is nothing to migrate and no reason to discard what
the user configured.
"""

import tkinter as tk
from tkinter import ttk

from ... import characters
from .base import Panel


class ClassPanel(Panel):
    def build(self):
        self.selected = tk.StringVar()

        self.frame = ttk.LabelFrame(self.parent, text=" Class ", padding=6)
        self.frame.pack(fill="x", padx=8, pady=3)

        row = ttk.Frame(self.frame)
        row.pack(fill="x")
        self.lbl_class = ttk.Label(row, text="")
        self.lbl_class.pack(side="left")
        self.combo = ttk.Combobox(
            row, textvariable=self.selected, state="readonly", width=18
        )
        self.combo.pack(side="left", padx=8)
        self.combo.bind("<<ComboboxSelected>>", self._on_pick)

    def _labels(self):
        """Localized class names in registry order."""
        return [self.tab.translator.class_name(c) for c in characters.all_classes()]

    def load(self):
        self.combo["values"] = self._labels()
        self.selected.set(self.tab.translator.class_name(self.account.character))

    def store(self):
        label = self.selected.get()
        for character in characters.all_classes():
            if self.tab.translator.class_name(character) == label:
                self.account.character_class = character.key
                return

    def _on_pick(self, _event=None):
        self.store()
        self.tab.on_class_changed()
        self.tab.request_save()

    def apply_language(self):
        self.frame.config(text=f" {self.t('sec_class')} ")
        self.lbl_class.config(text=self.t("class_label"))
        self.load()

    def set_busy(self, running):
        self.combo.config(state="disabled" if running else "readonly")
