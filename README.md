# Lineage Classic Auto v3.0.0 — mã nguồn dựng lại

Mã nguồn Python được dựng lại từ `main.exe` (bản build PyInstaller, Python 3.12).
Mọi hàm đã được biên dịch lại và so với bytecode gốc: **653/653 hàm khớp từng lệnh**.
Vì vậy chương trình chạy giống hệt bản exe bạn đang có. Docstring là bản gốc, còn các
dòng chú thích `#` là phần mình viết thêm, vì trình biên dịch Python đã xoá chú thích gốc.

## Cài đặt (Windows)
1. Cài **Python 3.12** (64-bit).
2. Cài driver Interception (một lần, cần quyền Admin, sau đó khởi động lại máy):
   giải nén `Interception.zip`, mở CMD bằng quyền Admin trong thư mục
   `Interception\command line installer` và chạy `install-interception.exe /install`.
3. Trong thư mục này:
   ```
   py -3.12 -m venv .venv
   .venv\Scripts\pip install -r requirements.txt
   .venv\Scripts\python main.py
   ```
   Log được ghi vào `session_log.txt`, cài đặt lưu ở `lineage_auto_config.json`.

## Build lại file exe
```
.venv\Scripts\pyinstaller --noconfirm main.spec
```
Kết quả nằm ở `dist\main\`. Khi gửi cho người khác, phải gửi cả thư mục (có `_internal`).

## Kiểm tra nhanh (không cần Windows)
```
python tests/smoke_test.py
```

## Phát triển bằng Claude Code
Mở thư mục này bằng Claude Code. File `CLAUDE.md` mô tả kiến trúc, vòng lặp chính,
các quy ước và những chỗ cần chú ý khi nâng cấp.

## Nội dung thư mục
- `main.py`: điểm khởi động
- `lineage_auto/`: toàn bộ mã nguồn, kèm dữ liệu skill và icon trong `lineage_auto/data`
- `model/`: 4 model YOLOX, mỗi model ứng với một bãi săn
- `hp_template.png`: mẫu ảnh để tìm thanh HP
- `main.spec`, `requirements.txt`, `tests/`: phần mình viết mới để build và kiểm tra

## Lưu ý
- Bản build gốc không có `mp_template.png`, nên chức năng đọc MP đang tắt.
  Đặt một ảnh mẫu thanh MP cạnh `main.py` để bật lại.
- Giao diện đang để chế độ một tài khoản (`MULTI_ACCOUNT_UI = False`).
