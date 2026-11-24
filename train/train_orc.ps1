# Orc model, end to end (PLAN 0.20, docs/TRAINING.md section 6). Run from the repo root in PowerShell:
#   powershell -ExecutionPolicy Bypass -File train\train_orc.ps1 [-Epochs 60] [-Trial] [-Name orc_v1] [-Out model\x.onnx]
# -Trial = pipeline test: unreviewed prelabel suggestions are accepted unseen (never ship that model).
# Without -Trial only REVIEWED frames (label_tool Enter = todo false) are exported: train any time on what is done.
# Ship rule (PLAN 0.22): recall >= 85 % day and >= 75 % night on the test frames -> HuntMap trial=False.
# Needs: .venv_train (torch cu128 + YOLOX deps), train\YOLOX (git clone), train\yolox_tiny.pth.
param(
    [int]$Epochs = 60,
    [switch]$Trial,
    [string]$Name = "orc_v1",
    # PLAN 0.22: day 111355 + 130457, night 133425 (its last 30 % is test: tests/prelabel.py "split")
    [string[]]$Train = @("records_game\20261124_111355_observe", "records_game\20261124_130457_observe",
                         "records_game\20261124_133425_observe"),
    [string[]]$Test = @("records_game\20261123_193903_observe", "records_game\20261124_133425_observe"),
    [string]$Out = "model\yolox_tiny_blessed_orc.onnx"
)
$ErrorActionPreference = "Stop"
$root = (Get-Location).Path
$data = Join-Path $root "datasets\$Name"
$env:PYTHONIOENCODING = "utf-8"

# 1. dataset: picked train frames, one class "orc" (test frames never go in)
if (Test-Path $data) { Remove-Item -Recurse -Force $data }
$exportArgs = @("tests\export_dataset.py", $data) + $Train + @("--classes", "single", "--split", "train", "--val-every", "6")
if ($Trial) { $exportArgs += "--use-suggestions" }
& "$root\.venv\Scripts\python.exe" @exportArgs
if ($LASTEXITCODE -ne 0) { throw "export failed" }

# 2. train on the GPU (fine-tune from the official yolox_tiny.pth)
$env:ORC_DATA = $data
$env:ORC_EPOCHS = "$Epochs"
$env:ORC_NAME = $Name
$env:PYTHONPATH = Join-Path $root "train\YOLOX"
Push-Location (Join-Path $root "train\YOLOX")
try {
    $sw = [Diagnostics.Stopwatch]::StartNew()
    & "$root\.venv_train\Scripts\python.exe" tools\train.py -f ..\exps\orc_tiny.py -d 1 -b 8 --fp16 -c ..\yolox_tiny.pth
    if ($LASTEXITCODE -ne 0) { throw "training failed" }
    Write-Host ("training took {0:N1} min" -f $sw.Elapsed.TotalMinutes)
    # 3. ONNX for the bot (BGR, decoded output [1,8400,6])
    & "$root\.venv_train\Scripts\python.exe" ..\export_onnx.py -f ..\exps\orc_tiny.py `
        -c "..\YOLOX_outputs\$Name\best_ckpt.pth" -o (Join-Path $root $Out)
    if ($LASTEXITCODE -ne 0) { throw "onnx export failed" }
} finally {
    Pop-Location
}

# 4. held-out test frames: day (193903) and night (end of 133425) separately, at a few thresholds.
#    Recall counts cursor-confirmed monsters (+ reviewed boxes); precision only means something once reviewed.
#    eval_detection reads model\yolox_tiny_blessed_orc.onnx: with another -Out, copy it there to measure.
foreach ($t in $Test) {
    foreach ($c in @("0.1", "0.15", "0.2", "0.3", "0.4")) {
        & "$root\.venv\Scripts\python.exe" tests\eval_detection.py --labels "$t\labels.json" --images $t --split test --maps blessed_orc --conf $c
    }
}
