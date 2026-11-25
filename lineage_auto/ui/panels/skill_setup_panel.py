"""Compact account-tab entry point for catalog-backed skill setup."""
from tkinter import ttk

from ...skills.catalog import get_catalog
from ..skill_setup_modal import SkillSetupModal
from ..skill_summary import format_skill_summary
from .base import Panel


class SkillSetupPanel(Panel):
    def build(self):
        self.catalog = get_catalog()
        self.frame = ttk.LabelFrame(
            self.parent, text=" Skill Setup ", padding=6
        )
        self.frame.pack(fill="x", padx=8, pady=3)

        self.setup_button = ttk.Button(
            self.frame, text="Skill Setup", command=self._open_modal
        )
        self.setup_button.pack(anchor="w")
        self.summary_label = ttk.Label(
            self.frame, text="", foreground="gray", wraplength=390
        )
        self.summary_label.pack(fill="x", pady=(6, 0))
        # PLAN 0.34: page F1 is full of heal / potions / buffs, so say where attack spells belong.
        self.hint_label = ttk.Label(self.frame, text="", foreground="#e65100", wraplength=390)
        self.hint_label.pack(fill="x", pady=(4, 0))

    def _open_modal(self):
        parent = getattr(self.tab, "frame", None)
        if parent is None:
            parent = self.parent.winfo_toplevel()
        SkillSetupModal(parent, self.tab).show()

    def refresh_summary(self):
        summary = format_skill_summary(self.account, self.catalog, t=self.tab.t)
        self.summary_label.config(text=summary or self.t("skill_summary_empty"))

    def load(self):
        self.refresh_summary()

    def apply_language(self):
        self.frame.config(text=f" {self.t('sec_skill_setup')} ")
        self.setup_button.config(text=self.t("btn_skill_setup"))
        self.hint_label.config(text=self.t("attack_page_hint"))
        self.refresh_summary()

    def set_busy(self, running):
        self.setup_button.config(state="disabled" if running else "normal")
