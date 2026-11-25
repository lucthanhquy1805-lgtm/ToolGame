# Huấn luyện / tinh chỉnh YOLOX-tiny cho bãi săn mới (PLAN 0.8, 4.2)

Mục tiêu: model nhận được quái của từng bãi (bắt đầu từ 오염된 축복의 땅, nơi model hiện có trả
**0 detection / 133 khung**). Mục 1–5: đường đi dữ liệu chung. **Mục 6: bãi orc đã train thử được trên
máy dev (24/11) — lệnh chạy lại + kết quả.**

```
máy game                               máy dev
────────                               ───────
ghi dữ liệu (records/…)  ──zip──▶  analyze_records.py  →  label_tool.py  →  eval_detection.py
                                                                         →  export_dataset.py → YOLOX train → ONNX → model/
```

## 1. Thu dữ liệu trên máy game (xem thêm deploy/HUONG_DAN.txt)

Trước khi ghi: chọn cửa sổ game, **đăng ký con trỏ** (kiếm = tấn công, thêm cả cung nếu có; thánh giá = xác).
Nhãn tự động chỉ có khi con trỏ đã đăng ký; con trỏ chưa đăng ký vẫn được ghi mã `hash` để phân tích sau.

| Cách ghi | Chuột | Nhãn quái tự động | Dùng khi |
|---|---|---|---|
| Chế độ 1 "관찰만 기록" + "모델 사용 안 함" | người chơi | vị trí chuột khi con trỏ là kiếm/cung | người tự săn, máy nhẹ |
| Chế độ 2 "사냥 중 기록" | bot | các điểm bot rê ra kiếm | đo model đang có |
| Chế độ 2 + "격자 커서 스캔" | bot (không bấm) | quét lưới quanh nhân vật khi model trả 0 | bãi an toàn, model không nhận quái |

Mỗi bản ghi: chọn đúng **"실제 사냥터"** (bãi thực tế) — tên này nằm trong `meta.json` và từng dòng
`frames.jsonl`, độc lập với model đang chọn. Ghi cả ngày và đêm (`night` = độ sáng trung bình < 45).

Khung đặc biệt ngoài nhịp 3 giây (chế độ 1): `event: "corpse"` khi con trỏ chuyển sang thánh giá,
`event: "hp0"` mỗi giây khi HUD đọc HP = 0 (để chụp được cửa sổ hồi sinh).

## 2. Đọc và gán nhãn trên máy dev

```bash
python tests/analyze_records.py records_game/<A>.zip records_game/<B>.zip   # số liệu + labels.json (nhãn con trỏ)
python tests/label_tool.py records_game/<A>                                 # gán nốt bằng tay
python tests/eval_detection.py --labels records_game/<A>/labels.json --images records_game/<A>
```

`labels.json` (mỗi ảnh):

```json
"f_00012.jpg": {"night": false, "map": "오염된 축복의 땅",
                "monster": [[812, 233]], "boxes": [[790, 197, 834, 269]], "ignore": [], "todo": false}
```

- `monster` = tâm quái, là thứ `eval_detection.py` chấm (khớp trong 60 px).
- `boxes` = khung `[x0, y0, x1, y1, lớp]` theo pixel của ảnh gốc, dùng để train.
- `todo: false` chỉ khi đã xem hết khung (cả khung không có quái cũng bấm Enter).
- Chấm điểm phải để **riêng vài bản ghi không dùng để train** (theo ngày/bãi), nếu không recall sẽ ảo.

label_tool — chọn lớp TRƯỚC khi vẽ (hiện trên thanh trên cùng):
`1` = quái (xanh lá), `2` = xác quái (cam), `3` = người chơi / NPC (xanh dương).
Kéo chuột trái = khung; bấm trái = khung mặc định của lớp quanh điểm bấm (quái 44×72, xác 60×36,
người 40×80); chuột phải = xóa khung dưới chuột; Enter/n = xong + khung sau; d/a = sau/trước; u = hoàn tác;
q = lưu và thoát. Chấm vàng = nhãn con trỏ chưa có khung — vẽ khung quái đè lên là nó được thay bằng tâm khung.
**Gán đủ cả 3 lớp trên mỗi khung**: thứ gì không có khung sẽ bị model học là "nền".
Khung lưu dạng `[x0, y0, x1, y1, lớp]` (lớp theo model: 0 quái, 1 người/NPC, 2 xác); khung cũ 4 số = quái.

