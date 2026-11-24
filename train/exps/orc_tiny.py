"""YOLOX-tiny, one class "orc", for 오염된 축복의 땅 - 오크의 땅 (PLAN 0.20, docs/TRAINING.md section 4).

Data: tests/export_dataset.py <out> <records...> --classes single --split train (COCO layout).
Images are read by YOLOX with cv2 = BGR, so the ONNX gets channels="bgr" (hunt_maps.NEW_MODEL_CHANNELS).
No normalisation (legacy=False preproc = 0..255 floats): the bot feeds the same.
Env: ORC_DATA (dataset folder), ORC_EPOCHS, ORC_NAME override the defaults below.
"""
import os
import random

import cv2
import numpy as np
import yolox.data.data_augment as data_augment
import yolox.layers
from pycocotools.cocoeval import COCOeval
from yolox.exp import Exp as MyExp

# Windows without MSVC/ninja: YOLOX's fast evaluator is JIT-compiled C++ and its fallback only catches
# ImportError; use the plain pycocotools one (same numbers, a little slower).
yolox.layers.COCOeval_opt = COCOeval

# PLAN 0.20/0.22: learn the orc SHAPE, not its green (other orc grounds have other colours), and see night
# frames (~0.5 of day brightness). Replaces YOLOX's mild augment_hsv (h +-5/180, s/v +-30); TrainTransform
# looks the name up in its module at call time.
HUE = 0.15  # share of the hue circle
SAT = (0.3, 1.6)
VAL = (0.4, 1.4)  # 0.4-0.65 ~ night
GREY_P = 0.1  # sometimes almost grey


def strong_hsv(img, *_args, **_kw):
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV).astype(np.float32)
    hsv[..., 0] = (hsv[..., 0] + random.uniform(-HUE, HUE) * 180) % 180
    hsv[..., 1] *= 0.1 if random.random() < GREY_P else random.uniform(*SAT)
    hsv[..., 2] *= random.uniform(*VAL)
    cv2.cvtColor(np.clip(hsv, 0, 255).astype(np.uint8), cv2.COLOR_HSV2BGR, dst=img)


data_augment.augment_hsv = strong_hsv

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class Exp(MyExp):
    def __init__(self):
        super().__init__()
        self.depth, self.width = 0.33, 0.375  # tiny
        self.num_classes = 1
        self.input_size = self.test_size = (640, 640)
        self.data_dir = os.environ.get("ORC_DATA", os.path.join(ROOT, "datasets", "orc_trial"))
        self.train_ann, self.val_ann = "instances_train2017.json", "instances_val2017.json"
        self.max_epoch = int(os.environ.get("ORC_EPOCHS", 60))
        self.no_aug_epochs = max(1, self.max_epoch // 6)
        self.warmup_epochs = 2
        self.eval_interval = 5
        self.print_interval = 5
        self.data_num_workers = 2
        self.flip_prob = 0.5  # the view is left/right symmetric
        self.mosaic_scale = (0.8, 1.2)  # monsters always have about the same size on screen
        self.mosaic_prob = 1.0
        self.enable_mixup = False  # tiny + few images
        self.mixup_prob = 0.0
        self.random_size = (18, 22)  # multiscale 576..704 around 640
        self.test_conf = 0.01
        self.exp_name = os.environ.get("ORC_NAME", "orc_tiny")
        self.output_dir = os.path.join(ROOT, "train", "YOLOX_outputs")
