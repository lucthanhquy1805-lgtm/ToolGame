"""HP threshold, heal skill and potion."""
import tkinter as tk
from tkinter import ttk

from ...characters.base import HOTKEYS
from ...config.models import EXTRA_POTION_SLOTS, PotionSetting
from ...skills import HEAL_SKILL_ID, get_catalog
from ..skill_icons import load_photo_icon
from .base import Panel


class HealthPanel(Panel):
    def build(self):
        self.threshold = tk.IntVar(value=50)
        self.use_skill = tk.BooleanVar(value=True)
        self.skill_key = tk.StringVar(value="F5")
        self.use_potion = tk.BooleanVar(value=True)
        self.potion_key = tk.StringVar(value="F6")
        self.read_hud = tk.BooleanVar(value=True)
        self.return_town = tk.BooleanVar(value=False)
        self.return_pct = tk.IntVar(value=35)
        self.return_key = tk.StringVar(value="F8")
        self._heal_photo = None

        self.frame = ttk.LabelFrame(self.parent, text=" HP ", padding=6)
        self.frame.pack(fill="x", padx=8, pady=3)

        top = ttk.Frame(self.frame)
        top.pack(fill="x")
        self.lbl_under = ttk.Label(top, text="")
        self.lbl_under.pack(side="left")
        ttk.Spinbox(
            top, from_=10, to=90, increment=5, textvariable=self.threshold,
            width=5, command=self.tab.request_save,
        ).pack(side="left", padx=6)
        ttk.Label(top, text="%").pack(side="left")
        self.chk_hud = ttk.Checkbutton(top, text="", variable=self.read_hud, command=self.tab.request_save)
        self.chk_hud.pack(side="left", padx=(12, 0))  # live HP/MP moved to the bottom bar (UI v7)

        bottom = ttk.Frame(self.frame)
        bottom.pack(fill="x", pady=(4, 0))
        self.chk_skill = ttk.Checkbutton(
            bottom, text="", variable=self.use_skill, command=self.tab.request_save
        )
        self.chk_skill.pack(side="left")
        self.lbl_heal_icon = ttk.Label(bottom)
        self.lbl_heal_icon.pack(side="left", padx=(4, 2))
        self.lbl_heal_name = ttk.Label(bottom, foreground="gray")
        self.lbl_heal_name.pack(side="left", padx=(0, 4))
        ttk.Combobox(
            bottom, textvariable=self.skill_key, values=list(HOTKEYS), width=5, state="readonly"
        ).pack(side="left", padx=4)
        potion = ttk.Frame(self.frame)  # own row: the tool is ~440 px wide now
        potion.pack(fill="x", pady=(4, 0))
        self.chk_potion = ttk.Checkbutton(
            potion, text="", variable=self.use_potion, command=self.tab.request_save
        )
        self.chk_potion.pack(side="left")
        ttk.Combobox(
            potion, textvariable=self.potion_key, values=list(HOTKEYS), width=5, state="readonly"
        ).pack(side="left", padx=8)

        town = ttk.Frame(self.frame)
        town.pack(fill="x", pady=(4, 0))
        self.chk_town = ttk.Checkbutton(town, text="", variable=self.return_town, command=self.tab.request_save)
        self.chk_town.pack(side="left")
        ttk.Spinbox(
            town, from_=5, to=90, increment=5, textvariable=self.return_pct,
            width=5, command=self.tab.request_save,
        ).pack(side="left", padx=6)
        ttk.Label(town, text="%").pack(side="left")
        ttk.Combobox(
            town, textvariable=self.return_key, values=list(HOTKEYS), width=5, state="readonly"
        ).pack(side="left", padx=8)

        # PLAN 1.4: extra potion slots: [on] HP/MP < pct% key cooldown s
        self.potion_rows = []
        for _ in range(EXTRA_POTION_SLOTS):
            row = ttk.Frame(self.frame)
            row.pack(fill="x", pady=(4, 0))
            v = {
                "enabled": tk.BooleanVar(value=False), "stat": tk.StringVar(value="HP"),
                "pct": tk.IntVar(value=50), "key": tk.StringVar(value="F7"),
                "cooldown": tk.DoubleVar(value=1.5),
            }
            v["chk"] = ttk.Checkbutton(row, text="", variable=v["enabled"], command=self.tab.request_save)
            v["chk"].pack(side="left")
            ttk.Combobox(row, textvariable=v["stat"], values=("HP", "MP"), width=4, state="readonly").pack(
                side="left", padx=4)
            ttk.Label(row, text="<").pack(side="left")
            ttk.Spinbox(row, from_=5, to=95, increment=5, textvariable=v["pct"], width=5,
                        command=self.tab.request_save).pack(side="left", padx=4)
            ttk.Label(row, text="%").pack(side="left")
            ttk.Combobox(row, textvariable=v["key"], values=list(HOTKEYS), width=5, state="readonly").pack(
                side="left", padx=8)
            ttk.Spinbox(row, from_=0.2, to=60, increment=0.5, textvariable=v["cooldown"], width=5,
                        command=self.tab.request_save).pack(side="left")
            ttk.Label(row, text="s").pack(side="left", padx=(2, 0))
            self.potion_rows.append(v)

        self._refresh_heal_skill_badge()

    def _refresh_heal_skill_badge(self):
        """Show pack icon + name for basic Heal (383) beside the F-key picker."""
        catalog = get_catalog()
        skill = catalog.get(HEAL_SKILL_ID) or {}
        name = skill.get("name_vi") or skill.get("name_kr") or HEAL_SKILL_ID
        self.lbl_heal_name.config(text=name)

        path = catalog.icon_path(HEAL_SKILL_ID)
        photo = load_photo_icon(path, size=24) if path else None
        self._heal_photo = photo
        if photo is not None:
            self.lbl_heal_icon.config(image=photo, text="")
        else:
            self.lbl_heal_icon.config(image="", text="")

    def load(self):
        settings = self.account.health
        self.threshold.set(settings.threshold_pct)
        self.use_skill.set(settings.use_skill)
        self.skill_key.set(settings.skill_key)
        self.use_potion.set(settings.use_potion)
        self.potion_key.set(settings.potion_key)
        self.read_hud.set(settings.read_hud_numbers)
        self.return_town.set(settings.return_town)
        self.return_pct.set(settings.return_pct)
        self.return_key.set(settings.return_key)
        for v, potion in zip(self.potion_rows, settings.potions):
            v["enabled"].set(potion.enabled)
            v["stat"].set(potion.stat.upper())
            v["pct"].set(potion.pct)
            v["key"].set(potion.key)
            v["cooldown"].set(potion.cooldown)
        self._refresh_heal_skill_badge()

    def store(self):
        settings = self.account.health
        settings.threshold_pct = int(self.threshold.get())
        settings.use_skill = bool(self.use_skill.get())
        settings.skill_key = self.skill_key.get()
        settings.use_potion = bool(self.use_potion.get())
        settings.potion_key = self.potion_key.get()
        settings.read_hud_numbers = bool(self.read_hud.get())
        settings.return_town = bool(self.return_town.get())
        settings.return_pct = min(90, max(5, int(self.return_pct.get())))
        settings.return_key = self.return_key.get()
        settings.potions = [
            PotionSetting.from_dict({
                "enabled": v["enabled"].get(), "stat": v["stat"].get().lower(), "pct": v["pct"].get(),
                "key": v["key"].get(), "cooldown": v["cooldown"].get(),
            })
            for v in self.potion_rows
        ]

    def apply_language(self):
        self.frame.config(text=f" {self.t('sec_hp')} ")
        self.lbl_under.config(text=self.t("hp_under"))
        self.chk_skill.config(text=self.t("use_heal_skill"))
        self.chk_potion.config(text=self.t("use_potion"))
        self.chk_hud.config(text=self.t("read_hud_numbers"))
        self.chk_town.config(text=self.t("return_town"))
        for i, v in enumerate(self.potion_rows, 1):
            v["chk"].config(text=self.t("extra_potion", n=i))
        self._refresh_heal_skill_badge()