## 3. Xuất dữ liệu

```bash
python tests/export_dataset.py datasets/lineage records_game/<A> records_game/<B> [--val-every 5]
```

Kết quả (chỉ lấy khung `todo: false`):

```
datasets/lineage/train2017/*.jpg   val2017/*.jpg                 ảnh đã che HUD giống bot (_blank_play_hud)
datasets/lineage/annotations/instances_{train,val}2017.json      COCO — định dạng gốc của YOLOX
datasets/lineage/labels/{train,val}2017/*.txt                    YOLO txt: "lớp cx cy w h" (0–1)
```

Lớp: `0 monster, 1 figure, 2 die` (COCO category_id = lớp + 1; YOLOX tự đổi về 0..2). Ảnh giữ kích
thước gốc (1187×890 từ máy game, 1280×960 từ docs/game_reference); YOLOX tự letterbox về 640.

## 4. Fine-tune YOLOX-tiny (bãi orc: xem mục 6)

### 4.1 Những điều model đang chạy yêu cầu (lineage_auto/vision/yolox_mobs.py)
- Đầu vào `images [1,3,640,640]`, float 0–255 **không chuẩn hóa**, letterbox giữ tỉ lệ, phần thừa
  ở phải/dưới tô 114 — giống `preproc` của YOLOX ≥ 0.2 (legacy=False).
- Đầu ra `output [1,8400,8]` = `cx, cy, w, h, obj, cls×3` **đã decode** → xuất ONNX với `--decode_in_inference`.
- 3 lớp theo thứ tự `monster, figure, die`.
- **Thứ tự kênh màu — lưu riêng cho từng model** (`HuntMap.channels` trong `lineage_auto/hunt_maps.py`):
  - 4 model đang có: `"rgb"` (giữ đúng cách bot vẫn đưa ảnh vào, không đổi kết quả nhận diện).
    Ghi nhận 23/11: fallen_spirit RGB 8/21 vs BGR 1/21; dragon_valley RGB 16/21 (fp 7) vs BGR 20/21 (fp 12).
  - **Mọi model train mới: `"bgr"` (chuẩn cố định, `hunt_maps.NEW_MODEL_CHANNELS`)** = đúng cách YOLOX chính
    thức đọc ảnh (cv2). Nhờ vậy train KHÔNG cần sửa dataset/preproc của YOLOX. Đừng đổi kênh khi train.
  - Thứ tự kênh của model đang dùng được ghi vào `meta.json` của mỗi bản ghi (`"channels"`).

### 4.2 Điểm bắt đầu: trọng số YOLOX chính thức
Không có `.pth` của các model đang dùng (ONNX không train tiếp được) → train từ `yolox_tiny.pth` chính thức
(COCO, tải ở trang Releases của YOLOX). Cần nhiều ảnh hơn so với tinh chỉnh từ model cũ: mục tiêu vài trăm
khung đã gán đủ 3 lớp mỗi bãi, có cả ngày và đêm. Nếu sau này có `.pth` cũ: dùng nó cho `-c` thay
`yolox_tiny.pth`, nhưng khi đó model đó dùng thứ tự kênh của nó (hỏi tác giả, thường là RGB) — ghi đúng vào
`channels` của HuntMap.

