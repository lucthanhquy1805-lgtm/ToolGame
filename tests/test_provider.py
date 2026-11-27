"""PLAN 0.48: YOLOX on DirectML / CPU (scan.detect_provider).

Usage:  python tests/test_provider.py
Checks: "auto" falls back to the CPU when onnxruntime has no DirectML or the DirectML load fails (a PC without a
usable GPU), "gpu" says so instead, "cpu" never tries DirectML, the config keeps the choice; and when this machine
really has DirectML, the boxes and scores of every model size equal the CPU ones on the frames of the orc record 20261127_191624_hunt.
"""
import glob
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import cv2  # noqa: E402
import numpy as np  # noqa: E402
import onnxruntime as ort  # noqa: E402

from lineage_auto.config.models import ScanSettings  # noqa: E402
from lineage_auto.vision import yolox_mobs as ym  # noqa: E402

MAP = "blessed_orc"
DML = "DmlExecutionProvider"


def fresh(provider):
    ym._SESSIONS.clear()
    ym.FALLBACKS.clear()
    ym.PROVIDER = provider
    return ym.ensure_session(MAP, 320, 1)


def test_config():
    assert ScanSettings().detect_provider == "auto"
    assert ScanSettings.from_dict({"detect_provider": "gpu"}).detect_provider == "gpu"
    assert ScanSettings.from_dict({"detect_provider": "cuda"}).detect_provider == "auto"
    assert ScanSettings.from_dict({}).detect_provider == "auto"  # a config older than 0.48


def test_fallback():
    real_avail, real_session = ort.get_available_providers, ort.InferenceSession
    try:
        ort.get_available_providers = lambda: ["CPUExecutionProvider"]  # the CPU-only onnxruntime wheel
        assert ym.session_device(fresh("auto")) == "CPUExecutionProvider" and len(ym.FALLBACKS) == 1
        try:
            fresh("gpu")
            raise AssertionError("gpu without DirectML must fail")
        except RuntimeError as exc:
            assert "DirectML" in str(exc)
        ort.get_available_providers = lambda: [DML, "CPUExecutionProvider"]

        def no_gpu(path, opts=None, providers=None):  # DirectML.dll there but no DX12 device
            if DML in (providers or []):
                raise RuntimeError("no adapter")
            return real_session(path, opts, providers=providers)
        ort.InferenceSession = no_gpu
        assert ym.session_device(fresh("auto")) == "CPUExecutionProvider" and "no adapter" in ym.FALLBACKS[0][1]
        calls = []
        ort.InferenceSession = lambda p, o=None, providers=None: calls.append(providers) or real_session(
            p, o, providers=providers)
        fresh("cpu")
        assert calls == [["CPUExecutionProvider"]], calls
        ort.InferenceSession = real_session
        real_race = ym._race_ms
        if DML in real_avail():  # DirectML loads but is slower (WARP on a PC without a GPU): the CPU wins
            ym._race_ms = lambda sess, runs=2: 500.0 if ym.session_device(sess) == DML else 50.0
            assert ym.session_device(fresh("auto")) == "CPUExecutionProvider", ym.FALLBACKS
            assert "500.0 ms >= CPU 50.0" in ym.FALLBACKS[0][1]
            ym._race_ms = real_race
            assert ym.session_device(fresh("gpu")) == DML  # "gpu" never races
    finally:
        ort.get_available_providers, ort.InferenceSession = real_avail, real_session
    print("ok fallback: no DirectML / load error / slower -> CPU (auto), error (gpu), cpu never tries DirectML")


def test_same_boxes():
    if DML not in ort.get_available_providers():
        print("skipped same boxes: this onnxruntime has no DirectML (pip install onnxruntime-directml)")
        return
    files = sorted(glob.glob(os.path.join(ROOT, "records_game", "20261127_191624_hunt", "f_*.jpg")))[:12]
    if not files:
        print("skipped same boxes: records_game/20261127_191624_hunt has no frames on this machine")
        return
    frames = [cv2.imread(p) for p in files]
    for size in ym.EXPORT_SIZES:
        if ym.model_path(MAP, size) is None:
            continue
        out = {}
        for provider in ("cpu", "gpu"):
            ym._SESSIONS.clear()
            ym.PROVIDER = provider
            sess = ym.ensure_session(MAP, size, 1)
            assert ym.session_device(sess) == ("CPUExecutionProvider" if provider == "cpu" else DML), provider
            out[provider] = [ym.detect(f, 640, 380, 2000, map_key=MAP, size=size) for f in frames]
            blob = np.zeros((1, 3, size, size), np.float32) + 114
            out[provider + "_raw"] = sess.run(None, {sess.get_inputs()[0].name: blob})[0]
        diff = float(np.abs(out["cpu_raw"][..., 4:] - out["gpu_raw"][..., 4:]).max())
        for a, b in zip(out["cpu"], out["gpu"]):
            for pa, pb in zip(a, b):
                assert len(pa) == len(pb) and all(np.hypot(x - u, y - v) <= 2 for (x, y), (u, v) in zip(pa, pb)), \
                    (size, pa, pb)
        assert diff < 1e-3, (size, diff)
        n = sum(len(m) for m, _f, _d in out["cpu"])
        ym._SESSIONS.clear()
        ym.PROBES.clear()
        ym.PROVIDER = "auto"
        ym.ensure_session(MAP, size, 1)
        gpu_ms, cpu_ms = next(iter(ym.PROBES.values()))
        print(f"ok {size}: {n} monsters on {len(frames)} frames, DirectML == CPU (max score diff {diff:.1e}); "
              f"auto race: DML {gpu_ms} ms, CPU {cpu_ms} ms -> {ym.LAST_DEVICE}")


if __name__ == "__main__":
    test_config()
    test_fallback()
    test_same_boxes()
    ym.PROVIDER = "cpu"
    print("provider tests OK")
