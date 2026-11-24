# Quái ORC – bãi 오염된 축복의 땅 (khu 오크의 땅 / 오크 지구)
Mục tiêu (người dùng 24/11): máy game CHỈ săn quái orc → model nhận diện tập trung vào nhóm này.

## Danh sách quái orc của bãi (nguồn web + quan sát trong game)
| Tên (Hàn)            | Lv | Vũ khí / đặc điểm nhận diện                     | Kiểu đánh | Thấy trong chat game 23/11 |
|----------------------|----|-------------------------------------------------|-----------|----------------------------|
| 오염된 오크          | 3  | orc cơ bản, đầu lợn, vũ khí + giáp đơn giản      | cận chiến | có |
| 오염된 오크 도끼병   | 6  | rìu chiến (전투 도끼)                            | cận chiến | có |
| 오염된 오크 전사     | 10 | kiếm + giáp                                      | cận chiến | có |
| 오염된 오크 궁수     | 13 | cung, đánh xa                                    | tầm xa    | có |
| 오염된 오크 창병     | 16 | giáo/thương                                      | cận chiến (tầm với dài) | có |
| 오염된 오크 근위병   | ?  | được nhắc trong tài liệu cũ (bản gốc)            | ?         | CHƯA thấy – cần kiểm tra |
Nguồn: tmo.gg wiki Lineage Classic (cấp độ), cafe.daum shinbimp (mô tả vũ khí), cafe.daum rainmusicfamily (근위병).
Toàn bộ quái orc ở bãi này màu da XANH LÁ (bị "죽음의 나무" làm ô nhiễm) – khác orc thường. Di chuyển và hồi sinh nhanh
(tài liệu cũ) → hợp săn gom/AoE.

## Cần xác minh trong game
- 네루가 오크 / 두다-마라 오크 có thể là NPC orc thân thiện quanh bãi (tài liệu nói có "오크족 NPC") → KHÔNG được đánh;
  model cần lớp "npc" hoặc loại theo con trỏ NPC.
- 스피리드 (Lv 30) là boss của bãi (스피리드 레이드) – không phải orc, nên tránh / để người chơi quyết.
- Khu khác của cùng bãi có quái không phải orc: 오염된 인간 (검사/투사/궁수/도끼병 – khu 인간), 오염된 딥플라워,
  오염된 땅의 정기 (khu 정령/요정). Đừng trộn nhãn các khu này vào model orc.
- Bãi "타락한 축복의 땅" (cấp cao hơn) có orc khác: 타락한 간디 오크 17, 타락한 오크 궁수 20, 타락한 두다-마라 오크 22,
  타락한 오크 마법사 26, 타락한 오크 전사 30 → nếu sau này lên bãi đó cần model/nhãn riêng.

## Đề xuất cho nhận diện
1. Lớp nhãn: orc (chung) + thuộc tính loại (오크/도끼병/전사/궁수/창병) + corpse + player + npc.
   Train trước 1 lớp "orc" là đủ để săn; lớp con để ưu tiên (vd. đánh 궁수 trước vì bắn xa).
2. Thu dữ liệu: mỗi loại ≥150 nhãn, cả NGÀY và ĐÊM, nhiều góc/khoảng cách, đứng trong cỏ/sau cây, đang chết/xác.
   Hiện có: 20261123_193903_observe = 60 nhãn (ngày, chưa tách loại).
3. Tín hiệu phụ không cần model: tên quái hiện trên đầu khi rê chuột (chữ trắng "오염된 오크 …") → OCR tên để gán
   loại tự động cho nhãn con trỏ; dòng chat "아데나 획득: 오염된 오크 …" = xác nhận giết + loại quái.
4. Con trỏ tấn công: kiếm (cận chiến) VÀ mũi tên (đánh xa) – cả hai đã đăng ký.