### 4.3 Các bước (máy có GPU NVIDIA)
```bash
git clone https://github.com/Megvii-BaseDetection/YOLOX && cd YOLOX && pip install -v -e .
```
`exps/lineage_tiny.py`:
```python
from yolox.exp import Exp as MyExp
class Exp(MyExp):
    def __init__(self):
        super().__init__()
        self.depth, self.width = 0.33, 0.375          # tiny
        self.num_classes = 3                           # monster, figure, die
        self.input_size = self.test_size = (640, 640)
        self.data_dir = "datasets/lineage"             # thư mục export_dataset.py
        self.train_ann, self.val_ann = "instances_train2017.json", "instances_val2017.json"
        self.max_epoch, self.no_aug_epochs = 80, 10
        self.flip_prob = 0.5                           # lật ngang được (góc nhìn đối xứng trái/phải)
        self.mosaic_scale = (0.8, 1.2)                 # quái luôn cùng cỡ trên màn hình: đừng co giãn mạnh
        self.exp_name = "lineage_tiny"
```
```bash
python tools/train.py -f exps/lineage_tiny.py -d 1 -b 16 --fp16 -c yolox_tiny.pth
python tools/export_onnx.py -f exps/lineage_tiny.py -c YOLOX_outputs/lineage_tiny/best_ckpt.pth \
       --output-name yolox_tiny_<bai>.onnx --decode_in_inference
```

### 4.4 Đưa vào bot và đo
1. Chép ONNX vào `model/`, thêm `HuntMap` trong `lineage_auto/hunt_maps.py` (key, tên ko/en, đường dẫn,
   **`channels=NEW_MODEL_CHANNELS`**).
2. `python tests/eval_detection.py --maps <key> --labels <bản ghi để riêng>/labels.json --images <…> [--conf X]`
   và chọn `conf` cho bãi (recall ≥ 90% mục tiêu PLAN 0.5; nhận nhầm được con trỏ lọc lại).
3. Smoke test, đóng gói, chạy chế độ 2 trên máy game và so sánh `hover_confirm_rate` / `wander`.

## 5. Hạn chế đã biết
- Nhãn tự động từ con trỏ (chế độ 1, quét lưới) chỉ là ĐIỂM quái, chưa có khung và chưa có xác/người →
  khung nào cũng phải xem lại bằng label_tool trước khi train.
- Nhãn quét lưới: quái di chuyển trong 2–4 giây quét → điểm có thể lệch so với ảnh chụp ngay trước khi quét.
- Bảng TeamViewer (góc phải dưới) che một phần ảnh; phần đó nằm trong vùng HUD bị che nên không ảnh hưởng train.

## 6. Bãi orc — quy trình đã chạy được trên máy dev (24/11, PLAN 0.20)

Máy dev: RTX 5060 Ti 16 GB, PyTorch 2.11 cu128 (Blackwell cần bản CUDA 12.8). Train trên GPU máy này được,
**không cần Colab**. Môi trường train tách riêng khỏi `.venv` đóng gói:

```powershell
python -m venv .venv_train
.venv_train\Scripts\python -m pip install torch torchvision --index-url https://download.pytorch.org/whl/cu128
.venv_train\Scripts\python -m pip install numpy opencv-python loguru tqdm thop tabulate psutil tensorboard pycocotools onnx onnxruntime
git clone --depth 1 https://github.com/Megvii-BaseDetection/YOLOX train\YOLOX          # không pip install (khỏi cần MSVC)
curl -L -o train\yolox_tiny.pth https://github.com/Megvii-BaseDetection/YOLOX/releases/download/0.1.1rc0/yolox_tiny.pth
```
Ba chỗ YOLOX không chạy thẳng với PyTorch mới / Windows (đã xử lý, không sửa mã YOLOX):
- bộ chấm COCO nhanh của YOLOX cần biên dịch C++ → `train/exps/orc_tiny.py` thay bằng pycocotools;
- `tools/export_onnx.py` gọi `torch.onnx._export` (đã bỏ) → dùng `train/export_onnx.py`;
- pycocotools đọc JSON bằng bảng mã Windows → `export_dataset.py` ghi COCO dạng ASCII.

