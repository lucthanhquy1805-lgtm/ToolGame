"""Checkpoint -> ONNX the bot can load (PLAN 0.20). Same steps as YOLOX tools/export_onnx.py, which calls
torch.onnx._export (gone in recent PyTorch).

Usage (training venv, from train/YOLOX with PYTHONPATH=.):
  python ../export_onnx.py -f ../exps/orc_tiny.py -c <best_ckpt.pth> -o <out.onnx>
Output: input "images" [1,3,S,S] (S = --size, default the exp's 640; the bot loads <name>_<S>.onnx for scan.input_size S) (0..255, BGR), output "output" [1,8400,5+classes] already decoded.
"""
import argparse
import importlib.util

import torch
from torch import nn
from yolox.models.network_blocks import SiLU
from yolox.utils import replace_module


def load_exp(path):
    spec = importlib.util.spec_from_file_location("exp_file", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.Exp()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("-f", "--exp", required=True)
    parser.add_argument("-c", "--ckpt", required=True)
    parser.add_argument("-o", "--out", required=True)
    parser.add_argument("--opset", type=int, default=11)
    parser.add_argument("--size", type=int, default=0, help="input side (PLAN 0.31: 416 / 320 = faster scans)")
    args = parser.parse_args()
    exp = load_exp(args.exp)
    model = exp.get_model()
    # our own checkpoint (holds numpy scalars): trusted, so not weights_only
    ckpt = torch.load(args.ckpt, map_location="cpu", weights_only=False)
    model.load_state_dict(ckpt["model"] if "model" in ckpt else ckpt)
    model.eval()
    model = replace_module(model, nn.SiLU, SiLU)
    model.head.decode_in_inference = True
    size = (args.size, args.size) if args.size else exp.test_size
    dummy = torch.zeros(1, 3, *size)
    torch.onnx.export(model, dummy, args.out, input_names=["images"], output_names=["output"],
                      opset_version=args.opset, dynamo=False)
    print(f"wrote {args.out}")


if __name__ == "__main__":
    main()
