"""Load and save settings, including one-time import of the v1/v2 config."""
import json
import os
import shutil
import time

from .. import app_paths
from .models import AccountSettings, AppSettings, HealthSettings, migrate_legacy_skills


def _import_legacy(path):
    """Convert a flat v1/v2 bot_config.json into a one-account AppSettings."""
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    account = AccountSettings(name="Account 1")
    account.health = HealthSettings(
        threshold_pct=int(data.get("hp_threshold_pct", 50)),
        use_skill=bool(data.get("skill_hp_enabled", True)),
        skill_key=str(data.get("hp_skill_key", "F5")),
        use_potion=bool(data.get("pot_hp_enabled", True)),
        potion_key=str(data.get("hp_pot_key", "F6")),
    )
    legacy_hashes = data.get("cursor_hashes") or {}
    # Round-trip through from_dict so legacy cursor names are translated.
    account = AccountSettings.from_dict({**account.to_dict(), "cursor_hashes": legacy_hashes})

    legacy_skills = data.get("skills") or {}
    attack_skills, buff_skills = migrate_legacy_skills(legacy_skills)
    account.attack_skills = attack_skills
    account.buff_skills = buff_skills
    account.ensure_skill_maps()
    account.enforce_skill_exclusivity()

    lang = data.get("lang") if data.get("lang") in ("ko", "en", "vi") else "ko"
    print(f"[CONFIG] imported legacy settings from {os.path.basename(path)}")
    return AppSettings(lang=lang, accounts=[account])


def _ahashes(signature):
    return [t.strip() for t in str(signature or "").replace(";", ",").split(",") if len(t.strip()) == 16]


class ConfigStore:
    def __init__(self, filename=None, legacy_filename=None):
        self.path = filename or app_paths.data_path(app_paths.CONFIG_FILE)
        self.legacy_path = legacy_filename or app_paths.data_path(app_paths.LEGACY_CONFIG_FILE)
        # PLAN 0.17: cursor aHashes the user removed on purpose (delete / move / ignore) since the last save.
        self.removed_cursors = set()

    def load(self):
        if os.path.exists(self.path):
            try:
                with open(self.path, "r", encoding="utf-8") as f:
                    return AppSettings.from_dict(json.load(f))
            except Exception as exc:
                print(f"[CONFIG] unreadable, using defaults: {exc}")
                return AppSettings()

        if os.path.exists(self.legacy_path):
            try:
                return _import_legacy(self.legacy_path)
            except Exception as exc:
                print(f"[CONFIG] legacy import failed: {exc}")

        return AppSettings()

    def backup(self):
        """Copy the config to lineage_auto_config.backup_<stamp>.json next to it. Returns the path or None."""
        if not os.path.exists(self.path):
            return None
        stem, ext = os.path.splitext(self.path)
        target = f"{stem}.backup_{time.strftime('%Y%m%d_%H%M%S')}{ext}"
        try:
            shutil.copy2(self.path, target)
            return target
        except OSError as exc:
            print(f"[CONFIG] backup failed: {exc}")
            return None

    def lost_cursors(self, settings):
        """["account/kind/aHash"] registered in the saved file but gone now, not removed on purpose."""
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                old = json.load(f)
        except (OSError, ValueError):
            return []
        now = {a.id: a.cursor_hashes for a in settings.accounts}
        lost = []
        for account in old.get("accounts") or []:
            current = now.get(account.get("id"))
            if current is None:
                continue
            for kind, signature in (account.get("cursor_hashes") or {}).items():
                gone = set(_ahashes(signature)) - set(_ahashes(current.get(kind))) - self.removed_cursors
                lost += [f"{account.get('name')}/{kind}/{token}" for token in sorted(gone)]
        return lost

    def save(self, settings):
        lost = self.lost_cursors(settings)
        if lost:
            print(f"[CONFIG] WARNING: cursor pictures lost without a delete: {', '.join(lost)} "
                  f"(backup: {self.backup()})")
        try:
            with open(self.path, "w", encoding="utf-8") as f:
                json.dump(settings.to_dict(), f, indent=4, ensure_ascii=False)
            self.removed_cursors.clear()
            return True
        except Exception as exc:
            print(f"[CONFIG] save failed: {exc}")
            return False