### 6.1 Từ bản ghi tới ảnh để duyệt
```bash
python tests/analyze_records.py --config records_game/_upload/lineage_auto_config.json --reread-names <bản ghi>
python tests/prelabel.py --train records_game/20261124_111355_observe --test records_game/20261123_193903_observe
python tests/label_tool.py records_game/20261124_111355_observe --review      # rồi bản ghi test
```
- `analyze_records`: nhãn con trỏ + đọc lại tên quái (khung 1302 trước v9 đọc sai 궁수↔창병) + HP/MP/giết
  offline vào `frames_offline.jsonl` (không sửa `frames.jsonl`).
- `prelabel`: chọn ảnh (cách nhau ≥4 s, khác cảnh: camera dời hoặc quái đổi chỗ; ưu tiên điểm con trỏ chắc chắn,
  궁수/도끼병, quái con trỏ mà màu không bắt được = trong cỏ) + khung gợi ý: **glow** (quái orc phát sáng xanh vàng,
  đứng trên đất/cát), **cursor** (điểm con trỏ + loại đọc từ tên), **yolox** (model cũ ở ngưỡng thấp, chỉ giữ khung đủ
  xanh). Ghi `split` (train/test) + `suggest` vào labels.json. Test = bản ghi khác ngày + khác cỡ cửa sổ.
- `label_tool --review`: Tab chọn gợi ý, y nhận, x/chuột phải bỏ, t đổi loại, kéo đè = sửa khung, bấm trái =
  khung mặc định chỗ quái bị sót, **Enter = nhận hết + ảnh sau**. Thời gian từng ảnh lưu ở `review_sec`.

Kết quả chọn (24/11): train 110/600 ảnh (3,2 gợi ý/ảnh), test 50/307 ảnh (3,3/ảnh).
Nhìn 6 ảnh: quái trên đất trống gần như đều có khung; khoảng một nửa khung trong cỏ cao / trên người chơi là sai;
sót quái đứng chụm nhóm (1 khối màu rộng) và quái trong bụi tối. **Ước tính duyệt: 10–15 s/ảnh** (1–2 lần bỏ,
~1 lần vẽ lại, ~1 lần bấm thêm) → ~30–40 phút cho 160 ảnh. Số đo thật: label_tool in ra khi thoát.

### 6.1b Duyệt nhãn — LỆNH CHẠY (Windows, PowerShell, 24/11 v10)
Chọn lại 24/11 tối (PLAN 0.22): TRAIN 302 ảnh = 111355: 110 + 130457: 90 + 133425 (ĐÊM, đoạn đầu): 102;
TEST 90 ảnh = 193903: 50 (ngày, 1187) + 133425: 40 (ĐÊM, 30 % cuối, cách mọi ảnh train ≥30 s).
Python: `.venv` của repo (đã có opencv/onnxruntime). Mỗi lệnh mở một bản ghi; làm lần lượt, ảnh train trước:
```powershell
cd C:\Tool\lineage_auto_src
.venv\Scripts\python tests\label_tool.py records_game\20261124_111355_observe --review
.venv\Scripts\python tests\label_tool.py records_game\20261124_130457_observe --review
.venv\Scripts\python tests\label_tool.py records_game\20261124_133425_observe --review
.venv\Scripts\python tests\label_tool.py records_game\20261123_193903_observe --review
```
- Khi mở: in bảng phím + "x/y ảnh đã duyệt"; chỉ hiện ảnh CHƯA duyệt (thêm `--all` để xem lại cả ảnh xong).
- Đáy cửa sổ: thanh tiến độ "reviewed a/b (train c/d, test e/f)" của bản ghi đó.
- Lưu ngay sau MỖI thao tác (y/x/t/kéo/Enter). Thoát lúc nào cũng được (q, Esc hoặc nút X); chạy lại đúng lệnh đó
  là tiếp tục từ ảnh chưa duyệt đầu tiên. Ảnh chỉ tính "đã duyệt" khi bấm Enter/n.
- Ảnh đêm được làm sáng ×1,8 trên màn hình (file không đổi). Ban đêm khung "glow" (tím, "? glow") hay nằm trên
  cỏ/người chơi → x; khung "yolox" (từ model thử) thường đúng.
