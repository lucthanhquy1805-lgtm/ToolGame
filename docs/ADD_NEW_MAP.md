# Thêm một bãi / khu / loại quái mới

Không sửa code: mỗi khu = 1 file danh mục + vài ảnh tên + (sau khi train) 1 model.
Ví dụ đầy đủ: khu `오염된 축복의 땅 - 오크의 땅` (`lineage_auto/data/monsters/blessed_orc.json`).

## 0. Danh mục quái — `lineage_auto/data/monsters/<key>.json`
```json
{
 "key": "blessed_orc",                       // tên file, chữ Latin; ảnh tên ở names/<key>/
 "real_map": "오염된 축복의 땅 - 오크의 땅",  // tên khu hiện trong ô "실제 사냥터" của tool
 "name_en": "Blessed Land (polluted) - Orc area",
 "hunt_map": null,                           // khóa HuntMap trong hunt_maps.py khi đã có model; null = chỉ thu dữ liệu
 "group": "orc",                             // tên lớp khi gộp mọi quái của khu thành 1 lớp
 "monsters": [
  {"name": "오염된 오크 궁수", "class": "orc_archer", "level": 13, "attack": "ranged"},
  {"name": "네루가 오크", "class": "npc", "npc": true, "no_attack": true},
  {"name": "스피리드", "class": "boss_spirid", "boss": true, "no_attack": true}
 ]
}
```
- `name`: đúng chữ Hàn trong game (tên trên đầu quái / dòng chat "아데나 (n) 획득: <name>").
- `class`: nhãn (chữ Latin, không dấu cách). Cờ `npc` / `boss` / `no_attack` = không phải quái để săn.
- Tool đọc file khi mở: khu mới hiện ngay trong ô "실제 사냥터". Máy game: có thể đặt thư mục
  `lineage_auto/data/monsters/` cạnh `main.exe` (ưu tiên hơn bản đóng gói).
- 3 khu còn lại của 오염된 축복의 땅 đã có file rỗng mẫu (`blessed_human/elf/spirit.json`).

## 1. Thu dữ liệu (máy game)
- Chọn đúng khu trong "실제 사냥터" → khu chưa có model thì tool tự tích "모델 사용 안 함".
- "관찰만 기록 시작", Mỗi(giây)=1. Người chơi tự săn; rê chuột lên mỗi con ~1 giây trước khi đánh.
- Ngày VÀ đêm, mỗi loại ≥150 lần rê. Gửi zip bản ghi (`records/<stamp>_observe`).
- Bản ghi có: `frames.jsonl` (mouse, cursor, hp/mp, `monster_name`/`monster_class` khi đã có ảnh tên,
  `kills`, `event: kill:<name>`), `names/f_xxxxx.png` (ảnh tên cắt được).

## 2. Ảnh tên (lần đầu của mỗi khu, máy dev)
Chưa có ảnh tên thì tool vẫn ghi con trỏ, chỉ không biết LOẠI. Từ bản ghi đầu tiên:
```
python tests/analyze_records.py --config <config máy game> --set-map <key> <bản ghi>   # nhãn con trỏ
python tests/build_name_templates.py <bản ghi> <key> 230:orc 65:orc_spear ...            # tên trên đầu
python tests/build_name_templates.py <bản ghi> <key> --chat 37:orc:5 ... --check         # tên trong chat
```
- Chọn khung tên nằm trên nền trơn (đất), không có chữ trắng khác bên cạnh. Xem ảnh `names/<key>/*.png`.
- `--chat <khung>:<class>:<n>`: dòng giết thứ n tính từ dưới; ảnh phải bắt đầu bằng tên (không phải "획득:").
- `--check` in tên đọc được trên mọi khung có con trỏ tấn công / các lượt giết — sửa ảnh nào đọc sai.
- Đáp án đọc bằng mắt (như `tests/data/orc_names_193903.json`) + test trong `tests/test_monsters.py`.

## 3. Nhãn
```
python tests/analyze_records.py --config <config> [--set-map <key>] --check-dir records_game/_check_<key> <bản ghi...>
python tests/label_tool.py <bản ghi>          # phím 1-9 = các lớp của khu, rồi corpse/player/npc
```
- Điểm vàng = con trỏ tấn công, kèm loại đọc từ tên. Kéo khung quanh điểm đó → khung tự nhận loại.
- Thêm khung cho quái không ai rê chuột, xác, người chơi, NPC. Enter = xong khung.
- Nhanh hơn (PLAN 0.20): `python tests/prelabel.py --train <bản ghi> --test <bản ghi khác ngày>` chọn ~150–250 ảnh
  khác nhau + vẽ sẵn khung gợi ý, rồi `python tests/label_tool.py <bản ghi> --review` (Enter = nhận hết + ảnh sau).
  Chi tiết + train một lệnh: docs/TRAINING.md mục 6.

## 4. Xuất dataset + train
```
python tests/export_dataset.py datasets/all <bản ghi...> --classes species      # mọi khu, giữ từng loại
python tests/export_dataset.py datasets/orc <bản ghi...> --map <key> --classes group   # 1 khu, 1 lớp "orc"
python tests/export_dataset.py datasets/bot <bản ghi...> --map <key>              # lớp của bot (monster/figure/die)
```
Mỗi ảnh ghi `map` + `night` (COCO + `manifest.json`), nên 1 dataset hợp nhất dùng được cho model chung
hoặc tách theo khu. Train theo `docs/TRAINING.md` (model mới dùng `channels="bgr"`).
Bot hiện dùng 3 lớp (monster/figure/die): model để săn xuất bằng `--classes model` hoặc `group`
(group: id 0 = quái của khu, giống "monster").

## 5. Đo
```
python tests/eval_detection.py --labels <bản ghi>/labels.json --images <bản ghi> [--conf X]
```
Chạy trước/sau mỗi thay đổi. Chọn `conf` theo khu (ghi vào `HuntMap.conf`).

## 6. Bật săn
- Chép `yolox_tiny_<key>.onnx` vào `model/`, thêm `HuntMap(key=..., onnx_rel=..., conf=..., channels="bgr")`
  vào `hunt_maps.py` (đây là chỗ duy nhất cần sửa code: model mới cần ngưỡng đã đo).
- Trong danh mục khu: `"hunt_map": "<key>"`. Chọn khu trong tool → bãi săn tự chuyển sang model đó.
- Khu chưa có model: bấm "Bắt đầu" săn sẽ hỏi xác nhận (khuyên dùng quan sát để thu dữ liệu).
