"""Hunt-map registry for per-map YOLOX weights.

One ONNX per hunting ground. Selecting a map in the UI loads that file;
dropping a correctly named .onnx into model/ is enough — no code change.
"""

import os
from dataclasses import dataclass

from .app_paths import asset_path

DEFAULT_MAP_KEY = "abandoned"
NEW_MODEL_CHANNELS = "bgr"  # fixed standard for every model trained from now on (docs/TRAINING.md)


@dataclass(frozen=True)
class HuntMap:
    key: str
    name_ko: str
    name_en: str
    onnx_rel: str
    # YOLOX score threshold; tuned with tests/eval_detection.py (PLAN 0.5).
    conf: float = 0.15
    # Colour order the ONNX expects. The shipped models get "rgb" (what the bot always fed them);
    # models trained with docs/TRAINING.md use NEW_MODEL_CHANNELS (official YOLOX loads images with cv2 = BGR).
    channels: str = "rgb"
    # PLAN 0.20: trained on unreviewed suggestion boxes to test the training pipeline. Usable on the dev PC
    # (eval_detection), never packed into a build; set False once a model trained on reviewed labels replaces it.
    trial: bool = False

    def display_name(self, lang="en"):
        if lang == "vi":
            return f"{self.name_ko} ({self.name_en})"  # in-game names are Korean
        return self.name_ko if lang == "ko" else self.name_en


MAPS = (
    HuntMap(
        key="abandoned",
        name_ko="버림받은자들의 땅",
        name_en="Abandoned Land",
        onnx_rel=os.path.join("model", "yolox_tiny_game.onnx"),
    ),
    HuntMap(
        key="fallen_spirit",
        name_ko="타락한자의 땅 정령방",
        name_en="Fallen Land Spirit Room",
        onnx_rel=os.path.join("model", "yolox_tiny_fallen_spirit.onnx"),
    ),
    HuntMap(
        key="toi",
        name_ko="오만의탑",
        name_en="Tower of Insolence",
        onnx_rel=os.path.join("model", "yolox_tiny_toi.onnx"),
    ),
    HuntMap(
        key="dragon_valley",
        name_ko="풍룡의 산맥",
        name_en="Dragon Valley",
        onnx_rel=os.path.join("model", "yolox_tiny_dragon_valley.onnx"),
        # 0.15 -> 0.02: recall 38% -> 76% on docs/game_reference (fp 1 -> 6, the cursor rejects those).
        conf=0.02,
    ),
    HuntMap(
        key="blessed_orc",
        name_ko="오염된 축복의 땅 - 오크의 땅",
        name_en="Blessed Land (polluted) - Orc area",
        onnx_rel=os.path.join("model", "yolox_tiny_blessed_orc.onnx"),
        conf=0.2,  # orc_v1 (reviewed labels): day 83%/P84%, night 76%/P84% on the test split, docs/TRAINING.md 6.5
        channels=NEW_MODEL_CHANNELS,
    ),
)

_BY_KEY = {m.key: m for m in MAPS}


def all_maps():
    return MAPS


def get(key):
    return _BY_KEY.get(key, _BY_KEY[DEFAULT_MAP_KEY])


def onnx_path(key):
    return asset_path(get(key).onnx_rel)


def model_exists(key):
    return os.path.isfile(onnx_path(key))


def pyinstaller_onnx_datas(model_dir="model"):
    """PyInstaller datas tuples for every .onnx in model_dir.

    Packs all hunt-map weights present at build time. Skips .pth checkpoints.
    """
    if not os.path.isdir(model_dir):
        return []
    trial = {os.path.basename(m.onnx_rel) for m in MAPS if m.trial}
    entries = []
    for name in sorted(os.listdir(model_dir)):
        if name.lower().endswith(".onnx") and name not in trial:
            entries.append((os.path.join(model_dir, name), "model"))
    return entries