- Train được trên phần đã duyệt bất cứ lúc nào: export chỉ lấy ảnh `todo=false` (xem 6.2).

### 6.2 Train + xuất + đo (một lệnh)
```powershell
powershell -ExecutionPolicy Bypass -File train\train_orc.ps1 -Epochs 60 -Name orc_v1          # sau khi duyệt
powershell -ExecutionPolicy Bypass -File train\train_orc.ps1 -Epochs 40 -Name orc_trial -Trial # thử quy trình
```
Các bước: `export_dataset.py --classes single --split train` (1 lớp "orc"; xác/người/NPC bỏ = nền) → train
(`orc_tiny.py`: tiny, 640, kênh BGR đúng như YOLOX đọc ảnh = `channels="bgr"`, lật ngang, mosaic 0.8–1.2, không
mixup) → `train/export_onnx.py` → `model/yolox_tiny_blessed_orc.onnx` ([1,8400,6]) → `eval_detection --split test`.
Bot đọc đầu ra 6 cột được (chỉ lớp 0 = quái; figure/die = không có).

### 6.3 Kết quả TRAIN THỬ (24/11, chưa duyệt nhãn — chỉ để kiểm tra quy trình)
- Dữ liệu: 111355 (1302×976), 92 ảnh train / 18 val, 352 khung **gợi ý nhận mù** (`--use-suggestions`).
- 40 epoch, batch 8, fp16, GPU: **10,5 phút** (2 epoch đầu ~1,5 phút gồm khởi động). AP50 val 0,58 (so với chính
  khung gợi ý nên chỉ để tham khảo), AP50:95 0,38.
- Đo trên tập TEST (193903: 23/11, 1187×890, 50 ảnh, 43 quái đã được con trỏ xác nhận), mỗi model chạy riêng:

| model | conf | recall | thời gian/khung (CPU) |
|---|---|---|---|
| blessed_orc (thử) | 0.05 | 37/43 (86%) | 44 ms |
| blessed_orc (thử) | 0.15 | 35/43 (81%) | 44 ms |
| blessed_orc (thử) | 0.30 | 33/43 (77%) | 43 ms |
| dragon_valley | 0.02 (của nó) | 4/43 (9%) | 42 ms |

- Cột fp của eval_detection KHÔNG dùng được ở đây: ảnh test chưa duyệt, mỗi ảnh chỉ 1 con có nhãn (thường 3–5 con).
  Nhìn 6 ảnh test ở conf 0.3: ~15/19 khung đúng quái (~80%), sai = cỏ / người đứng sát quái; sót = nhóm chụm, bụi tối.
- Chạy nhiều model trong một lần `eval_detection` làm số ms sai (~500 ms do tranh luồng CPU) → đo từng model riêng.
- Model thử có `trial=True` trong `hunt_maps.py`: dùng được trên máy dev, **không đóng gói** (PyInstaller bỏ qua).
  Máy game không có file → khu orc vẫn ở chế độ thu dữ liệu (`has_model` kiểm cả file ONNX).

### 6.3b TRAIN THỬ 2 (24/11 tối, `-Trial -Name orc_trial2 -Epochs 40`, chưa duyệt nhãn)
302 ảnh train (102 đêm), 1348 khung gợi ý nhận mù, tăng cường màu mạnh (orc_tiny.py `strong_hsv`), 10,0 phút GPU.
Recall = quái được con trỏ xác nhận (ngày 45 điểm / 50 ảnh 193903, đêm 24 điểm / 40 ảnh cuối 133425):

| model | conf | recall NGÀY | recall ĐÊM | ms/khung CPU |
|---|---|---|---|---|
| thử 1 (24/11 trưa, 92 ảnh ngày) | 0.15 | 37/45 (82%) | 17/24 (71%) | 38 |
| thử 1 | 0.30 | 35/45 (78%) | 17/24 (71%) | 38 |
| **thử 2** | 0.10 | 41/45 (91%) | 22/24 (92%) | 40 |
| **thử 2** | 0.15 | 40/45 (89%) | 22/24 (92%) | 38 |
| **thử 2** | 0.20 | 40/45 (89%) | 21/24 (88%) | 38–42 |
| **thử 2** | 0.30 | 38/45 (84%) | 20/24 (83%) | 38–44 |

- Precision CHƯA đo được (cột fp so với 1 điểm/ảnh). Nhìn 6 ảnh test ở conf 0.3: khoảng 6–7/15 vòng đúng quái
  (~45 %); sai = chính người chơi / người chơi khác, bụi cỏ — đúng những khung "glow" sai đã được nhận mù khi train.
  → Model thử 2 KHÔNG đóng gói (vẫn `trial=True`), dù recall đã qua ngưỡng: số trên tập nhỏ, nhãn chưa duyệt.
- File `model/yolox_tiny_blessed_orc.onnx` giờ là thử 2 (thử 1 không giữ trong repo).

### 6.4 Việc tiếp
1. ~~Duyệt ảnh → train lại không `-Trial` → chọn `conf` → `trial=False` → đóng gói~~ XONG: orc_v1, mục 6.5.
2. ~~Thêm bản ghi BAN ĐÊM~~ XONG (133425 trong train + test).
3. Lặp: dùng model đã train làm nguồn gợi ý (`prelabel --map-model blessed_orc`) cho bản ghi mới — bắt được nhóm
   chụm và quái trong cỏ tốt hơn khối màu. Bản ghi "Ghi khi đang săn" với orc_v1 (v11) là nguồn tiếp theo.

### 6.5 orc_v1 — model ĐÓNG GÓI ĐẦU TIÊN (24/11, nhãn ĐÃ DUYỆT)
Lệnh: `train\train_orc.ps1 -Epochs 60 -Name orc_v1` (không `-Trial`), **10,8 phút** GPU, best AP val 26,68 (AP50:95).
`train_orc.ps1` dòng 26 và 53 gọi `.venv\Scripts\python.exe` (python hệ thống thiếu `mss`).
Đo trên tập TEST đã duyệt (recall / precision):

| conf | NGÀY 193903 (50 ảnh, 232 orc) | ĐÊM 133425 test (40 ảnh, 78 orc) |
|---|---|---|
| 0.1 | 84% / P82% | 77% / P81% |
| **0.2** | **83% / P84%** | **76% / P84%** |
| 0.3 | 82% / P86% | 73% / P84% |
| 0.4 | 81% / P92% | 71% / P83% |

38 ms/khung CPU. Ngưỡng đóng gói (≥85% ngày, ≥75% đêm): đêm đạt, ngày thiếu 1–2% → **người dùng chấp nhận** cho
thử săn thật vì bot còn xác nhận bằng con trỏ tấn công trước khi đánh (box sai = rê chuột thừa, không đánh nhầm).
Chọn **conf 0.2** (`HuntMap.conf`): giữ recall đêm ≥75%, precision 84%. `trial=False` → main.spec đóng gói model;
chọn khu `오염된 축복의 땅 - 오크의 땅` → bãi `blessed_orc`, bỏ tích "không dùng model".
Giả lập săn (`tests/test_hunt_replay.py`: `TargetingFeature.acquire` thật trên ảnh test, con trỏ = attack khi chuột
nằm trong box đã duyệt): có mục tiêu ở 48/50 ảnh ngày (96%) và 32/34 ảnh đêm có orc (94%); lần rê đầu trúng orc
45/48 và 27/32.

### 6.7 orc_v2 — thêm lớp "corpse" (PLAN 0.30 / 2, CHƯA TRAIN: chưa có nhãn xác)
Lần duyệt đầu đã XÓA các orc đang nằm → 4 bản ghi đã duyệt có 0 hộp corpse. Duyệt lại nhanh, chỉ thêm xác:

    .venv\Scripts\python.exe tests\label_tool.py records_game\20261124_133425_observe --corpse
    (lặp lại cho 111355, 130457, 193903; khung gần con trỏ thánh giá hiện trước; vẽ hộp quanh orc nằm/đang ngã,
     phím 8 = corpse, Enter = xong khung này cho lượt xác; khung đã duyệt lượt đầu vẫn giữ nhãn orc)

Train 2 lớp (orc = 0, corpse = 1; người chơi/NPC bỏ ra):

    powershell -ExecutionPolicy Bypass -File train\train_orc.ps1 -Name orc_v2 -Classes corpse -Out model\yolox_tiny_orc_v2.onnx

Bot không cần sửa mã: `vision/yolox_mobs.class_layout` đọc số lớp từ đầu ra ONNX (6 = 1 lớp, 7 = orc+corpse,
8+ = monster/figure/die). Hộp corpse → bỏ khỏi ứng viên (targeting, ≤20 px) + tín hiệu chết "die_box" (kill_fall)
+ vị trí cho nhặt đồ. Đo: eval_detection hiện chỉ chấm lớp orc; recall/precision lớp corpse cần thêm vào khi có nhãn.

### 6.8 orc_v2 (1 lớp, 25/11) — mặc định từ v18 (conf 0.3), orc_v1 chọn được ở Quét → Nâng cao → Model
Train: 111355 + 130457 + 133425 (train) + **092741** (132 ảnh đêm 1280×960, người chơi/cung thủ/slime/nhân vật = nền)
= 434 ảnh, 60 epoch, 17,3 phút GPU, best AP val 34,55. Test thêm: 30 ảnh đã duyệt cuối của 092741
(`split: "test"`, f_00682–f_00843; bản trước khi tách nằm trong git, commit 527d6e6).
File: orc_v2 = `model/yolox_tiny_blessed_orc{,_416,_320}.onnx`; orc_v1 = `model/yolox_tiny_blessed_orc_v1.onnx` (640, HuntMap `blessed_orc_v1`).
Recall / precision ở conf 0.2 (v2 ở 0.3 trong ngoặc), "char" = box trên chính nhân vật (≤45 px quanh char_anchor):

| tập | orc_v1 | orc_v2 |
|---|---|---|
| ngày 193903 1187×890 (50 ảnh duyệt) | 83% / P84%, char 2 | 83% / P86% (83% / P89%), char 1 |
| đêm 133425 1302×976 (40 ảnh duyệt) | 76% / P84% | 77% / P81% (76% / P84%) |
| đêm 092741 1280×960 (30 ảnh duyệt) | 95% / P90% | 96% / P95% (96% / P96%) |
| đêm 183803 1280×960 (58 điểm con trỏ) | 58/58 | 54/58 (54/58) |
| 223510 1334×1008 (58 điểm con trỏ) | 58/58, char 17 | 56/58, char 20 |

ms/khung bằng nhau (cùng kiến trúc). Hai tập con trỏ nghiêng về v1 (bot rê chuột theo box của v1 lúc ghi), nhưng
1 ca sót của v2 là thật (183803 f_00024: 오크 전사 trong cỏ cao). Chưa có ảnh 1334×1008 nào được duyệt.

### 6.9 타락한 축복의 땅 (4 mùa, orc tím) → orc_v3 (PLAN 0.37, 25/11) — CHỜ DUYỆT
8 bản quan sát 1334×1008 nhập từ `records_game/spring_summer_autumn/*.zip` thành
`records_game/<started>_observe_<spring|summer|autumn|winter>_<day|night>` (meta + frames.jsonl: `real_map` sửa
thành "타락한 축복의 땅의 봄/여름/가을/겨울"; bản ghi gốc ghi nhầm "오크의 땅"). Khu yêu tinh:
`20261124_230953_observe_spring_day_elf` (cùng bản đồ "타락한 축복의 땅의 봄", khu khác; meta `"zone": "fallen_blessed_elf"`, để sau). Ô chọn khu chọn theo LOẠI QUÁI (`zone_name`): "타락한 축복의 땅 (봄/여름/가을/겨울) - 오크" / "타락한 축복의 땅의 봄 - 요정"; bản ghi mới ghi thêm `"zone"` = khoá catalog, analyze_records ưu tiên nó hơn tên bản đồ.
Catalog `fallen_blessed.json`: một file cho 4 mùa (`real_maps`), 5 loại orc, `hunt_map: null` (chưa có model).

**Zero-shot orc_v2** (điểm con trỏ attack = nhãn yếu, khớp ≤ 60 px):

| bản ghi | điểm | conf 0.1 | conf 0.3 |
|---|---|---|---|
| xuân ngày | 498 | 3% | 1% |
| hạ ngày | 279 | 3% | 1% |
| thu ngày | 419 | 1% | 0% |
| đông ngày | 494 | 6% | 6% |
| hạ đêm | 523 | 2% | 1% |
| thu đêm | 441 | 2% | 1% |
| đông đêm | 403 | 1% | 1% |

→ Giả thuyết PLAN 0.20 "cùng chủng loại khác màu, model học hình dáng" **SAI** với orc_v2 (dù đã train với
`strong_hsv` hue ±0,15): orc tím gần như vô hình với nó (~0,1 box/khung). Đã xem ảnh: nhãn con trỏ đúng.

**prelabel** (`--glow purple`: khối tím đóng kín, chỉ lọc kích thước — các bộ lọc của glow xanh bỏ mất 70–90 % orc tím;
49–81 % điểm con trỏ nằm trong một box tím, 2–5 box/khung): mỗi bản 32 train + 8 test (test = 30 % cuối bản ghi, cách
ảnh train ≥ 30 s → test riêng từng mùa/ngày-đêm), cách nhau ≥ 12 s. Kết quả: 217 train + 56 test = 273 ảnh
(hạ ngày chỉ 25+8: bản ghi 10 phút), 5,1 gợi ý/ảnh (glow 1111, cursor 176, cursor+glow 90, yolox 3).
Box tím sai hay gặp: người chơi có hiệu ứng tím, bóng cây tối; quái đứng sát nhau = 1 box → bấm thêm.

    python tests/prelabel.py --train <rec>:32 --test <rec>:8 [... 7 bản] --gap 12 --glow purple --map-model blessed_orc

Duyệt (mỗi lệnh một bản, như 6.1b):

    .venv\Scripts\python tests\label_tool.py records_game\20261124_235143_observe_spring_day --review
    .venv\Scripts\python tests\label_tool.py records_game\20261125_001022_observe_summer_day --review
    .venv\Scripts\python tests\label_tool.py records_game\20261125_003058_observe_autumn_day --review
    .venv\Scripts\python tests\label_tool.py records_game\20261125_005357_observe_winter_day --review
    .venv\Scripts\python tests\label_tool.py records_game\20261125_012808_observe_summer_night --review
    .venv\Scripts\python tests\label_tool.py records_game\20261125_015330_observe_autumn_night --review
    .venv\Scripts\python tests\label_tool.py records_game\20261125_021734_observe_winter_night --review

Loại quái hiện ở gợi ý (궁수/전사/"orc") đọc bằng ảnh tên của 오크의 땅 nên không tin được; train 1 lớp "orc" nên
không ảnh hưởng. Chưa có xuân ĐÊM.
Train orc_v3 sau khi duyệt (một model orc chung: 오크의 땅 + 4 mùa; mọi catalog có `group: "orc"` → 1 lớp):

    powershell -ExecutionPolicy Bypass -Command "& .\train\train_orc.ps1 -Epochs 60 -Name orc_v3 -Out model\yolox_tiny_blessed_orc_v3.onnx -Train @('records_game\20261124_111355_observe','records_game\20261124_130457_observe','records_game\20261124_133425_observe','records_game\20261125_092741_hunt','records_game\20261124_235143_observe_spring_day','records_game\20261125_001022_observe_summer_day','records_game\20261125_003058_observe_autumn_day','records_game\20261125_005357_observe_winter_day','records_game\20261125_012808_observe_summer_night','records_game\20261125_015330_observe_autumn_night','records_game\20261125_021734_observe_winter_night') -Test @()"
