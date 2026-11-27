# Kế hoạch nâng cấp — Lineage Classic Auto (từ bản 3.0.0)

Máy dev (C:\Tool\lineage_auto_src) KHÔNG có game. Game chạy trên máy khác; triển khai để sau (cuối file).
Quy tắc làm việc cho Claude Code:
- Làm theo thứ tự giai đoạn. Mỗi việc xong phải chạy `python tests/smoke_test.py` và bổ sung test cho logic mới
  (giả lập ctx/input như trong smoke_test, không cần game).
- Mọi thông số mới (phím, ngưỡng %, chế độ...) phải lưu trong `AccountSettings` (config/models.py, có
  from_dict/to_dict, mặc định = hành vi cũ) và có ô chỉnh trên giao diện + chuỗi ko/en trong ui/i18n.py.
- Vòng lặp dài phải gọi `poll_escape(ctx)` và kiểm tra `ctx.running` để ESC luôn dừng được.
- Việc nào cần ảnh/tọa độ thật từ game: làm phần code + chỗ cấu hình, đánh dấu "CẦN DỮ LIỆU GAME".

## DANH SÁCH VIỆC TỔNG (nguồn sự thật duy nhất — đánh dấu [x] khi xong)
Chi tiết từng việc nằm ở các mục bên dưới VÀ ở mục "Câu trả lời của người dùng" (A1–A10, bổ sung lần 2)
cùng 3.5. Khi tóm tắt tiến độ phải đi theo danh sách này, không chỉ theo tiêu đề giai đoạn.

Giai đoạn 0 — Sửa lỗi & tốc độ
- [x] 0.1 Bot đứng im khi nhận nhầm + quét chậm (đếm lượt quét nhầm → wander, blacklist điểm đã rê, ~6 điểm/lượt, đo thời gian)
- [x] 0.2 Chọn cửa sổ theo process LC.exe
- [x] 0.3 Phát hiện NHÂN VẬT chết nhanh: đọc số "HP:0/xxx" trên HUD + nhận cửa sổ hồi sinh (A1)
      (phần đọc số XONG 23/11: vision/hud_numbers.py, 10/10 ảnh, 3.5ms; HP:0 → chết sau 2 lần đọc, kể cả khi tắt hồi máu;
       XONG 26/11 v21rc1 (chi tiết ở 0.40): HP HUD = 0 → KHÔNG bấm/không click gì nữa, dừng ngay, log WARNING,
       lưu 3 ảnh THÔ records/deaths/death_*.png, trạng thái đỏ "Nhân vật chết - đã dừng"; thêm dấu hiệu thứ hai:
       số HP HUD biến mất > 2 s sau khi HP đã < 50 % (cửa sổ chết che HUD) cũng là chết.
       CÒN (cần dữ liệu game): nhận DẠNG cửa sổ hồi sinh để tự hồi sinh/đi tiếp — 3 ảnh chết chính là dữ liệu đó.)
- [ ] 0.5 NHẬN DIỆN ĐỦ MỌI QUÁI TRONG PHẠM VI SĂN (độ phủ/recall) — có bộ đo trên ảnh thật (xem mục 0.5)
      (đang làm: bộ đo xong; model dragon_valley đo trên ảnh bãi 풍룡의 상흔 (KHÔNG phải bãi của nó) 38% → 76%;
       CHƯA model nào được đo trên đúng bãi của nó; chưa đạt 90% — xem "Tiến độ 0.5" và "Video 23/11")
- [x] 0.6 Bộ GHI DỮ LIỆU trên máy game (vì chỉ xem được qua TeamViewer): chế độ 1 "chỉ quan sát" + chế độ 2 "ghi khi săn" (xem mục 0.6)
- [x] 0.6b THU DỮ LIỆU ĐỂ LÀM MODEL (bản v3, 23/11): nhãn từ con trỏ người chơi (chế độ 1 ghi mouse/cursor/hash mỗi
      khung), quét lưới con trỏ (0.8c), khung sự kiện ngoài nhịp (corpse khi con trỏ thành thánh giá, hp0 mỗi giây khi HUD
      HP = 0 — cửa sổ hồi sinh chưa nhận được, chỉ chụp), "Bãi săn thực tế" (meta.json + mỗi dòng frames.jsonl),
      "night" mỗi khung, "모델 사용 안 함" cho chế độ 1; analyze_records.py đọc nhãn mới, gộp nhiều bản ghi, thống kê
      theo bãi/ngày-đêm; dist/LineageAuto_20261123_v3.zip + HUONG_DAN.txt mục 3-5, 3-8, 4, 5-9, 10.
      CHƯA KIỂM TRÊN MÁY GAME. GUIDE_KO.txt chưa cập nhật v3.
- [ ] 0.4 Phát hiện QUÁI đã chết nhiều tín hiệu: con trỏ thánh giá, YOLOX "die"/box biến mất, DeathWatch, thanh HP quái (A1+)
      (code XONG 23/11: con trỏ X + box "die" ở chỗ khóa khi box quái mất + DeathWatch khi không còn kiếm; mỗi trận ghi lý do
       kết thúc combat.last_outcome, ctx.state["kills"], recorder end_*/kills. Chưa: thanh HP quái, dòng chat — chưa biết game có
       hiện không. CHỜ SỐ LIỆU chế độ 2 để biết tín hiệu nào đúng: lớp "die" của model chỉ thấy 1–2/3 xác trên ảnh mẫu)
- [x] 0.7 KHÔNG DỪNG ĐƯỢC BOT QUA TEAMVIEWER (thử 23/11 16:25 trên máy game, bản v2): khi bot chạy, bấm nút "중지 [ESC]"
      và gửi ESC qua TeamViewer đều không ăn, chuột phải taskbar cũng không. Cần: (a) phím dừng thứ 2 (vd. F12/Pause)
      + kiểm tra RegisterHotKey/Interception có thấy phím TeamViewer gửi không; (b) tự dừng khi thấy chuột di chuyển
      không phải do bot (InputArbiter); (c) hẹn giờ tự dừng (phút) + tự dừng khi đủ "최대 장수" của bản ghi;
      (d) file cờ STOP cạnh main.exe. Cũng ghi nhận: HP 75% làm bot hồi máu liên tục (회복의 기운 spam).
      (XONG 23/11, bản v3, CHƯA KIỂM TRÊN MÁY GAME QUA TEAMVIEWER:
       • Thử trên máy dev: phím giả lập bằng SendInput (cách TeamViewer gửi) TỚI ĐƯỢC cả RegisterHotKey lẫn
         GetAsyncKeyState → dùng cả hai cho phím dừng thứ 2 (RecordSettings.stop_key: Pause mặc định / ScrollLock /
         Insert; KHÔNG cho F5–F12 vì bot tự bấm). Phím dừng + file STOP dừng TẤT CẢ kể cả chế độ quan sát
         (manager.stop_all(include_observe=True)). Log "[HOTKEY] ESC registered=…" — trên máy dev ESC = False (app khác
         giữ ESC) → có thể cũng là lý do ESC không ăn trên máy game; xem log lần sau.
       • Nguyên nhân nút 중지 không bấm được: _run gọi window.activate() mỗi vòng + rê chuột liên tục → poll_escape
         giờ dừng bot khi cửa sổ tool (cùng process) lên foreground, sau 2s đầu (FOCUS_GRACE). Thay cho (b).
       • (c) "자동 정지(분)" mặc định 15 (0 = tắt) cho cả săn và quan sát + dừng khi bản ghi đủ max_frames.
       • (d) file STOP cạnh main.exe, kiểm tra 0.5s, xóa sau khi dừng; deploy/3_DUNG_BOT.bat + lối tắt Desktop
         "DUNG Lineage Auto". Chưa làm (b) "chuột di chuyển không phải do bot". HP 75% spam: chưa xử lý.)
- [x] 0.8 KẾT QUẢ CHẾ ĐỘ 2 ĐẦU TIÊN (records_game/20261123_162251_hunt.zip, 23/11 16:22, 464s, 133 khung, bãi
      오염된 축복의 땅, ban ngày, class wizard, model dragon_valley, conf 0.5): 0 detection / 133 khung dù màn hình đầy
      오염된 오크 전사/궁수 → 642 lượt quét = 642 lượt wander, 0 lần rê chuột. Model hiện có KHÔNG nhận quái bãi này.
      Việc: (a) thêm bãi 오염된 축복의 땅 vào hunt_maps; (b) gán nhãn 133 khung này (labels.json "todo") để huấn luyện/
      tinh chỉnh model; (c) phương án dự phòng không cần model: dò TÊN quái (chữ trắng trên đầu) / thanh HP quái /
      quét lưới con trỏ quanh nhân vật khi model trả 0. Ghi chú: cửa sổ game trên máy game là 1187x890 (không phải
      1280x960); bảng TeamViewer (góc phải dưới) che một phần hotbar trong ảnh chụp.
      (TIẾN ĐỘ 23/11, bản v3: (c) XONG phần "quét lưới con trỏ" — features/grid_scan.py, chỉ khi đang ghi + tích
       ô, YOLOX trả 0 → chụp 1 ảnh, rê lưới (bước 40, bán kính 200 ≈ 80 điểm), 1 lần đọc con trỏ/điểm, KHÔNG bấm,
       ghi hovers src=grid + grid_sweeps/grid_points/grid_ms, rồi wander như cũ. (b) XONG công cụ tests/label_tool.py
       (đã chạy trên 133 khung, mở được) nhưng 133 khung CHƯA GÁN — cần người gán (~1 phút/khung). Thử lọc màu
       xanh làm nhãn gợi ý: bỏ sót quái trong cỏ, tách 1 con thành nhiều box → không dùng. (a) CHƯA: chưa có ONNX
       cho bãi này; bãi chỉ có trong ô "Bãi săn thực tế" (REAL_MAPS).
       PHÁT HIỆN khi kiểm tra cửa sổ 1187x890: đọc số HUD HP/MP thất bại 0/133 khung (glyph theo pixel 1280) → sửa:
       hud_numbers phóng ảnh về rộng 1280 trước khi đọc → 133/133. Bar reader/buff icon đã đa tỉ lệ. Ô hotbar
       mặc định của buff_icons (cx_frac 0.28+…) rơi vào KHUNG CHAT, sai ở mọi cỡ — nhưng không nơi nào dùng.
       eval_detection.py lấy vị trí nhân vật/bán kính theo cỡ ảnh thật (trước cố định 640,380 / 1280x960).)
      (RÀ 26/11, v21rc1 — XONG ở v11–v19: (a) bãi có model riêng (`blessed_orc` orc_v1, `fallen_blessed` orc_v3);
       (b) 133 khung + các bản sau đã gán và duyệt, orc_v1/orc_v3 train từ đó; (c) quét lưới + đọc tên quái + dòng
       chat giết đều chạy. Không còn việc gì trong mục này.)
- [x] 0.9 BÃI 오염된 축복의 땅 CÓ 4 KHU (ảnh docs/game_reference/npc_teleport_nonamae_oyeom.png, 23/11): NPC 장로 노나메
      hỏi đi khu nào: 요정의 땅 / 인간의 땅 / 오크의 땅 / 정령의 땅. Mỗi khu quái khác nhau (bản ghi 16:22 = 오염된 오크;
      video 23/11 = 오염된 인간 검사/투사/궁수) → "실제 사냥터" và hunt_maps phải tách theo khu, vd.
      "오염된 축복의 땅 - 인간의 땅". Đây cũng là mẫu hộp thoại NPC dịch chuyển cho 1.3b (danh sách chữ, khu đang
      rê chuột chuyển màu xanh lá, con trỏ bàn tay).
      (RÀ 26/11 — XONG phần tách khu: 4 khu có trong `data/monsters/*.json` và ô "Bãi săn thực tế", mỗi khu trỏ
       sang hunt_map của nó. Phần HỘP THOẠI NPC DỊCH CHUYỂN vẫn chưa làm và thuộc 1.3b (quay lại bãi sau khi về làng).)
- [x] 0.10 GHI NHẬN 23/11 17:40: game KHÔNG nhận chuột từ TeamViewer (click, giữ chuột để đi, click đánh quái đều không có
      tác dụng; cửa sổ tool/Explorer thì nhận bình thường) → client chặn input giả lập (SendInput), giải thích vì sao bot
      phải dùng Interception. Hệ quả: Claude/TeamViewer không chơi thay được; người chơi phải ngồi máy game khi thu chế độ 1.
      Bản ghi chế độ 1 đầu tiên: bãi 오염된 축복의 땅 (khu 인간의 땅, ban đêm), bắt đầu 17:40. Danh sách "실제 사냥터"
      chưa có khu con → cần thêm 4 khu (mục 0.9).
      (RÀ 26/11 — GHI NHẬN, đã xử lý: bot dùng Interception (control/InputBackend) nên game nhận input; chính vì
       SendInput không vào game mà 0.28 dùng SendInput của TeamViewer làm tín hiệu "người dùng đang điều khiển" → dừng.)
- [x] 0.11 LỖI PHÂN LOẠI CON TRỎ (phát hiện trên records_game/20261123_174023_observe, chế độ 1, 900s, 284 khung,
      203 đêm, người chơi tự đánh 오염된 인간 궁수/투사/도끼병): cả 284/284 khung bị gán cursor="attack" dù có 5 hash
      khác nhau (80e0e0e060000000 x243, c0e0783028000000 x34, 80c0e0e0e0000000 x5, f0f0f03800000000, c0e0c0c0e0c00000).
      Nguyên nhân: aHash 64 bit của con trỏ quá thô, khoảng cách giữa các con trỏ KHÁC nhau chỉ 2–15 bit, mà
      HAMMING_OK = 14 (winapi/cursor.py) và classify() xét "attack" trước → gần như mọi con trỏ thành attack.
      → 278 nhãn tự động trong labels.json KHÔNG tin được. Ảnh hưởng cả bot săn (is_attack dùng cùng ngưỡng: rê
      lên đất cũng có thể bị coi là quái). Việc: (a) ưu tiên so MD5 chính xác, aHash chỉ dự phòng với ngưỡng ≤2 và
      chọn loại có khoảng cách NHỎ NHẤT, không lấy loại đầu tiên; (b) hash độ phân giải cao hơn (vd. 16x16 hoặc lưu
      ảnh con trỏ 32x32 vào bản ghi); (c) phân loại lại bản ghi này offline từ cột "hash" sau khi lấy hash đã đăng ký
      trong lineage_auto_config.json của MÁY GAME (máy dev để trống); (d) test đơn vị với các hash ở trên.
      KIỂM TRA CẤU HÌNH MÁY GAME (records_game/game_pc_config.json, kéo về 18:00): 4 con trỏ đăng ký TRÙNG NHAU:
      attack = 80e0e0e060000000+57351b16..+80c0e0e0e0000000+507c7967.., corpse = ground = 80e0e0e060000000+57351b16..,
      npc = 80c0e0e0e0000000+507c7967.. → hash con trỏ MẶC ĐỊNH (243/284 khung) đang được coi là attack, corpse VÀ
      ground cùng lúc. Bot săn không thể dùng con trỏ để xác nhận quái. Việc: (e) nút 등록 phải từ chối hash trùng với
      loại khác và báo lỗi; (f) đăng ký lại 4 con trỏ trên máy game (rê đúng lên quái / xác / đất / NPC); (g) xác minh
      con trỏ game có ĐỔI khi rê lên quái không — nếu không đổi thì phải bỏ cách xác nhận bằng con trỏ.
      Hash c0e0783028000000 (34 khung) chưa rõ là gì (có thể bàn tay/UI hoặc kiếm thật). game_pc_session_log.txt:
      ESC registered=True, phím dừng Pause (0x13) registered=True trên máy game.
      18:04 Claude thử đăng ký lại qua TeamViewer (nhân vật ở 화전민 마을): NPC (rê lên 노나메) → 80c0e0e0e0000000 (như cũ);
      Mặt đất → "fcfc480000000000,37df0d97..,80c0e0e0e0000000,507c7967.." (hash mới + lẫn hash NPC; bản
      records_game/game_pc_config_1804.json). Mỗi lần đăng ký có vẻ lưu nhiều hash đọc được trong 3s → lẫn con trỏ
      lúc đang di chuyển. Đăng ký qua TeamViewer KHÔNG tin được (game bỏ qua input giả lập) → người chơi phải đăng ký
      tại máy game; nút 등록 chỉ nên lưu hash xuất hiện ổn định ở cuối 3s.
      GHI CHÚ KHU CỦA CÁC BẢN GHI (danh sách 실제 사냥터 chưa có khu con): 20261123_174023_observe = 인간의 땅 (đêm);
      20261123_192010/192623_observe = 인간의 땅 (ngày, ngắn); bản quan sát bắt đầu ~19:38 = 오크의 땅 (ngày,
      quái 오염된 오크 / 오크 도끼병). Kết luận 19:40: ở khu 오크, tool bật + quan sát (Thu con trỏ TẮT) KHÔNG khựng.
      19:49 XÁC NHẬN CỦA NGƯỜI DÙNG: khi rê lên quái ở khu 오크 con trỏ là MŨI TÊN CHÉO CÓ LÔNG ĐUÔI (đánh xa), không phải
      kiếm → cần gán hình này vào "attack" (một loại nhiều hình). Bản quan sát ~19:38 có ~52 khung mũi tên → phân
      loại lại offline sau khi có hash mũi tên (lấy từ cursors/ của bản ghi hoặc config máy game). Bot săn cũng phải
      chấp nhận cả kiếm lẫn mũi tên là con trỏ tấn công (1.1c). Cửa sổ game trên máy game che phần phải của tool
      (khung "본 커서" bị cắt) → tool nên tự xuống dòng lưới theo bề rộng hoặc có thanh cuộn ngang.
      19:52 Claude gán mũi tên = Quái trên máy game → config 19:56 (records_game/game_pc_config_1956.json): attack =
      kiếm c0e0783028000000 + mũi tên c0c0201818000000. Bản ghi records_game/20261123_193903_observe (오크의 땅,
      ngày, 307 khung): 60 khung con trỏ mũi tên (= 60 nhãn quái), 26 xác, 184 đất, 37 không rõ. HP trong frames
      đọc đúng (165–190/190). analyze_records --config vẫn lỗi trên Linux (winapi/structs.py gọi ctypes.windll khi
      import) → cần import lười cả winapi. records_game/_wrong_download_main.exe là file kéo nhầm, xóa được.
      (CODE XONG 23/11, bản v4 dist/LineageAuto_20261123_v4.zip — CÒN (f): người chơi đăng ký lại 4 con trỏ TẠI MÁY GAME:
       • (a) CursorProfile.classify: MD5 chính xác → aHash chính xác → aHash GẦN NHẤT ≤ AHASH_MAX_DIST (winapi/cursor.py),
         hòa / quá xa → "unknown"; bỏ ưu tiên attack. Mặc định = 1 bit, KHÔNG phải 2: mũi tên mặc định 80e0e0e060000000
         và 80c0e0e0e0000000 chỉ cách nhau 2 bit (các cặp khác 6–18). Token đăng ký ở ≥2 loại → "unknown" + log cảnh báo 1 lần.
         ready (được săn) = attack đã đăng ký VÀ không trùng loại khác; session.start + nút săn báo đăng ký lại.
         Mọi chỗ dùng is_attack/is_corpse/classify (targeting, combat, grid_scan, observe) đi qua classify này — không đổi logic săn khác.
       • (b) Lưu ẢNH con trỏ thay cho hash 16x16 (chưa làm hash 16x16): PNG khi đăng ký (cursors/<id>_<loại>.png cạnh main.exe,
         hiện nhỏ cạnh mỗi loại) và trong bản ghi (records/<...>/cursors/<hash>.png, mỗi hash 1 ảnh); meta.json "cursor_classifier": 2.
       • (e) Nút 등록: đọc liên tục 3s (50ms/lần), chỉ lưu bộ token giữ nguyên ≥0,7s ở cuối với chuột lệch ≤3px (stable_tail);
         đăng ký lại THAY giá trị cũ; trùng loại khác → cửa sổ từ chối kèm ảnh (ko/en/vi); "불안정"; nút 삭제; khởi động có
         loại trùng → log WARNING + chữ cam "재등록 필요" + dòng đỏ.
       • (c) tests/analyze_records.py --config: phân loại lại offline, thống kê theo hash (+ ảnh nếu có), cảnh báo config trùng;
         nhãn con trỏ chỉ dùng khi phân loại tin được (--config hoặc cursor_classifier ≥2); labels.json chỉ ghi đè khi chưa có
         công người gán. Kết quả 20261123_174023_observe + game_pc_config.json: cả 5 hash → unknown (config trùng) → 0/284
         nhãn tin được (labels.json đã ghi lại, 0 nhãn tự động; 278 nhãn cũ bỏ).
       • (d) tests/test_cursor.py (6 hash thật, config máy game, config 18:04, MD5 trước, hòa, đăng ký trùng, ổn định) + smoke OK.
       • (g) KẾT LUẬN: con trỏ game CÓ ĐỔI khi rê lên quái. 34 khung c0e0783028000000: 32/34 chuột nằm ngay trên quái có tên
         "오염된 인간 투사/궁수/도끼병/검사" hiện trên đầu (tên chỉ hiện khi rê lên), 2 khung còn lại tối/không thấy quái (quái vừa
         chạy/chết). 24 khung 80e0e0e060000000 xem mẫu: chuột trên đất/bụi/túi đồ, không có quái → 80e0e0e060000000 = con trỏ
         thường (đất), c0e0783028000000 = gần như chắc là KIẾM (attack). 80c0e0e0e0000000 (5) và c0e0c0c0e0c00000 (1) chỉ xuất hiện
         khi chuột NGOÀI cửa sổ game (mouse=null) → con trỏ Windows, KHÔNG phải NPC → đăng ký NPC trên máy game đang sai.
         f0f0f03800000000 (1 khung, f_00078): chuột trên quái đang ngã/xác → có thể là thánh giá (xác), chưa chắc.
         Nếu đăng ký đúng attack=c0e0783028000000, bản ghi này có 34 nhãn quái — chưa tạo vì phải xác nhận bằng đăng ký tại máy game.)
      (18:40 NGƯỜI DÙNG ĐĂNG KÝ ĐÚNG tại máy game (records_game/game_pc_config_1840.json): attack=c0e0783028000000 kiếm,
       corpse=f0f0f03800000000 thánh giá, ground=80e0e0e060000000 bàn tay chỉ, npc=f0f0602000000000 bong bóng → khớp kết luận (g).
       → (f) XONG. Nhãn: analyze_records --config game_pc_config_1840.json → labels.json 34 nhãn quái (243 ground, 34 attack,
       1 corpse, 6 unknown = con trỏ Windows ngoài cửa sổ). Kiểm bằng mắt (records_game/_check/, _sheet_34_attack_labels.jpg):
       ~28/34 điểm nằm trên quái; 6 khung nghi ngờ (f_00089, 00092, 00099, 00117, 00125, 00262 — nền tối/trống dù tên quái
       vẫn hiện: quái đã đi khỏi giữa lúc đọc con trỏ và lúc chụp, hoặc quá tối) → xem lại bằng label_tool trước khi train.
       v5 ĐĂNG KÝ DỄ HƠN (phản hồi 18:40: xác biến mất nhanh, mặt đất đổi con trỏ liên tục, đăng ký lại bị "Thất bại"):
       • Phím tắt: ô "Chế độ đăng ký con trỏ" → HotkeyListener (RegisterHotKey, thread riêng) Ctrl+Alt+1..4 =
         quái/xác/đất/NPC (AccountSettings.cursor_keys, cấm F1–F12/ESC/Pause, bắt buộc Ctrl/Alt); bấm → capture_now()
         đọc 5 lần/150ms lấy giá trị nhiều nhất (majority), bíp cao = lưu, bíp trầm = không; tắt ô / bắt đầu săn-ghi /
         đóng tool → gỡ phím. Đã thử RegisterHotKey trên máy dev: 4/4 phím đăng ký được.
       • Bộ sưu tập "Con trỏ đã thấy" (runtime/cursor_collection.py, cursors/seen_<id>/index.json + PNG): tự thu khi ghi
         chế độ 1 (mỗi tick có chuột trong cửa sổ) / chế độ 2 (mỗi lần rê) hoặc khi tích "Thu con trỏ" (thread 0,1s, nghỉ khi
         phiên đang chạy). Lưới 12 hình + số lần + combobox Quái/Xác/Mặt đất/NPC/Bỏ qua; gán = THÊM vào loại (nhiều hình/loại),
         bỏ khỏi loại khác (kèm MD5 đi cặp); hình nhiều nhất có "gợi ý: Mặt đất". "Nạp bản ghi…" lấy từ frames.jsonl
         (+cursors/*.png); bản ghi cũ không có ảnh con trỏ → hiện vùng ảnh dưới chuột. Bản ghi chế độ 1 giờ có cột "md5".
       • runtime/__init__ nạp lười (PEP 562) → analyze_records chạy khi thiếu pyautogui/keyboard/interception (đã thử).
       • tests/test_cursor.py 12 test (thêm: config 18:40, majority + parse_hotkey, tự xóa trùng + backup, bộ sưu tập,
         nạp bản ghi 278 khung) + smoke OK. dist/LineageAuto_20261123_v5.zip; HUONG_DAN 3-8 + GUIDE_KO 5-2 cập nhật.
       CHƯA THỬ TRÊN MÁY GAME: phím tắt khi game đang focus (game có thể chặn/nuốt Ctrl+Alt+số?), tiếng bíp.)
- [x] 0.12 CÀI ĐẶT BỊ TREO KHI TOOL CŨ CHẠY NGẦM (23/11 18:24, cài v4 trên máy game): bấm X đóng cửa sổ tool nhưng
      main.exe vẫn chạy (tasklist thấy PID 4752) → robocopy trong 1_CAI_DAT.bat thử lại vô hạn (mặc định /R:1000000
      /W:30, output bị >nul nên nhìn như treo). Phải taskkill tay. Việc: (a) đóng cửa sổ = thoát hẳn tiến trình (dừng
      thread săn/ghi, unhook phím, thoát); (b) 1_CAI_DAT.bat: taskkill /im main.exe /f trước khi chép (chỉ process
      trong C:\LineageAuto\main), robocopy /R:2 /W:2, báo lỗi rõ nếu chép thất bại.
      (XONG 23/11, v5: on_close dừng cả quan sát (stop_all(include_observe=True)), gỡ phím tắt con trỏ + keyboard hook,
       run() gọi os._exit(0) sau mainloop → tiến trình tắt hẳn (thử trên exe: CloseMainWindow → thoát sau <3s).
       1_CAI_DAT.bat: PowerShell tắt main.exe có Path = %DEST%\main\main.exe (in PID), robocopy /R:2 /W:2 hiện lỗi
       (bỏ >nul), báo lỗi rõ; /XF thêm lineage_auto_config.backup_*.json, /XD thêm cursors. Thử với main.exe đang chạy:
       bị tắt, chép xong, config giữ nguyên. CHƯA thử trên máy game.)
- [x] 0.13 LỖI v4 KHI ĐĂNG KÝ LẠI (23/11 18:37, máy game): cấu hình cũ có attack/corpse/ground trùng nhau → đăng ký
      Mặt đất bị "Thất bại" vì clashes_with() so với giá trị CŨ của các loại đang bị đánh dấu "cần đăng ký lại".
      Người dùng phải bấm Xóa từng loại trước. Sửa: (a) khi khởi động mà phát hiện trùng → tự xóa các loại trùng
      (giữ bản sao trong log/backup), hoặc clashes_with bỏ qua loại đang ở trạng thái trùng; (b) thông báo lỗi
      "Thất bại" phải nói rõ trùng với loại nào và gợi ý bấm Xóa. Xác (X) còn báo "Không ổn định": kiểm tra con trỏ
      thánh giá có đổi hình liên tục (động) không — nếu có thì chấp nhận tập hash xoay vòng.
      (XONG 23/11, v5: MainWindow khi khởi động thấy loại trùng → ConfigStore.backup() (lineage_auto_config.backup_<giờ>.json)
       rồi CursorProfile.drop_duplicates() xóa các loại trùng → "Chưa đăng ký", log [CURSOR]. clashes_with() bỏ qua loại
       đang trùng. "Thất bại: trùng <loại>" + cửa sổ 2 ảnh (vừa đọc / đã đăng ký) + gợi ý bấm Xóa. Thử trên exe với
       game_pc_config.json: backup tạo, 4 loại về rỗng; với game_pc_config_1840.json: không đổi gì.
       Xác "Không ổn định": cấu hình 18:40 chỉ có 1 hash thánh giá f0f0f03800000000 → chưa thấy dấu hiệu con trỏ động;
       nếu có, bộ sưu tập cho gán nhiều hình vào cùng loại Xác. Nút cũ nới thành 5s / đứng yên 0,3s.)
- [x] 0.14 LỖI NGHIÊM TRỌNG (người dùng báo 23/11 19:27, bản v5): "bật tool thì nhân vật trong game không di chuyển
      được". Log máy game: records_game/game_pc_session_log_1928.txt. Trình tự 19:18–19:27: mở tool → quan sát 19:20
      → 19:25:45 người dùng bấm Bắt đầu (săn) → buff F10/F11/F6 → 19:26:08 dừng (bấm vào cửa sổ tool) → quan sát lại
      19:26:23 → báo lỗi. Nghi vấn: (a) dừng giữa lúc nhấn–kéo/nhấn phím → nút chuột trái hoặc Ctrl/Alt/Shift bị GIỮ
      qua Interception (không gửi up) → khi dừng/thoát phải luôn gửi mouse_up + key_up cho mọi phím đã nhấn;
      (b) luồng _listen_interception_escape giữ filter bàn phím và chuyển tiếp chậm/sai thứ tự (down qua Python,
      up đi thẳng); (c) "Thu con trỏ" gọi GetCursorInfo/GetIconInfo quá dày (26.947 mẫu trong vài phút) → kiểm tra
      tải CPU/GDI, giới hạn ~20 lần/giây. Mọi session đều log "interception ready (keyboard=0 mouse=10)" = thiết bị
      mặc định, auto_capture không thấy thao tác thật → kiểm tra bot có gửi vào đúng chuột không. Log v4 18:55: bot
      rê lên điểm YOLOX nhưng con trỏ vẫn là bàn tay (class=ground live=80e0e0e060000000) → có thể chuột Interception
      không làm game đổi con trỏ, hoặc điểm YOLOX sai. Chờ người dùng thử: tắt tool / mở tool không chạy gì / quan sát.
      19:30: "Thu con trỏ" đếm 366.739 → 405.809 mẫu chỉ trong vài phút KHI TOOL ĐỨNG YÊN (không ghi, không săn) →
      vòng thu con trỏ chạy không nghỉ (hàng nghìn lần/giây). Nghi phạm số 1 cho "khựng". Sửa: giới hạn ≤20 lần/giây,
      chỉ đọc khi chuột đổi vị trí hoặc con trỏ đổi handle (so hCursor trước khi tính hash), dừng khi cửa sổ game
      không ở trước; mặc định TẮT. Claude đã bỏ tích "Thu con trỏ" và khởi động lại tool lúc 19:31.
      (CODE XONG 24/11, bản v6 — CHƯA KIỂM TRÊN MÁY GAME:
       • Nguyên nhân "Thu con trỏ" chạy không nghỉ: `_collecting.wait(0.1)` — Event đang SET nên wait() trả về
         ngay. Đo trên máy dev: cũ 17.579 lần hash/giây = 99% một nhân CPU; mới ≤20 lần/giây (sleep 0,05s), chỉ hash
         khi hCursor hoặc vị trí chuột đổi (CursorProbe.peek = chỉ GetCursorInfo), bỏ qua khi game không ở trước;
         đứng yên ~1% CPU. Mặc định vẫn TẮT (không lưu vào config).
       • InputController theo dõi nút/phím bot đang giữ; release_all() (mouse_up trái luôn + key_up mọi phím còn
         giữ) khi dừng săn / thoát vòng săn / đóng tool. Backend có key_up (Interception, pyautogui).
       • ESC: RegisterHotKey(ESC) NUỐT phím ESC khỏi game suốt lúc tool mở → nay chỉ đăng ký khi đang SĂN
         (SessionManager.hunting()); quan sát / rảnh: ESC về game, không dừng quan sát (dừng bằng nút, Pause, STOP).
       • _listen_interception_escape: chỉ giữ filter bàn phím khi đang săn; filter KEY_ALL (down + up cùng một
         hàng đợi, chuyển tiếp trước rồi mới xét ESC) thay cho chỉ KEY_DOWN (up đi thẳng → sai thứ tự).
       • Chưa kiểm: chuột Interception có làm game đổi con trỏ không (log v4 18:55).)
- [x] 0.15 HP/MP TRÊN TOOL ĐỨNG YÊN 100% KHI ĐANG QUAN SÁT (người dùng báo 23/11 19:45, v5): game HP 156–174/190
      nhưng tool hiện "HP: 100% MP: 100%". Nguyên nhân (ui/main_window.py): _start_hp_monitor chỉ đọc HUD khi
      session KHÔNG running; _poll_state khi running lấy ctx.state["hp"/"mp"] — chế độ quan sát (session.py,
      vòng observe) có read_hud nhưng KHÔNG ghi vào ctx.state → nhãn giữ giá trị cũ. Dữ liệu ghi (frames.jsonl
      cột "hp") vẫn đúng. Sửa: vòng observe ghi ctx.state["hp"]=%, ctx.state["mp"]=% sau mỗi lần đọc (cả số tuyệt
      đối), ghi thêm "mp" vào frames.jsonl; nhãn tool hiện "HP 156/190 (82%)". Kiểm tra cả chế độ săn.
      (XONG 24/11: vòng quan sát ghi state hp/mp % mỗi lần đọc HUD; nhãn hiện "HP 156/190 (82%)" / "MP x/y (z%)"
       khi đọc được số HUD (cả lúc rảnh và lúc săn, lấy state hp_abs/mp_abs); frames.jsonl có "mp".)
- [x] 0.16 TẬP TRUNG QUÁI ORC (người dùng 24/11 01:51): máy game chỉ săn orc ở 오염된 축복의 땅 khu 오크. Danh sách
      quái, đặc điểm, nguồn, đề xuất lớp nhãn: docs/game_reference/ORC_MONSTERS.md. Ưu tiên: model 1 lớp "orc" cho bãi
      này + OCR tên trên đầu quái / dòng chat "아데나 획득" để gán loại tự động.
      LƯU Ý (người dùng 24/11 02:01): orc chỉ là BÃI ĐẦU TIÊN, sau này cần nhiều loại quái/bãi khác → mọi thứ phải
      tổng quát: danh mục quái theo bãi/khu là FILE DỮ LIỆU (lineage_auto/data/monsters/<map>.json: tên Hàn, lớp, cấp,
      kiểu đánh, ghi chú NPC/boss), nhãn/OCR tên/chat đọc từ danh mục; model theo bãi (map → model) hoặc model chung
      nhiều lớp; quy trình thu → nhãn → train → đo lặp lại được cho bãi mới chỉ bằng cách thêm file danh mục.
      (XONG PHẦN THU + NHÃN 24/11, bản v6 — CÒN: thu thêm ngày/đêm trên máy game, train model, đo, bật săn:
       • Danh mục: lineage_auto/data/monsters/blessed_orc.json (+ file rỗng blessed_human/elf/spirit), module
         lineage_auto/monsters.py; ô 실제 사냥터 có 4 khu "오염된 축복의 땅 - 요정/인간/오크/정령의 땅". Chọn khu
         chưa có model → tự tích "không model"; khu có hunt_map → đổi bãi săn; săn ở khu chưa có model → hỏi.
       • vision/name_reader.py: tên trên đầu quái dưới con trỏ attack (khuôn names/<khu>/<class>.png, chữ trắng,
         so khuôn + kiểm bề rộng dòng + so phần đuôi tên) — 59/60 đúng, 0 sai trên 60 khung mũi tên của
         20261123_193903_observe (đáp án đọc bằng mắt: tests/data/orc_names_193903.json), ~32ms. Chat dùng khuôn
         riêng <class>_chat.png (font chat khác); KillWatcher dóng hàng các dòng giết khi chat cuộn → 27 lượt giết.
       • Bản ghi quan sát: monster_name/monster_class/name_score, names/f_xxxxx.png, kills, event "kill:<tên>".
       • tests/: analyze_records (chạy không cần Windows; --set-map, --map, --check-dir, đọc tên/giết offline,
         thống kê loại × ngày/đêm), label_tool (lớp theo danh mục, điểm tự động mang loại), export_dataset
         (--map, --classes model|group|species, manifest khu/ngày-đêm), build_name_templates.py, test_monsters.py.
       • 20261123_193903_observe: labels.json 60 điểm + loại (orc 3, 창병 33, 전사 15, 궁수 4, 도끼병 5), ảnh kiểm
         tra records_game/_check_orc/. Quy trình: docs/ADD_NEW_MAP.md.)
      (24/11 tối, v11: model orc_v1 + bật săn khu 오크 XONG (0.20). CÒN: săn thật + "Ghi khi đang săn" trên máy game.)
      (RÀ 26/11 — XONG: danh mục quái theo khu là file dữ liệu, đọc tên trên đầu + dòng chat giết theo danh mục,
       model theo bãi (hunt_maps), quy trình thu → nhãn → train → đo ở docs/ADD_NEW_MAP.md + docs/TRAINING.md.
       Yêu cầu "tổng quát hoá" đã được giữ ở mọi mục sau (bãi orc tím thêm vào chỉ bằng file danh mục + ONNX).)
- [x] 0.17 GIAO DIỆN CHIA TAB (người dùng 24/11, bản v7): ttk.Notebook 6 tab Chính / Săn / Hồi phục / Kỹ năng / Con trỏ /
      Dữ liệu + thanh dưới cố định (nút lớn theo chế độ Săn/Quan sát, nút Quan sát, HP/MP, trạng thái, phím dừng).
      (XONG 24/11: ui/account_tab.py (ScrollPage: thanh cuộn chỉ hiện khi tràn; cả 6 tab vừa 440x640, đo bằng
       tests/ui_screenshots.py → ảnh docs/ui_v7/), panel mới ZonePanel (실제 사냥터 chuyển từ RecordPanel),
       StatusPanel (chế độ, trạng thái, đã giết, thời gian chạy, cảnh báo), GridPanel (quét lưới + chỗ cho 1.2);
       ScanPanel có "Nâng cao" thu gọn; HP/MP sống ra thanh dưới; dấu ⚠ ở tab Chính/Con trỏ; config "ui"
       {tab, geometry, topmost, mode} (AppSettings.ui), các khóa cũ giữ nguyên; "Luôn trên cùng"; kills đếm cả
       trong quan sát (chat). Test: tests/test_ui.py. Khung "Con trỏ đã thấy" nay hiện tối đa 8 hình (trước 12).)
- [x] 0.17 LỖI "본 커서" SAU KHI CÀI v7 (24/11 10:30, máy game): lưới hiện gán SAI — mũi tên Windows (108 lần) đang là
      "몬스터", mũi tên lông đuôi (65 lần, hash c0c0201818000000 = con trỏ tấn công thật) là "—". Claude sửa trên UI:
      mũi tên lông → 몬스터, mũi tên Windows → 무시. Kéo config về (records_game/game_pc_config_v7_1031.json): attack chỉ
      còn mũi tên, MẤT kiếm c0e0783028000000 → có thao tác trong lưới đã XÓA hash kiếm. Claude đã ghi lại config có cả
      kiếm + mũi tên (records_game/_upload/lineage_auto_config.json) lên máy game lúc 10:32. Việc: (a) tìm vì sao
      lưới hiển thị gán lệch hình (map tile ↔ hash, md5/aHash cặp đôi khi nạp lại lần đầu sau nâng cấp); (b) đổi loại
      một ô chỉ được thêm/bỏ ĐÚNG hash của ô đó, không đụng hash khác của cùng loại; (c) test: kiếm+mũi tên trong attack,
      đổi ô Windows → 무시 không làm mất kiếm.
      (XONG 24/11, v8. Nguyên nhân: (1) CursorProbe.last_legacy/last_image là biến chung, đọc KHÔNG khóa bởi luồng
       thu con trỏ, luồng phím tắt và luồng quan sát → một ô có thể lưu ảnh/md5 của lần đọc khác; ảnh chỉ lưu lần đầu
       nên ảnh sai từ v5/v6 (cursors/seen_*) tồn tại mãi → ô hash KIẾM mang hình mũi tên Windows, hiện "몬스터".
       (2) chọn 무시/— trên ô đó bỏ hash KIẾM khỏi attack mà không hỏi; lưới không vẽ lại sau khi đổi (ô khác hiện cũ).
       Không có index.json thật của máy game: test tái hiện dựng lại thư mục seen v6 từ ảnh thật bản ghi 193903.
       Sửa: CursorProbe.lock + read() (hash, md5, ảnh, vị trí của CÙNG một lần đọc) dùng ở thu con trỏ / quan sát /
       capture; image_print(ảnh) phải = hash mới lưu PNG (bộ sưu tập + recorder), khi nạp seen_* ảnh sai bị xóa
       (ô hiện "?"); đổi ô chỉ thêm/bớt đúng aHash + md5 của ô đó (CursorProfile.pictures/remove), bỏ khỏi một loại
       phải xác nhận (무시 trên ô chưa gán chỉ đánh dấu ô); tab 커서: mỗi hình của một loại có nút 삭제 riêng (bỏ nút Xóa cả loại);
       mũi tên Windows (80c0e0e0e0000000, c0e0c0c0e0c00000 + md5) tự 무시, assign/register/phím tắt từ chối;
       ConfigStore.save: loại mất aHash mà người dùng không xóa → [CONFIG] WARNING + backup_<giờ>.json.
       Test: tests/test_cursor.py +4 (tái hiện lưới, 1956 → Windows 무시 + mũi tên 몬스터 = đủ kiếm+mũi tên,
       pictures/remove, cảnh báo + backup) ; smoke/ui/monsters OK. dist/LineageAuto_20261124_v8.zip.
       CHƯA THỬ TRÊN MÁY GAME. Sau khi cài: ô kiếm cũ có thể hiện "?" (ảnh sai đã xóa) — vẫn là 몬스터, không cần làm gì.)
- [x] 0.18 MP KHÔNG ĐỌC ĐƯỢC KHI QUAN SÁT (v8, máy game 24/11 11:14): game hiện MP 245/317 nhưng tool "MP: -- %"; HP đọc
      đúng (190/190 → 100%). Kiểm tra vùng/khuôn số MP trên HUD ở cửa sổ 1187x890 (vision/hud_numbers) và đường cập
      nhật mp trong vòng quan sát (0.15).
- [x] 0.19 BẢN GHI 24/11 11:13 (records_game/20261124_111355_observe, v8, 오크의 땅, NGÀY, cửa sổ game 1302x976 – KHÁC
      1187x890 hôm qua): 600 khung (dừng vì đủ "tối đa 600" ở nhịp 1s = 10 phút, không phải 15 phút), 199 khung con trỏ
      tấn công = 199 nhãn; tên đọc được: 창병 101, 전사 40, 궁수 33, 오크 12, 도끼병 3, không rõ 10 (bộ đọc tên vẫn chạy
      ở cỡ cửa sổ mới). LỖI ở cỡ 1302x976: hp=null, mp=null cả 600 khung, kills = 0 (đọc chat không ra) → HUD số và chat
      đang theo tọa độ/khuôn cố định cho 1187x890; phải co giãn theo kích thước cửa sổ thật. Tối đa khung nên tự tính
      = tự dừng(phút)*60/nhịp, hoặc mặc định 1200.
      24/11 11:36: người dùng xác nhận trên máy game (v8, quan sát ~15 phút ở khu 오크): KHÔNG còn khựng → 0.14 XONG.
      (0.18 + 0.19 XONG 24/11, v9. Nguyên nhân chung: ở 1302x976 khung chat CAO hơn (người chơi kéo) → thanh HP/MP
       nằm ở ~0,70 chiều cao thay vì 0,79; dải tìm "HP:" cố định 0,775–0,83 → hp/mp null (UI hiện HP từ thanh máu
       dự phòng, MP không có dự phòng → "--"). Sửa: hud_numbers tìm "HP:"/"MP:" trong 0,5–0,92, thử trước hàng lần
       đọc trước (~4 ms/lần); chat: đỉnh vùng chat = hàng "HP:" + 27 px (thang 1280), chữ thu về cỡ 1187 trước khi so
       khuôn; dóng hàng chat giữa 2 khung bằng HÌNH mọi dòng (mật độ mực theo cột, bỏ dòng ghim "*****" trên cùng)
       thay vì tên + mép phải (ở 1302 tên dòng giết hay đọc sai, mép phải lệch ~5 px → đếm lại giết cũ, 42 → 18 thật);
       tên trên đầu quái cũng thu về cỡ 1187 (trước: 궁수 đọc thành 창병). Đo offline: hp/mp 600/600 (111355) và
       307/307 (193903); giết 18 (111355, mỗi khung ≤1, kiểm bằng mắt f_00403/558/567), 22 (193903, trước 27: khung
       f_00037 vẫn đếm dư khi bảng TeamViewer + thông báo hệ thống thay dòng ghim). analyze_records ghi hp/mp/giết đọc
       offline vào frames_offline.jsonl (frames.jsonl không sửa), --reread-names đọc lại tên.
       "Tối đa (khung)": 0 = tự động = tự dừng(phút)×60/nhịp (15×60/1 = 900; không hẹn giờ → 1200); config cũ còn
       600 (mặc định cũ) tự thành 0; khung sự kiện (xác/giết/HP0) không tính → không dừng sớm hơn hẹn giờ. UI hiện
       "0=tự động 900". Test: test_monsters (2 cỡ cửa sổ, cap), smoke (cap 3 + 2 khung sự kiện).)
- [x] 0.20 MODEL ORC — NHÃN BÁN TỰ ĐỘNG + TRAIN THỬ (24/11, máy dev). Xem docs/TRAINING.md mục 6.
      (PHẦN MÁY DEV XONG 24/11 — CÒN: người duyệt 160 ảnh, bản ghi ĐÊM, train lại trên nhãn đã duyệt, chọn conf.
       • Nhãn con trỏ (config _upload = v7_1031 + kiếm), loại đọc lại offline ở cỡ đúng:
         111355: 199 điểm — 창병 83, 전사 45, 궁수 36, 도끼병 9, 오크 9, không đọc được 17; giết (chat) 18.
         193903: 60 điểm — 창병 33, 전사 15, 도끼병 5, 궁수 4, 오크 3. Mẫu 60 tên 111355 nhìn bằng mắt: 5 sai
         (창병↔전사 ×3, 도끼병→전사, 궁수→창병), 4 không đọc (trước: ~9 sai, phần lớn 궁수→창병).
       • tests/prelabel.py: khung gợi ý (glow = khối xanh vàng đứng trên đất/cát, cursor + loại từ tên, yolox cũ ngưỡng
         thấp lọc theo màu) + chọn ảnh (≥4 s, khác cảnh, ưu tiên điểm con trỏ / 궁수·도끼병 / quái trong cỏ).
         train 110 ảnh (111355, 1302, 24/11), test 50 ảnh (193903, 1187, 23/11) → labels.json "split"/"suggest".
         Sót: quái chụm nhóm, trong bụi tối; sai: cỏ cao, người đứng sát quái.
       • label_tool --review (Tab/y/x/t, kéo đè = sửa, Enter = nhận hết + ảnh sau, review_sec + trung bình khi thoát).
         Ước tính 10–15 s/ảnh → 30–40 phút cho 160 ảnh (chưa có số đo thật: cần người duyệt).
       • export_dataset: --classes single (1 lớp orc), --split train|test, --use-suggestions (CHỈ để thử quy trình),
         COCO ASCII. eval_detection --split test. hunt_maps: HuntMap blessed_orc (bgr, conf 0.15, trial=True → không
         đóng gói); danh mục blessed_orc.json "hunt_map": "blessed_orc"; Zone.has_model kiểm cả file ONNX.
       • Train thử: GPU RTX 5060 Ti (.venv_train: torch 2.11 cu128 + train/YOLOX + yolox_tiny.pth chính thức),
         40 epoch / 10,5 phút trên 92 ảnh gợi ý nhận mù → model/yolox_tiny_blessed_orc.onnx [1,8400,6].
         Tập test: recall 81% (35/43) ở conf 0.15, 77% ở 0.3, ~44 ms/khung CPU; dragon_valley 9% (4/43).
         Precision nhìn mắt ~80% ở 0.3 (6 ảnh). Chạy lại: train/train_orc.ps1.)
      (XONG 24/11 tối, v11 — orc_v1 trên nhãn ĐÃ DUYỆT: train_orc.ps1 -Epochs 60 -Name orc_v1, 10,8 phút, best AP 26,68.
       TEST ngày 193903 (50 ảnh, 232 orc): conf 0.1 84%/P82%, 0.2 83%/P84%, 0.3 82%/P86%, 0.4 81%/P92%;
       đêm 133425 (40 ảnh, 78 orc): 0.1 77%/P81%, 0.2 76%/P84%, 0.3 73%/P84%, 0.4 71%/P83%; 38 ms/khung.
       Ngày thiếu 1% so với ngưỡng 85% → người dùng CHẤP NHẬN cho thử săn thật (con trỏ vẫn xác nhận trước khi đánh).
       hunt_maps blessed_orc: conf 0.2, bỏ trial (đóng gói), bgr. Chọn khu 오크 → bãi blessed_orc + bỏ tích "không dùng
       model". Giả lập săn tests/test_hunt_replay.py: mục tiêu 48/50 ảnh ngày, 32/34 ảnh đêm. docs/TRAINING.md 6.5.
       train_orc.ps1 dòng 26/53 gọi .venv\Scripts\python.exe (người dùng sửa). Đóng gói dist/LineageAuto_20261124_v11.zip
       (có model orc; 1_CAI_DAT giữ config/records/cursors, đã thử cài vào thư mục tạm). CÒN: thử săn thật trên máy game.)
- [x] 0.20 GIẢ THUYẾT CỦA NGƯỜI DÙNG (24/11 13:15): mọi bãi cấp 0–35 đều là quái ORC trên đất bị tha hóa, KHÁC MÀU nhưng
      CÙNG CHỦNG LOẠI (cùng hình dáng) → có thể dùng CHUNG một model orc, không cần thu đủ dữ liệu từng bãi.
      KIỂM CHỨNG sau bản ghi đêm khu 오크: (1) ở mỗi bãi orc khác chỉ chạy QUAN SÁT ~5 phút (không model, rê chuột lên
      quái); (2) trên máy dev chạy model orc OFFLINE trên bản ghi đó, recall = số điểm con trỏ tấn công có box model
      (eval_detection); (3) ≥80% → dùng chung; thấp hơn → thêm 1 lượt ngắn bãi đó vào dataset và fine-tune CHÍNH model
      orc (một model nhiều bãi). Thêm tăng cường màu (hue/saturation jitter) khi train để model ít phụ thuộc màu.
      Ghi chú: tests/prelabel.py đang dựa vào màu xanh đặc trưng → bãi màu khác cần nguồn gợi ý khác.
      (RÀ 26/11 — ĐÃ KIỂM CHỨNG ở 0.37: một model orc dùng chung cho CẢ 4 MÙA của 타락한 축복의 땅 (orc_v3, 78–91 %
       recall) nhưng KHÔNG dùng chung được với 오크의 땅 (orc_v1 vẫn tốt hơn ở đó) → "cùng chủng loại" đúng trong một
       bãi 4 mùa, sai khi khác bãi. Tăng cường màu HSV đã có trong train (train/exps/strong_hsv).)
- [x] 0.21 BẢN GHI 24/11 13:04 (records_game/20261124_130457_observe, v9, 오크의 땅, NGÀY, 1302x976, 814 khung): con trỏ
      tấn công 146 (도끼병 42, 오크 31, 궁수 24, 전사 20, 창병 13, không rõ 16), xác 81; hp/mp đọc 814/814 (0.18/0.19 OK
      trên máy game). LỖI: không có sự kiện kill nào trong frames.jsonl (chỉ "corpse") dù có giết → đọc chat lượt giết chỉ
      chạy offline, chưa ghi khi quan sát trực tiếp; kiểm tra. VẪN CHƯA CÓ ẢNH ĐÊM.
      (24/11 tối, v10 — CHƯA TÁI HIỆN ĐƯỢC, chờ số liệu máy game: tests/test_observe_kills.py chạy CHÍNH
       AccountSession._run_observe trên 814 khung đã lưu (grab = ảnh, con trỏ = chuột đã ghi) → 8 lượt giết = offline.
       Đã loại trừ: KillWatcher tạo 1 lần/lượt, gọi mỗi khung lưu, cùng ảnh BGR cỡ thật (co về 1187 trong chat_bands),
       không nuốt lỗi (lỗi sẽ dừng quan sát; bản ghi chạy đủ 900 s); v9 (12:40) đóng gói SAU lần sửa chat cuối (11:46)
       và có đủ khuôn *_chat.png. Còn lại: ảnh THÔ (không JPEG) khác ảnh lưu — chữ chat màu kem, độ bão hòa nét chữ
       trong JPEG p90 54 / p99 69 sát giới hạn 60 của whiteness; mô phỏng màu đậm hơn 25 % chỉ giảm 8→5, không về 0
       → chưa chắc. v10 ghi summary "chat_frames"/"chat_lines" (analyze_records in ra) + raw/f_xxxxx.png mỗi 100 khung.
       Bản ghi v10 tiếp theo: chat_lines ≈ 0 → so raw/*.png với JPEG cùng khung để sửa whiteness của chat.)
      (RÀ 26/11 — XONG: lỗi "không có sự kiện kill khi quan sát" hết từ 0.31/0.32 (đọc chat qua cùng JPEG như bản
       ghi); bản chạy thật v20 20261126_090350_hunt đọc được 53 dòng giết TRỰC TIẾP. tests/test_observe_kills.py
       vẫn còn để kiểm lại, nhưng ảnh của 130457 không còn trên máy dev nên test đó bị bỏ qua ở đây.)
- [x] 0.22 BẢN GHI ĐÊM ĐẦU TIÊN (records_game/20261124_133425_observe, v9, 오크의 땅, 1302x976, 797 khung): độ sáng
      43–61 (TB 51; ban ngày ~90–100) → cả bản là ĐÊM, nhưng cờ "night" chỉ bật 66/797 (ngưỡng 45 quá thấp ở cỡ cửa
      sổ/khu này) → đổi phân loại ngày/đêm: so với độ sáng ban ngày của khu, hoặc ngưỡng ~70, hoặc đọc biểu tượng
      mặt trời/trăng trên HUD. Con trỏ tấn công 174 (전사 33, 창병 30, 궁수 22, 도끼병 19, 오크 18, KHÔNG ĐỌC ĐƯỢC TÊN 52
      = 30% → bộ đọc tên yếu ban đêm, cần khuôn tên đêm). Tổng khu 오크 sau 4 bản ghi ≈ 580 nhãn (≈174 đêm).
      (24/11 tối, MỘT PHẦN: • ngày/đêm = độ sáng cả khung < 64 (vision/name_reader.NIGHT_BRIGHTNESS, dùng chung recorder +
       analyze_records; đo: ngày 66,5–115, đêm 42,7–61,1 → ngưỡng 70 sẽ xếp nhầm khung ngày 130457). analyze_records
       ghi "night" mọi khung vào frames_offline.jsonl (không dùng cờ cũ ngưỡng 45). • Tên ban đêm: THỬ khuôn đêm → đêm
       36/37 nhưng ngày thêm 1 sai; CHỌN ngưỡng trắng 150 khi khung là đêm (180 ban ngày): đêm 37/37 đúng (đáp án mắt
       tests/data/orc_names_133425_night.json), ngày 193903 vẫn 59/60, 0 sai. build_name_templates.cut co về cỡ 1187.
       Test: test_monsters test_name_reader_at_night (37 khung, ≥35 đúng, 0 sai).
       • Dữ liệu (prelabel: rec:N, bản ghi vừa train vừa test → test = 30 % cuối, train dừng 30 s trước đó; HSV glow co
         theo độ sáng; gợi ý thêm từ model orc thử --map-model blessed_orc --yolox-conf 0.15):
         TRAIN 302 ảnh / 1348 gợi ý = 111355 110/542 + 130457 90/443 + 133425 ĐÊM 102/363 (đoạn đầu chỉ đủ 102 ảnh khác
         cảnh); TEST 90 ảnh / 388 gợi ý = 193903 50/261 (ngày) + 133425 40/127 (đêm). Ban đêm khung "glow" nhiễu (cỏ,
         người chơi), khung yolox thường đúng.
       • label_tool --review: bảng phím khi mở, "x/y đã duyệt", thanh tiến độ đáy (train/test), ảnh đêm sáng ×1,8 khi
         hiển thị; đã có sẵn: lưu sau mỗi thao tác, chỉ hiện ảnh chưa duyệt, mở lại = tiếp tục. Sửa: in chữ Hàn trên
         console cp1252 làm tool chết ngay khi mở. Lệnh chạy: docs/TRAINING.md 6.1b.
       • Train: orc_tiny.py thay augment_hsv (hue ±0,15, sat ×0,3–1,6, sáng ×0,4–1,4, 10 % gần xám); train_orc.ps1 mặc
         định 3 bản ghi train + 2 test, đo ngày/đêm riêng ở 5 ngưỡng, -Out; eval_detection có cột precision ("?" =
         ảnh chưa duyệt, fp đếm thừa). Ngưỡng đóng gói: recall ≥85 % ngày, ≥75 % đêm.
       • Train thử 2 (gợi ý nhận mù, 40 epoch, 10 phút): recall ngày 89 % / đêm 88 % ở conf 0.2 (thử 1: 82 % / 71 %
         ở 0.15), ~40 ms/khung CPU; precision nhìn mắt ~45 % ở 0.3 (khung người chơi/bụi) → KHÔNG đóng gói. docs 6.3b.
       • Đóng gói v10 (dist/LineageAuto_20261124_v10.zip): đọc tên đêm + chẩn đoán 0.21; không có model orc.
       Nhãn đã duyệt → orc_v1 đóng gói ở v11 (xem 0.20). CÒN: khuôn/đọc tên ở 1280x960 đêm (0.24).)
      (RÀ 26/11 — XONG: ngày/đêm theo NIGHT_BRIGHTNESS 64, ngưỡng trắng 150 ban đêm, test_monsters có bài đêm;
       cửa sổ 1280x960 ban đêm nay đọc được cả tên lẫn chat (các bản ghi 0.39/0.40 đều là đêm).)
- [ ] 0.23 VIDEO MÁY GAME 23/11 (người dùng gửi 24/11 15:34): LC_2026_11_23_163033_Screen.mp4 (9:53) và
      LC_2026_11_23_190135_Screen.mp4 (10:55), 1280x960 30fps. Bãi 해적섬 던전 2층 (hầm ngục rất tối), nhân vật Lv54
      (군주, HP 510, MP 50) TỔ ĐỘI 2 người: 형수패 (trưởng nhóm, vương miện) + 형수팬. Quái: 라버본, 라버본 솔져,
      헤비 리자드맨 — KHÔNG phải orc. Hữu ích cho: (a) bãi hầm ngục tối (sau orc), (b) giai đoạn 3 tổ đội 2 nhân vật
      (khung danh sách party góc trái: tên + thanh HP/MP từng thành viên → đọc HP đồng đội để hồi/buff), (c) hotbar
      khác (F1: skill + bình 36/10 + cuộn 25/20). Video không có con trỏ được ghi → chỉ dùng làm ảnh tham khảo/gán tay.
- [~] 0.24 GÓI DỮ LIỆU MÁY GAME THỨ 2 (records_game/LineageAuto_data_20261124_1602.zip, người dùng gửi 24/11 15:40):
      nhân vật KHÁC – Lv26 Knight (HP 209, MP 130), cửa sổ 1280x960, 오염된 축복의 땅 khu orc, ĐÊM (độ sáng TB 36–38),
      đang bật ATS (tự săn của game, "남은시간"). Config máy này SAI: attack = 80e0e0e060000000 (= con trỏ BÀN TAY/đất),
      corpse/ground/npc trống → 6 lượt săn (15:27–15:33) "hover_confirm 100%" nhưng toàn "lost target" (đánh vào đất).
      Bản quan sát 153404 (256 khung): 207 khung con trỏ MŨI TÊN c0c0201818000000 (attack thật, chưa đăng ký nên ghi
      "unknown") → ~207 NHÃN ĐÊM dùng được khi phân loại lại theo hash. Bản 154711 (289 khung): 286 khung bàn tay → 0
      nhãn, chỉ làm ảnh nền đêm. Tên quái không đọc được (None) – cần kiểm tra ở 1280x960 đêm tối.
      Việc: (a) cảnh báo khi đăng ký attack trùng con trỏ mặc định 80e0e0e060000000 (từ chối như mũi tên Windows);
      (b) nạp 2 bản ghi vào dataset đêm (phân loại lại theo hash với config chuẩn); (c) đăng ký lại con trỏ trên máy này.
      (RÀ 26/11 — BỎ: máy game thứ 2 (Knight Lv26, ATS của game) không còn dùng từ 25/11, dữ liệu của nó không
       vào dataset orc_v1/v3. (a) cảnh báo khi đăng ký nhầm con trỏ bàn tay 80e0e0e060000000 KHÔNG làm riêng: kiểm
       tra "trùng kind" (0.13) đã chặn đúng trường hợp này (attack = ground = corpse) và báo ở tab Con trỏ.)
- [~] 0.25 MÁY GAME THỨ 2 (người dùng xác nhận 24/11 15:57): chạy Knight Lv26 (오염된 축복의 땅, đêm, ATS bật, cửa sổ
      1280x960) và Knight/군주 Lv54 (해적섬 던전 2층, tổ đội 형수패 + 형수팬 – video 0.23). Bản tool trên máy này cũ hơn v8
      (log không có [CONFIG]/v8; mp_template missing). Việc: cài bản mới nhất (v10 khi có), đăng ký lại 4 con trỏ (attack =
      kiếm + mũi tên), đặt "Bãi săn thực tế" đúng; quy trình thu/gửi dữ liệu giống máy 1; ghi tên máy vào meta.json
      (hostname) để phân biệt nguồn dữ liệu. Lưu ý ATS của game đang bật khi quan sát – không chạy bot săn của tool cùng
      lúc với ATS.
      (RÀ 26/11 — BỎ: chỉ chạy một máy game (máy 1, pháp sư Lv30). Nếu dùng lại máy 2 thì làm theo đúng quy trình
       cài đặt hiện tại (deploy/HUONG_DAN.txt) chứ không cần mục riêng.)
- [ ] 0.26 CÀI v11 LÊN MÁY GAME 1 (24/11 18:27): mở được, cửa sổ game giờ 1280x960. Sau khi cài, ô "Bãi săn" vẫn là
      Dragon Valley và "Không dùng model" vẫn tích dù khu đã là 오크의 땅 — chỉ đổi đúng khi CHỌN LẠI khu (Claude chọn
      khu khác rồi chọn lại 오크). Sửa: khi nạp config, áp dụng quy tắc khu → bãi/model ngay lúc khởi động.
      Trên máy game còn bản quan sát 20261124_171102_observe chưa kéo về.
      (RÀ 26/11 — CÒN MỞ (một phần): v20 đã làm phần nguy hiểm nhất: lúc BẮT ĐẦU săn, tên bản đồ trên màn hình
       quyết định zone/danh mục chat và ghi lại record.real_map (0.39/7), và chọn bãi ở khung Bản đồ kéo zone theo.
       CHƯA làm: khi NẠP config lúc khởi động, tự áp quy tắc khu → bãi/model (config cũ vẫn giữ bãi cũ cho tới khi
       người dùng chọn lại khu).)
- [x] 0.27 LẦN SĂN THẬT ĐẦU TIÊN VỚI orc_v1 (v11, máy game 1, pháp sư Lv30, 오크의 땅 ĐÊM, 1280x960, 24/11 18:34–18:50;
      records_game/20261124_183457_hunt (3 phút) + 20261124_183803_hunt (12.6 phút, 654 khung); log
      records_game/game_pc_session_log_1858.txt). Bot TỰ SĂN ĐƯỢC: 140 lần rê trúng quái (tỉ lệ con trỏ xác nhận 71%),
      140 lần đánh, chat game cho thấy giết orc liên tục, HP thấp nhất ~57% (hồi F5 hoạt động), không về làng, không kẹt.
      VẤN ĐỀ: (a) 133/139 trận kết thúc "lost target", chỉ 6 "monster dead" → bộ phát hiện quái chết gần như không ăn
      (pháp sư giết nhanh, median 2s; quái chết/biến mất bị coi là mất mục tiêu) → kills=6 sai, nhặt đồ F4 không chạy
      sau giết. Cần: coi box biến mất ngay sau đòn đánh + dòng chat "아데나 획득" = giết; đối chiếu số giết theo chat.
      (b) 560 lượt wander, 209/654 khung model không thấy quái (đêm tối) → đi lang thang nhiều; xem lại đường wander
      và ngưỡng conf (meta ghi conf 0.5 — kiểm tra bot dùng 0.2 của khu hay 0.5 của scan.detect_conf).
      (c) chế độ săn không ghi hp/mp vào frames (hp=None). (d) analyze_records vẫn import mss qua vision/__init__.
      (24/11 tối, v12 — XONG trên máy dev, CHỜ KIỂM TRÊN MÁY GAME (săn 15 phút CÓ BẬT MINIMAP + ghi khi săn):
       • ĐO LẠI GIẢ THUYẾT (a): chat của 183803 chỉ có 10 dòng "아데나 획득: <tên>" trong 12,6 phút (+6 thánh giá) → phần
         lớn "lost target" KHÔNG phải quái đã chết: 24/133 lần bot đánh lại ngay con cũ cạnh nhân vật trong 1 s, ảnh
         f_00017–23 cho thấy 전사 đứng sát nhân vật 7 s rồi bot bỏ. Nguyên nhân: box mất 2 nhịp là bỏ, kể cả khi con trỏ
         trên quái vẫn là KIẾM. (conf 0.5 → 0.2 chỉ thêm 6/200 khung trận có box sát nhân vật — không phải nguyên nhân chính.)
       • 1 Kết thúc trận (features/combat.py): kiếm dưới chuột = quái còn đó, không đếm mất; chat_kill = dòng giết mới
         (KillWatcher chạy trong vòng săn qua TargetingFeature.see → sửa luôn 0.21 cho chế độ săn); box mất + không kiếm
         VANISH_CONFIRM 1,5 s → "vanished" (tính giết) nếu khu không đọc được chat, "gone" (không tính) nếu chat đọc được
         mà không có dòng giết; dòng giết tới trễ ≤3 s sau trận "gone" → tính lại là giết (late_chat_kill);
         "lost" chỉ còn khi quái chạy xa (khoảng cách tăng >64 px trong UNREACH_SEC). Sau giết: loot theo chế độ (mục 7).
       • 2 Ngưỡng: ScanSettings.conf_map — detect_conf chỉ dùng cho đúng bãi được gõ (UI ghi conf_map khi đổi);
         config cũ (0.5 từ v7, Dragon Valley) bị bỏ qua → orc dùng 0.2. meta.json "conf" = ngưỡng thật đã dùng.
       • 3 Không tới được: trong trận, khoảng cách nhân vật→khóa không giảm ≥16 px trong 2,5 s (ngoài tầm cận chiến) →
         "unreachable" + targeting.block (vị trí thế giới theo minimap 40 s; không minimap: tọa độ màn hình 8 s, xóa khi đi).
         Sau 1,2 s không tiến: minimap route "detour" → click khe hở (tối đa 2 lần/trận). vision/minimap.py: hộp 224×200
         ở (0,0) cho 1280 (co theo bề rộng; 227×202 ở 1302), xám sáng = đi được, chấm tối = vật cản, phần trong suốt =
         ngoài bản đồ, mũi tên đỏ = nhân vật ở giữa; 1 px minimap ≈ 10 px màn hình (đo phase correlation 8,5–12,5),
         cùng hướng với màn hình; BFS 4 hướng + điểm xa nhất còn nhìn thẳng = cửa; Odometry = cộng dồn phase correlation
         (cắt 216 px: OpenCV lệch +0,5 px ở bề rộng 220–225). Đọc đúng 144/144 khung có minimap (511–654), 0 nhận nhầm
         trên 510 khung tắt minimap, 0,7 ms. Minimap chỉ để SẮP XẾP mục tiêu (cùng phía trước) và gợi ý đường vòng; quyết
         định bỏ dựa trên tiến độ thật (mặt nạ quanh mũi tên còn nhiễu, ban ngày cảnh nền lộ qua minimap trong suốt).
       • 4 Wander (features/exploration.py): có minimap → chấm điểm 8 hướng: heat (box YOLOX mọi lượt quét, theo tọa độ
         thế giới, giảm nửa mỗi 60 s) + frontier (chưa đi qua 120 s) + hướng vào giữa vùng đi được + phạt ngoài bán kính
         120 px minimap quanh điểm bắt đầu (chuẩn bị 1.2), bỏ hướng đâm vào vật cản (hết hướng → đi qua khe). Không
         minimap → như v11. Mỗi lượt log + event "wander" (dir, why, điểm).
       • 5 frames.jsonl khi săn có hp/mp/minimap; vision/__init__ lười (PEP 562) → analyze_records không cần mss.
       • 7 Nhặt đồ: LootSettings.mode auto (mặc định) / walk_f4 / walk_click (+max_dist 300, wait 2 s; config cũ
         enabled=True → walk_f4); đi tới chỗ quái chết (bỏ nếu xa / minimap báo sau tường), F4 hoặc click đốm sáng gần
         xác, chờ dòng chat mới; event "loot". Nút "Tự nhận biết" (tab Săn): ≥5 lần giết, ≥50 % có dòng giết → auto.
         Xác: box "die" ≤20 px → bỏ khỏi ứng viên; con trỏ thánh giá không bao giờ là kiếm nên không đánh xác.
         ĐO 183803: 10 dòng "아데나 (n) 획득: <tên quái>" với nhặt đồ TẮT, bot không bấm F4 / không đi tới xác → server
         này tự vào túi (dòng có tên quái = adena từ con vừa giết).
       • 6 Test: tests/test_hunt_183803.py (nay test_hunt_records.py) chạy CHÍNH engage/targeting/exploration trên 654 khung (đồng hồ giả, con trỏ =
         box YOLOX ≤30 px quanh chuột, "frozen" tắt vì 1 khung/s): 85 trận mô phỏng → chat_kill 6, gone 20, unreachable 8
         (bị đánh dấu), lost 0 (v11: 133/139), 51 "cut" = bot mới còn đánh tiếp lúc v11 đã bỏ để rê con khác; 7/10 dòng
         giết rơi vào trận mô phỏng. Wander 23 lượt trên khung 506–654: 16 theo minimap (thẳng/qua khe, không lượt nào
         đâm vào vật cản), 7 quay vòng (khung chưa có minimap). smoke_test thêm các kết thúc trận mới + loot modes.
         GIỚI HẠN: ảnh là của bot v11 (nhân vật đi theo bot cũ) → số "gone"/"cut" chỉ là ước lượng; con trỏ thật chỉ có
         lúc rê. Đo thật: bản ghi v12 tiếp theo (events.jsonl, analyze_records in "wander ... why").
       • Đóng gói dist/LineageAuto_20261124_v12.zip; HUONG_DAN/GUIDE_KO mục v12 (BẬT MINIMAP).)
- [x] 0.28 "KHỰNG" KHI SĂN (người dùng báo 24/11 19:15; records_game/20261124_190646_hunt 625 khung, log
      records_game/game_pc_session_log_1920.txt): KHÔNG phải tool treo – bot bị KẸT VÀO MỘT MỤC TIÊU quá lâu:
      19:13:16→19:14:10 (54s) chỉ kết thúc nhờ "combat burst cap"; 19:08:59 (31s), 19:09:44 (30s), 19:15:36 (19s)...
      Ảnh _check/stall_1913.jpg (f_00347..387): nhân vật trong CỎ CAO + cây rậm, orc 전사/창병 ngay phía trên, chat không
      có lượt giết mới suốt 54s → đánh không trúng / bị cỏ-cây chắn / click trúng nhãn tên. Phiên này: 86 lần đánh, 82
      "lost", 2 kill ghi nhận, hover_confirm 85%, 309 wander. Sửa: giới hạn mỗi trận ~8s nếu KHÔNG có tiến triển (không
      dòng chat giết, không thấy thanh HP quái giảm, nhân vật không lại gần) → bỏ, đánh dấu vị trí không tới được, chọn con
      khác; burst cap hiện tại quá dài. Bảng TeamViewer trên máy game che hotbar phải-dưới trong ảnh (nên thu nhỏ).
      Dừng bot qua TeamViewer vẫn KHÔNG được khi đang săn (nút Dừng, ESC gửi từ xa, bấm cửa sổ tool đều không ăn) → 0.7
      cần xem lại: nút Dừng phải ăn ngay cả khi bot giữ chuột (kiểm tra bằng luồng UI riêng / GetAsyncKeyState chuột).
      (24/11 tối, v12 — XONG trên máy dev, CHỜ KIỂM TRÊN MÁY GAME:
       • Kẹt mục tiêu (features/combat.py): tiến triển = dòng chat giết hoặc nhân vật lại gần ≥16 px; đứng cận chiến
         KHÔNG còn tính là tiến triển. 5 s không tiến triển → bước sang bên 60 px 1 lần (bên nào minimap thông) rồi đánh
         lại; 8 s (NO_PROGRESS_SEC, kể cả khi con trỏ vẫn KIẾM) → "no_progress" + targeting.block (~40 s). Trần tuyệt
         đối MAX_FIGHT_SEC = 15 s (150 nhịp giữ làm lưới an toàn). THANH HP QUÁI: KHÔNG có trên ảnh — thanh đỏ trên đầu
         là HP của NHÂN VẬT (dài 42/65 px khi HUD 124/190, 53/65 khi 153/190) → không dùng. Điểm giữ chuột = tâm box
         +15 px (thân dưới); chữ tên ở ~45 px phía trên → không đổi (v12 không giữ chuột trên chữ tên; chỉ đường skill
         _cast_at_target dùng bảng tên, pháp sư này không bật skill tấn công).
       • summary.json "fights" (nhóm kill/gone/unreachable/no_progress/cap/lost: số trận + giây TB) + "fight_endings"
         theo từng kiểu; events fight_end có "seconds"; analyze_records in dòng "fights".
       • Giả lập (tests/test_hunt_records.py, thay test_hunt_183803.py): 190646 → 58 trận: cut 27, gone 13 (TB 4,3 s),
         unreachable 11 (3,9 s), no_progress 4 (9,9 s), kill 3 (5,2 s); 15 chỗ bị đánh dấu, 5 lần bước sang bên;
         trận f_00340–395 (v11: 54 s, cap) kết thúc sau 5,7 s ("gone"). Trận dài nhất ≤ 15 s (v11: 54/31/30/19 s).
         183803 → 84 trận: cut 51, gone 19, unreachable 8, kill 6, lost 0 (v11 133/139 lost).
       • Dừng qua TeamViewer: log 19:06–19:18 KHÔNG có dòng lý do dừng nào → các lệnh dừng không tới được tool. Nguyên
         nhân chính: khi bot GIỮ chuột trái (đánh kiểu kéo), cửa sổ game giữ mouse capture → click từ xa (nút Dừng, cửa sổ
         tool, lối tắt DUNG) đều vào game; bot lại di chuột mỗi nhịp. Sửa: winapi/hotkeys.RemoteInputWatch = hook chuột +
         phím mức thấp trên luồng hotkey, chỉ bật khi đang săn với Interception: input BỊ TIÊM (LLMHF/LLKHF_INJECTED =
         SendInput của TeamViewer; Interception trông như phần cứng) — click/phím bất kỳ hoặc rê ≥30 px → dừng + nhả chuột.
         Mọi đường dừng nay ghi "[ENGINE] stop: <lý do>" (ESC hotkey / polled / keyboard hook / tool window / Interception /
         remote mouse / remote key / Stop button / stop key / STOP file). tests/test_remote_stop.py (SendInput thật trên
         máy dev): rê 40 px → dừng sau 85 ms; ESC → dừng. Lưu ý: ctypes.WinDLL riêng (đặt argtypes lên windll dùng chung
         sẽ đụng gói `keyboard`). CHƯA BIẾT: game chạy quyền Admin mà tool không thì hook mức thấp có nhận input không
         (UIPI) — log v12 sẽ cho biết ("remote input watch=True" + dòng stop).
       • 1_CAI_DAT.bat: mở tool xong thì đóng cửa sổ cmd (chỉ còn pause khi lỗi / cài driver).
       • HUONG_DAN/GUIDE_KO: bật minimap, thu nhỏ bảng TeamViewer, rê chuột trên TeamViewer = dừng.)
- [x] 0.29 v12 SĂN Ở "오크 숲" (24/11 20:55, người dùng báo "đi vòng vòng"): góc trái dưới ghi 오크 숲 (bãi ngoài trời, KHÔNG
      phải 오염된 축복의 땅), quái gần nhân vật "아투바 오크" (orc thường, không phát sáng xanh) → model orc_v1 (học orc
      오염된 phát sáng) gần như không thấy → 0 giết sau ~2 phút, wander liên tục. Minimap TẮT. Chat có "마법 사용: 실패!
      올바른 대상이 아니거나 취소함" → bot bấm skill tấn công khi không có mục tiêu hợp lệ. Đây là bằng chứng đầu tiên cho
      0.20: orc khu khác (khác màu) chưa được model nhận. Việc: thu quan sát ở 오크 숲 (아투바/네루가/두다마라/간디 오크…),
      đo model offline, fine-tune chung; thêm khu 오크 숲 vào danh sách; không bấm skill tấn công khi chưa khóa mục tiêu.
- [x] 0.30 v12 TRÊN MÁY GAME (24/11 20:54–20:59, 오크 숲): dừng qua TeamViewer bằng rê chuột/click/ESC KHÔNG ăn; log có
      "remote input watch=True" (20:54:49) nhưng KHÔNG bắt được rê chuột/click/ESC từ TeamViewer (có thể TeamViewer gửi qua
      driver riêng nên không mang cờ injected, hoặc game giữ chuột). File STOP gửi qua TeamViewer File Transfer vào C:\LineageAuto\main\STOP → dừng ngay
      ("[ENGINE] stop: STOP file"). Cách dừng chắc chắn từ xa hiện tại = File Transfer gửi file STOP (mẫu ở
      records_game/_stop/STOP). Phiên này: 583 lượt quét, 528 wander, chỉ 3 trận; luật 8s "no progress → blacklist" và
      "side step" đã chạy đúng. Sửa: ghi log mỗi sự kiện chuột/phím mà watcher thấy (nguồn, cờ) để biết TeamViewer gửi kiểu gì.
      (24/11 khuya, v13 — XONG trên máy dev, CHỜ KIỂM TRÊN MÁY GAME:
       • 1 TÍN HIỆU GIẾT: chat "아데나 (n) 획득: <tên>" = số 1 (đã có từ v12: chat_kill); nay so tên dòng giết với tên đọc
         trên đầu con đang khóa lúc bắt đầu trận (log "= locked" / "!= locked X", cần khuôn tên của khu). Box mất ≥1,5 s
         không còn kiếm: chế độ nhặt "auto" + chat đọc được → "gone"; server rơi đất (walk_f4/walk_click) → "vanished" =
         GIẾT + vị trí xác (combat.last_anchor) cho nhặt đồ. summary.json "fights": kill_chat / kill_fall (die_box,
         vanished, frozen) / kill_corpse_cursor / gone / no_progress / unreachable / cap / lost + "chat_kill_lines".
         KHÔNG làm được "theo dõi box 5 lần/giây": YOLOX đầu vào cố định 640×640 (~37 ms máy dev, ~160 ms máy game) nên
         cắt vùng quanh mục tiêu không nhanh hơn; cần xuất model nhỏ hơn (320) nếu muốn. Dáng "nằm" = lớp corpse của orc_v2.
       • 2 MODEL NHẬN XÁC: label_tool --corpse (lượt 2 trên khung ĐÃ duyệt, khung ±2 quanh con trỏ thánh giá hiện trước,
         phím 8 = corpse, Enter = "corpse_done"); export_dataset --classes corpse (orc=0, corpse=1); train_orc.ps1
         -Classes corpse (ORC_CLASSES=2); bot đọc bố cục lớp theo bề rộng đầu ra ONNX (yolox_mobs.class_layout:
         6 = orc_v1, 7 = orc+corpse, 8+ = monster/figure/die) → hộp corpse bỏ khỏi ứng viên + tín hiệu chết + vị trí
         nhặt. 4 bản ghi đã duyệt có 0 hộp corpse → CHƯA TRAIN orc_v2, v13 đóng gói orc_v1. docs/TRAINING.md 6.7.
       • 3 Nhặt đồ server rơi đất: dùng vị trí "vanished"/die_box (không cần thấy xác); đi tới / F4 / click / chờ "획득"
         như v12 (bỏ nếu xa, sau tường, quá wait).
       • 4 "마법 사용: 실패": KillWatcher nhận dòng này (khuôn data/chat/magic_fail.png cắt từ 183803 f_00100, điểm 1,0 /
         các dòng khác ≤0,24) → log "chat: 마법 사용: 실패 (F5 pressed 0.3s before)" + tạm ngừng skill tấn công 5 s.
         ĐO: 1 dòng/bản ghi (183803 f_00002, 190646 f_00069 = 3 s sau "heal skill F5" 19:07:58); log 20:49–20:59 KHÔNG
         có lần bấm skill tấn công nào (cấu hình tắt hết) → nguồn là HỒI MÁU F5 / buff tự-cast lúc bắt đầu (cả 3 buff
         "icon not seen"), không phải skill tấn công. Skill tấn công vốn chỉ bấm trong engage (sau con trỏ xác nhận).
       • 5 Dừng từ xa: winapi/hotkeys.CursorWatch — con trỏ dời >40 px khi bot không di chuột (InputController.last_move_t,
         đặt cả trước và sau move) = người dùng → dừng; không cần cờ injected. 10 s đầu mỗi lần săn log "[HOTKEY] input
         seen: mouse msg=… flags=… extra=… xN". test_remote_stop: SendInput rê → dừng 80 ms, ESC → dừng, SetCursorPos
         (không cờ injected) → dừng. File STOP qua File Transfer = cách chắc chắn, ghi trong HUONG_DAN/GUIDE_KO.
       • 6 Khu "오크 숲": data/monsters/orc_forest.json (hunt_map null → thu dữ liệu). Chỉ "아투바 오크" đã thấy trong game;
         네루가/두다-마라/간디 오크, 오크 궁수, 오크 스카우트 ghi "verify". Bản ghi 205449 chưa kéo về → chưa đo orc_v1.)
Giai đoạn 1 — Săn cơ bản
- [x] 1.1 Đánh "nhấn–kéo nhẹ–thả" (mặc định) / "kéo vào khung chat"; đánh lại nếu quái chạy xa (A6)
      (RÀ 26/11: nhấn–giữ–kéo là cách đánh duy nhất từ v11 (`combat._hold_and_drag`), bám theo box và đánh lại khi
       quái dịch (`track_current` + `_refresh_hold`); quái chạy xa > best+4x16 px = "lost" rồi quét lại.
       BỎ biến thể "kéo vào khung chat": không cần, cách hiện tại đạt 5,25 giết/phút ở bản v20.)
- [x] 1.1b ĐÁNH TỪNG CON: chọn con gần nhất, giết xong mới sang con khác, không đánh lan; ưu tiên con đang đánh mình (A8)
      (RÀ 26/11: ứng viên xếp gần nhất trước (`targeting.candidates`), mỗi lúc chỉ một khoá; chỉ đổi mục tiêu khi
       khoá hiện tại CHƯA sát người và có con sát người (0.39/6, `closer_than` + xác nhận bằng rê chuột);
       "đang đánh mình" = HP đang tụt + box ≤ 70 px → `session._defend` (0.39).)
- [x] 1.1c Con trỏ tấn công = KIẾM hoặc CUNG (đăng ký cả hai), quái chết = THÁNH GIÁ (A8)
      (XONG 24/11: mọi is_attack/is_corpse/classify (targeting, combat, grid_scan, observe) đi qua
       CursorProfile.classify, loại "attack" giữ nhiều hình; nút 등록/phím tắt cho attack nay CỘNG thêm hình
       (không thay) → đăng ký mũi tên không xóa kiếm. Test với c0e0783028000000 + c0c0201818000000 và bản ghi
       193903: 60 khung = attack.)
- [~] 1.2 (BỎ, làm lại ở 1.7) Phạm vi săn tại chỗ/3/5/10/15/20/30 bước (ĐO BẰNG MINIMAP, không dùng "/위치"), quay về điểm xuất phát
      (XONG 26/11, v21rc1: `ScanSettings.hunt_range` (0 = không giới hạn, 1 = tại chỗ, 3/5/10/15/20/30) + ô
       "Phạm vi săn (bước)" ở tab Săn. Điểm xuất phát = vị trí odometry đầu tiên sau khi bấm Bắt đầu
       (`ctx.state["home"]`, ExplorationFeature.observe; minimap tắt rồi bật lại = epoch mới = mốc mới).
       1 bước = `scan.step_mm` nếu đã đo, nếu chưa thì `minimap.STEP_MM` = 2,3 px minimap (1.2b).
       HIỆU CHỈNH (26/11): nút "Đo bước" ở tab Săn — bật minimap, bấm Đo, đi thẳng 5 click (1 click = 2 bước = 10 bước), bấm Xong;
       tool theo odometry 0,3 s/lần rồi lưu px minimap/bước vào config (`scan.step_mm`, KHÔNG cần build lại) và
       ghi log `[STEP] ... = x.x minimap px per step, saved`. Ngoài khoảng 1-20 = đo sai, không lưu.
       KHÔNG tự đi 10 bước hộ: lệnh đi là click theo px, đúng cái đang cần đo.
       Chọn mục tiêu: `TargetingFeature.out_of_range` bỏ quái ngoài phạm vi (đếm out_of_range_skip).
       Lang thang: vòng tròn phạm vi thay MAX_RADIUS_MM khi chấm điểm hướng; ra ngoài phạm vi → đi bộ về
       (why go_home); 1 bước = KHÔNG click đi bộ. Trận đang đánh ngoài phạm vi vẫn đánh xong.
       Không có minimap: phạm vi bị bỏ qua + cảnh báo "Phạm vi cần minimap" (KHÔNG làm dự phòng theo thời
       gian đi bộ — không có tín hiệu vị trí nào đáng tin). Ghi: home_dist (bước) trong mỗi event wander,
       analyze_records in xa nhất/TB + số lần đi về. Test: `tests/test_hunt_records.py` check_range trên
       20261126_101941_hunt với phạm vi 5 và 10.)
- [~] 1.2c (BỎ, gộp vào 1.7) Săn TẠI CHỖ (hunt_range = 1) theo class (XONG 27/11, v21rc5).
      Trước: range_mm = tầm cận chiến (70 px) → Pháp sư/Tiên tại chỗ chỉ đánh quái đến sát người; bị đẩy lệch thì
      không về; tắt minimap thì "tại chỗ" bị bỏ qua và bot đi lang thang.
      Nay (`targeting.in_place` / `ranged`, `CombatStyle` của class: mọi class trừ MELEE là đánh xa):
      - Chọn mục tiêu đo trên MÀN HÌNH từ nhân vật (không cần minimap): đánh xa ≤ `IN_PLACE_SHOT_PX` 350 px,
        cận chiến ≤ `MELEE_DIST` 70 px.
      - Đánh xa: `combat.engage_ranged` - KHÔNG giữ/click chuột trái vào quái, chỉ bắn phép (phím → chờ ellipse →
        click); không có ellipse = click phải hủy, không click (click trơn = đánh tay = đi tới); cast_order
        click_key đổi thành key_click. Không phép nào sẵn sàng (MP/hồi chiêu) = đứng chờ. Kết thúc: dòng chat
        giết, box mất `BOX_GONE_SEC`, quái ra ngoài 350 px, trần `melee_max_sec`. Không đi nhặt đồ (loot
        skipped=stay_put).
      - Cận chiến: như cũ, chỉ con sát bên.
      - Bị đẩy lệch > `exploration.IN_PLACE_DRIFT` 3 bước (odometry) → 1 click go_home; còn lại đứng yên.
        Minimap tắt → đứng yên hẳn + cảnh báo `warn_in_place_minimap`.
      - UI: "Phạm vi săn (bước; 0 = không giới hạn, 1 = tại chỗ)"; bỏ khung "Sắp có (PLAN 1.2)" ở tab Ghi.
      Test `check_in_place_101941` (test_hunt_records): pháp sư 74 trận, 64 phép (15 vào quái > 140 px), 0 lần giữ
      chuột / click không có ellipse; wander chỉ click go_home khi lệch > 3 bước; minimap tắt = 0 click.
      Chưa làm: cung của Tiên (click trái vào quái trong tầm cung) - chưa có bản ghi Tiên đánh cung để kiểm tra
      click đó không biến thành đi bộ; Tiên tại chỗ hiện chỉ dùng phép tấn công.
- [x] 1.2b Đo bước trên máy game không lưu được (XONG 26/11, v21rc2, bản ghi 20261126_192615_observe: 2 đoạn x 5 click = 10 bước).
      Nguyên nhân THẬT: odometry mất dấu, không phải sai đơn vị (48 px client / scale 10 = 4,8 px minimap ≈ 4,5 đo
      được). Minimap TRONG SUỐT: tương quan trên ảnh xám thô chỉ đạt peak 0,02-0,2 khi đi → bỏ 8/10 bước → log
      `[STEP]` 3,3-4,0 (tổng px client/bước, cần ~45) bị loại. Sửa: `minimap.odo_marks` = black-hat 11 px > 50
      (chỉ giữ chấm/đường tối nhỏ của bản đồ, bỏ cảnh lộ dưới nền và vùng tối lớn), che mũi tên r=10 → peak
      0,65-0,92, mỗi bước (+4,-2)/(-4,-2) đúng. Peak < `Odometry.MIN_RESPONSE` (0,3) = bỏ, giữ vị trí cũ.
      Đơn vị thống nhất: 1 bước = px minimap (`scan.step_mm`, mặc định `minimap.STEP_MM` 2,3, hợp lệ 1-20);
      `step_px` (px client) của v21rc1 không còn được đọc. range_mm / steps_from_home dùng thẳng đơn vị đó.
      Kiểm lại: go_home (hướng = hiệu toạ độ odometry) và vùng rào (`targeting.block`: toạ độ odometry,
      so khoảng cách * scale với BLOCK_RADIUS px client) đã đúng đơn vị, chỉ hưởng lợi từ odometry tốt hơn.
      Test: `python tests/test_odometry.py` (vị trí (-20,+10) rồi (0,+20) = bản đồ dịch (+20,-10) rồi (0,-20);
      "Xong" sau 5 click lưu ~2,2; peak thấp giữ vị trí; config cũ/ngoài khoảng → mặc định).
      SỬA 26/11 (đo trên máy game): 1 click trong game = 2 bước; đo 5 click = 10 bước ra 2,3 px minimap/bước.
      "5 bước" của 192615 thật ra là 5 click = 10 bước → mặc định cũ 4,5 bị gấp đôi; `STEP_MM` = 2,3.
      Hướng dẫn nút Đo bước: "1 click = 2 bước, đi 5 click thẳng" (`scan_panel.CLICK_STEPS`; MEASURE_STEPS vẫn 10).
- [x] 1.3 Về làng khi HP < 30–40% (cuộn F8 mặc định, cấu hình được) → DỪNG (A5)
      (XONG 23/11: HealthSettings.return_town/return_pct=35/return_key=F8, mặc định TẮT; dòng mới trong khung HP;
       HP dưới ngưỡng 2 lần đọc → thả chuột, bấm cuộn 1 lần, trạng thái "귀환 - 정지됨"; hồi máu/bình chạy trước.
       CHƯA KIỂM TRÊN GAME: cuộn phải nằm ở trang hotbar đang mở; chưa kiểm tra đã thật sự về làng)
- [ ] 1.3b QUAY LẠI BÃI SĂN sau khi về làng (cần cho 24/24, PLAN 0.38). Người dùng xác nhận (25/11): về bãi bằng ĐI BỘ
      hoặc nhờ NPC 장로 노나메 (화전민 마을) dịch chuyển. Hộp thoại 노나메 (docs/game_reference/npc_teleport_nonamae_oyeom.png,
      ảnh chụp điện thoại, nghiêng → KHÔNG cắt mẫu được): 2 cấp — "오염된 축복의 땅의 … 중 어디로 가겠는가?" rồi
      요정의 땅 / 인간의 땅 / 오크의 땅 / 정령의 땅; dòng dưới chuột tô xanh lá. Có cả "타락한 축복의 땅의 봄/여름/가을…".
   Thiết kế (ưu tiên NPC; đi bộ theo điểm mốc minimap để sau):
   1. Về làng do HP thấp (1.3) → nếu bật "Quay lại bãi săn": đứng hồi tới HP/MP ≥ 90 % (hoặc bình nếu cấu hình).
   2. Tìm 노나메: tên trên đầu + con trỏ NPC (rê quanh nhân vật, như targeting nhưng chờ kind "npc").
   3. Click → đọc chữ trong hộp thoại, chọn dòng đúng bãi đang chọn (theo mẫu chữ, KHÔNG toạ độ cứng; hộp thoại khác
      mong đợi → không làm gì, dừng + cảnh báo).
   4. Sau dịch chuyển: tên bản đồ góc dưới trái phải đúng bãi → săn tiếp; sai → dừng.
   5. An toàn: tối đa N lần quay lại / giờ (mặc định 6); chết (thánh giá) / hết bình / hết cuộn → dừng hẳn + cảnh báo.
   XONG (25/11): bước 4 — `vision/map_name.MapNameReader` đọc tên bản đồ góc dưới trái (mẫu chữ data/map_names/,
      cắt bằng tests/build_map_names.py; so cả dòng + đuôi 40 px vì 4 mùa chung "타락한 축복의 땅의"). Trên 11 bản ghi
      (1187/1280/1302/1334 rộng): 0 lần đọc sai, ≤ 2,5 % khung không đọc. "오염된 축복의 땅" không ghi khu con
      (오크/요정…) → bước 4 chỉ xác nhận được bản đồ, không xác nhận được khu. tests/test_map_name.py.
   CẦN ẢNH TỪ MÁY GAME (quay bằng chế độ "관찰만 기록", nhịp 1 s, trong lúc người tự làm một chuyến về làng → bãi):
      · tên bản đồ khi đứng trong 화전민 마을 (góc dưới trái);
      · 노나메 trong làng: đứng gần, rê chuột lên người (tên trên đầu + con trỏ NPC), vài góc khác nhau;
      · hộp thoại 노나메 đủ các dòng: cấp 1 (오염된 / 타락한 …), cấp 2 có 오크의 땅 và đủ 봄/여름/가을/겨울;
        rê chuột qua từng dòng (dòng tô xanh) — ảnh chụp từ tool, không chụp bằng điện thoại;
      · khung hình ngay sau khi dịch chuyển tới từng bãi.
- [x] 1.4 Nhiều loại bình hồi phục (HP/MP), phím + ngưỡng riêng
      (XONG 23/11: HealthSettings.potions = 3 ô "bình thêm" (bật, HP/MP, ngưỡng %, phím, chờ giây), mặc định TẮT;
       bình chính cũ giữ nguyên; skill hồi/bình chính chạy trước, mỗi lượt đọc chỉ bấm 1 bình, ô trên ưu tiên;
       bình MP cần đọc được số MP trên HUD. Chưa: kiểm tra trùng phím với skill/buff, đổi trang hotbar F1/F2/F3)
- [x] 1.7 PHẠM VI SĂN N BƯỚC (code xong 27/11, chờ đo máy game) — LÀM LẠI, thay 1.2/1.2c (gốc + N bước, không wander, đánh xong về gốc;
      pháp sư/tiên đứng im theo CLASS; vị trí = cộng dồn dịch chuyển, minimap chỉ đối chiếu) — xem mục 1.7 (27/11)
- [ ] 0.43 Quái ở GẦN bị sót / không nhận lại / đổi mục tiêu sai: đo trước-sau rồi sửa (giữ vết quái qua khung,
      khung đầy mỗi 1 s trong trận, < 100 px không blacklist dài) — xem mục 0.43 (27/11)
- [x] C (1.8) Thời gian buff nhập theo GIÂY, bước 10 s (XONG 27/11; config vẫn lưu phút nên bản cũ tự đúng:
      11,5 -> 690 s; tests/test_buff_duration.py)
- [x] 0.44 Lượt "tại chỗ" v21rc5 hỏng: không bắn phép (ô phép không bật mà bot im lặng) + đi qua đi lại
      (nhiễu odometry) — XONG 27/11, xem mục 0.44; phần tính vị trí đúng vẫn ở 1.7
- [x] 0.45 NGHIÊM TRỌNG: "Áp dụng" trong Cài đặt skill xoá phép tấn công ở trang F2 khi có buff trùng PHÍM
      (không trùng ô) — dựng lại được và đã sửa 27/11, xem mục 0.45; đây cũng là gốc của 0.44 mục 1
- [ ] 3.0b Chế độ "kéo quái" cho hiệp sĩ (ghi 27/11, làm sau 1.7)
- [x] 1.4b Bình: thời gian chờ dài + tự biết hết bình (XONG 27/11, v21rc5, bản ghi 20261127_003555_hunt).
      Đo: F1+F6 = 2 bình mana, chờ 1,5 s; MP < 50 % từ ~135 s → 2 bình uống hết trong 1,5 s (137 s), rồi bấm ô
      TRỐNG mỗi 1,5 s suốt 12 phút. MP không có lần tăng ≥ 15 nào. 67/69 lần quay về F1 giữa trận đều sau 137 s,
      0,5 s sau mỗi phép trên F2 → ~134/222 page_switch là do bấm ô bình trống (phép F2 ↔ bình F1).
      Sửa 1: `PotionSetting.cooldown` tối đa 3600 s (`COOLDOWN_MAX`); tab Hồi máu: "chờ [số] [giây|phút]"
      (lưu luôn bằng giây; ≥ 60 s hiện bằng phút). Bình mana 10 phút = "chờ 10 phút".
      Sửa 2: `vision/hotbar.py` (ô F5-F12 ở góc dưới phải, co giãn theo chiều rộng client; tab trang sáng nhất =
      trang đang mở). Ô vật phẩm hết = ô tối chỉ còn nhãn phím mờ: độ sáng p99 55 vs 255 khi còn (ô kỹ năng
      tối vì hồi chiêu 60-62 → chỉ dùng cho Ô BÌNH). 716 khung 003555: 538 khung trang F1 đọc đúng 100 %.
      `HealthFeature._out_of_potions`: khi bình đến lượt, đọc ô (≤ 1 lần/s, chỉ khi trang của ô đang mở);
      2 lần trống liên tiếp → đánh dấu hết, KHÔNG bấm nữa; xem lại mỗi `RECHECK_SEC` 3 phút (có lại → bấm tiếp)
      hoặc khi bấm Bắt đầu. Log WARNING, event `potion_empty` {slot, stat}, đếm `potion_empty`, UI cảnh báo
      "Hết bình ở F1+F6" (`ctx.state["potion_empty"]`). Chưa đọc dòng chat "hết vật phẩm" (ảnh ô đã đủ).
      Test `python tests/test_potions.py`.
      magic_fail 40/146 (003555): ghép theo spell_mp, 37 phép thất bại ("마법 사용: 실패! 올바른 대상이 아니거나 취소함"
      = mục tiêu không hợp lệ/hủy), 50 phép không trừ MP. Phép hỏng: khoảng cách trung vị 101 px (phép tốt 53),
      giây thứ 1,5 của trận (tốt 2,5), 27/37 trận kết thúc < 1 s sau đó (16 `gone`) = quái đã chết/biến mất khi
      phép tới; 14/37 con trỏ trước phím KHÔNG phải kiếm (80e0e0e060000000; phép tốt 18/109) = trỏ chưa nằm trên
      quái. Chưa sửa (đề xuất: chỉ bắn khi con trỏ trước phím là attack, bỏ phép khi box vừa mất).
- [ ] 1.5 Nhặt hết đồ: F4 (chính) + click (dự phòng), sau mỗi con chết (A7)
      (F4 XONG 23/11: features/loot.py + khung "줍기" (bật, phím F4, số lần bấm=2), mặc định TẮT; chỉ chạy khi trận kết thúc
       bằng giết (corpse_cursor/die_box/frozen), thả chuột, chờ 0.3s giữa mỗi lần bấm, ESC dừng được, đếm state["loot_presses"].
       CÒN: click dự phòng — chỉ làm nếu F4 không nhặt hết trên Classic (PLAN: "F4 → CẦN KIỂM TRA TRONG CLASSIC");
       CẦN DỮ LIỆU GAME: bật chế độ 2 + nhặt đồ, xem chat "획득" và ảnh còn nhãn "아데나" sau khi bấm F4)
- [~] 1.6 KHUNG Ô KỸ NĂNG PHÍM TẮT (yêu cầu người dùng 23/11 19:24 — QUAN TRỌNG) — PHẦN ĐÁNH ĐƠN MỤC TIÊU XONG ở
      v16 (xem 0.33: mọi skill role="attack" tự dùng được, mỗi ô có MP%/tầm/hồi chiêu, thứ tự bấm cấu hình được,
      trang F1). CÒN LẠI: AoE theo số quái trong bán kính, chế độ săn "Tại chỗ"/"Diện rộng", đổi trang F2/F3.
      Mô tả gốc: một bảng ~10 ô kỹ năng/hiệu ứng
      tăng cường, mỗi ô = (trang F1/F2/F3 + phím F5–F12 hoặc Ctrl+1..8) + VAI TRÒ + điều kiện dùng:
      - Đánh DIỆN RỘNG (AoE): dùng khi ≥N quái trong bán kính R quanh nhân vật (N, R cấu hình), có hồi chiêu/MP tối thiểu.
      - Đánh đơn mục tiêu: chèn vào nhịp đánh từng con (1.1b), mỗi X giây hoặc khi quái còn HP thấp/cao.
      - Buff/hiệu ứng tăng cường (giáp, tốc độ, khiên, vũ khí…): buff lại khi hết (2.1b), thời lượng từ catalog skill.
      - Hồi máu/MP, giải độc: theo ngưỡng (đã có HP/MP, cure_poison).
      Kèm CHẾ ĐỘ SĂN chọn được: "Tại chỗ" (đứng yên, chỉ đánh quái lại gần / trong tầm skill, hợp với AoE) và
      "Diện rộng" (đi tìm quái trong bán kính 3/5/10/15/20/30 bước rồi quay về điểm xuất phát — gộp với 1.2).
      Gộp/thay thế: khung "스킬 설정" hiện tại (attack_skills/buff_skills theo F5–F12), 2.1 (15 ô buff). Dùng chung
      một mô hình dữ liệu ô kỹ năng cho cả đánh và buff; mỗi ô có thứ tự ưu tiên, bật/tắt, kiểm tra MP đủ.
      Cần hỏi lại người dùng: "diện rộng" là chế độ di chuyển rộng hay kỹ năng AoE (ghi cả hai ở trên).
Giai đoạn 2 — Buff & MP
- [ ] 2.1 15 ô buff, mỗi ô = (trang F1/F2/F3, ô F5–F12), skill hoặc vật phẩm (A4)
- [x] 2.1b BUFF LIÊN TỤC: giáp/tốc độ/biến hình hết là buff lại ngay; phát hiện hết qua chat "사라집니다", icon cột buff, đồng hồ; chèn buff giữa nhịp đánh (A3/A4+)
      (XONG 26/11 v21rc1 qua ĐỒNG HỒ + DÒNG CHAT (chi tiết ở 0.40): dòng chat báo hết buff → xoá đồng hồ của ô đó →
       buff lại ngay ở nhịp sau, sau hồi máu. Mỗi buff một ẢNH DÒNG CHAT `data/chat/buff_gone/<skill_id>.png`
       (cắt bằng tests/build_chat_phrases.py) vì mỗi buff một câu khác nhau. Mới có ảnh của 399 인챈트 덱스터리티;
       실드/블레스드 아머 CẦN một bản ghi có ảnh (bản 001245 chỉ còn jsonl trên máy dev). Icon cột buff: chưa dùng.)
- [ ] 2.1c CHẾ ĐỘ HỌC: ghi lại người chơi buff gì/khi nào → đề xuất lịch buff để duyệt (A3)
- [x] 2.2 Đọc MP (OCR số "MP:x/y" trên HUD; mp_template là dự phòng) — xong cùng 0.3 (ctx.read_mp đọc số HUD trước)
Giai đoạn 3 — Nhiều nhân vật & tổ đội
- [ ] 3.1 Bật giao diện nhiều tài khoản
- [ ] 3.2 1 PC 2 nhân vật (để sau theo A9, làm phần lõi trước)
- [ ] 3.3 Hồi máu / buff cho thành viên tổ đội
- [ ] 3.4 Săn bán tự động nhóm: người chơi di chuyển, bot đánh/hồi/buff; vai trò nhân vật 2 tùy chọn (A8)
- [ ] 3.5 Các nhân vật TƯƠNG TÁC & HỖ TRỢ LẪN NHAU: PartyBoard, hồi/buff cho nhau, đánh cùng mục tiêu, bảo vệ, đi theo, cùng về làng/tiếp tục săn
Giai đoạn 4 — Tiện ích & nhận diện
- [x] 4.1 Thống kê (thời gian, quái đã giết, bình đã dùng, về làng, chết)
      (XONG 26/11 v21rc1: tab "Thống kê" (runtime/stats.py + ui/panels/stats_panel.py) — thời gian chạy, giết tổng
       và /giờ, giết theo loại quái, bình máu/mana, phép hồi máu, phép tấn công (và số lần phép không lên), về làng,
       chết, lùi lại; ghi records/stats_<ngày>.json mỗi 10 phút và khi dừng.)
- [ ] 4.2 Model YOLOX CHUNG cho mọi bãi/mọi quái (ngày + đêm) + công cụ thu ảnh và gán nhãn bán tự động (A1)
      (23/11 v3: thu dữ liệu XONG phần công cụ — xem 0.6b; gán nhãn tests/label_tool.py; xuất COCO/YOLO
       tests/export_dataset.py; quy trình fine-tune docs/TRAINING.md (chưa train).
       QUYẾT ĐỊNH 23/11 (người dùng): • thứ tự kênh lưu riêng từng model = HuntMap.channels; 4 model cũ "rgb" (như
       trước, benchmark không đổi), model train mới dùng chuẩn cố định "bgr" (NEW_MODEL_CHANNELS = cách YOLOX gốc đọc
       ảnh). Ghi nhận: fallen_spirit RGB 8/21 vs BGR 1/21, dragon_valley RGB 16/21 fp7 vs BGR 20/21 fp12.
       • label_tool 3 lớp: phím 1 quái (0 monster), 2 xác (2 die), 3 người chơi/NPC (1 figure); box [x0,y0,x1,y1,lớp].
       • Không có .pth → train từ yolox_tiny.pth chính thức; người dùng gửi .pth cũ sau nếu tìm thấy.
       • Người dùng tự thu dữ liệu trên máy game để làm nhận diện tốt hơn (bước tiếp theo).)
Kiểm tra thêm
- [ ] Xem thư mục log của game (C:\Program Files (x86)\NC\Lineage Classic\log) có ghi chat không → nếu có, đọc log thay vì OCR

---------------------------------------------------------------------------------------------------
- [x] 0.31 v13 SĂN 15 PHÚT (24/11 22:35–22:50, 오크의 땅, wizard Lv30, bản ghi records_game/20261124_223510_hunt):
  37 lượt "giết" (34 corpse_cursor + 3 frozen) = ~2,5 con/phút. 51 trận kết thúc no_progress (TB 9,9s = ~505s ≈ 56% thời gian),
  15 unreachable, 13 gone, 2 cap. Dừng bằng rê chuột (displacement) HOẠT ĐỘNG (2 lần 22:34:30, 22:34:59). detect_ms TB 165 ms (bench 38 ms).
  LỖI A: 40/51 no_progress có anchor cách nhân vật <66px (nhân vật ở ~(667,385) trên cửa sổ 1334x1008) = đang ĐÁNH GIÁP LÁ, bị vây
         3–4 con (f_00058) mà quy tắc 8s vẫn bỏ quái → sửa: mục tiêu kề bên + con trỏ kiếm/cung = đang đánh, KHÔNG tính no_progress
         (chỉ cap ~25s); kiểm tra luôn box có trùng chính nhân vật không (22 trận sword=no).
  NGUYÊN NHÂN LỖI A (người dùng: "không đánh quái dù nó ở gần"): combat.py coi "đứng giáp lá không phải tiến triển" →
         5s side step 60px (66 lần!) kéo nhân vật RA KHỎI con đang đánh, 8s bỏ + skip chỗ đó (miss_ttl, toạ độ màn hình)
         → các con đang vây đánh nhân vật bị bỏ qua. Nhận diện KHÔNG kém hơn: hits/khung 4,87 (v11: 1,16–2,76), 723/729 khung có quái,
         590 khung có quái trong 150px. Chỉ có 143 lần quét / 906s (bám sai mục tiêu quá lâu).
  YÊU CẦU NGƯỜI DÙNG (24/11 23:08): (1) nhận diện quái NHANH, (2) luôn tấn công con GẦN NHẤT, (3) kết liễu 1 con = đếm 1 lần giết
         (đếm chính xác, không trùng, không đếm lượt bỏ quái).
  LỖI B: chat_kill_lines = 0 dù khung chat hiện rõ "아데나 [9] 획득: 오염된 오크 / 도끼병" (f_00024) → KillWatcher không đọc được
         trong chế độ săn (chú ý chữ hiện "[9]" ngoặc vuông, cửa sổ 1334x1008); cần test với ảnh f_00024/f_00058.
  (24/11 khuya, v14 — XONG trên máy dev, CHỜ KIỂM TRÊN MÁY GAME; dist/LineageAuto_20261125_v14.zip):
   • 1 NHẬN DIỆN NHANH: runtime/detector.DetectorThread chạy YOLOX liên tục ở luồng riêng (scan.detect_fps=5), vòng săn
     dùng kết quả mới nhất (TargetingFeature._detect; mỗi nhịp đánh chờ ≤0,3 s kết quả MỚI, quét tìm thì không chờ).
     Xuất lại orc_v1 với đầu vào 416 và 320 (train/export_onnx.py --size → model/yolox_tiny_blessed_orc_416/_320.onnx;
     các khu khác chưa có .pth → vẫn 640). ROI = vùng quanh nhân vật ±0,36w, -0,38h..+0,36h, bỏ minimap/skill/HUD dưới
     (223510: 95% hộp nằm trong vùng này). onnxruntime intra_op_num_threads = nửa số lõi, 2..4.
     ĐO (máy dev 16 lõi, 4 luồng, ms/khung): 640 toàn khung 49 · 416+ROI 24 · 320+ROI 16 (1 luồng: 144 / 62 / 39).
     Độ chính xác trên tập test orc (193903 ngày + 133425 đêm, nhãn đã duyệt), recall quái ≤150 px / ≤300 px quanh nhân
     vật: 640 toàn khung 84% / 88% (fp 21) · 416+ROI 83% / 87% (fp 17) · 320+ROI 77% / 79% (fp 13) → MẶC ĐỊNH 416+ROI.
     Máy game bản 13 đo 165 ms ở 640 → ước ~80 ms ở 416+ROI; CHƯA ĐO TRÊN MÁY GAME: log "[detect] size .. roi .. threads
     ..: X ms avg, Y/s" sau 10 s rồi mỗi phút; nếu X > 80 ms ở lần đo đầu → tự hạ xuống 320 (1 lần, có log).
     Xác nhận con trỏ chỉ 1–2 con gần nhất (scan.max_probe_points ≤ 2). Cấu hình (Quét → Nâng cao): detect_fps,
     input_size (320/416/640), detect_roi, melee_max_sec.
   • 2 GẦN NHẤT TRƯỚC: hộp có tâm ≤25 px quanh nhân vật = chính nhân vật → bỏ (f_00024: hộp (673,422) là "con quái" bản 13
     đánh 14,3 s rồi no_progress). ≤100 px: không bao giờ bỏ qua vì miss/blacklist, luôn đứng đầu (minimap chỉ xếp
     các con xa hơn), còn hộp gần thì quét lại thêm 3 lần trước khi đi lang thang. MELEE = khóa ≤70 px + con trỏ
     kiếm/cung: không side step, không no_progress/unreachable, không blacklist; chỉ hết khi chết / mất hộp / trần
     scan.melee_max_sec 25 s. Luật 0.28 (side step 5 s, bỏ 8 s) chỉ còn cho khóa >70 px. Đang đánh mà có con
     ≤70 px và < 50% khoảng cách khóa → kết thúc "switch", khóa sang con đó (rehover_last xác nhận bằng con trỏ).
   • 3 ĐẾM GIẾT: LỖI B = đọc chat ảnh THÔ. Observe 222830 trên máy game: chat_lines 174 / 174 khung (≈1 dòng/khung — chỉ
     dòng ghim trên cùng) trong khi JPEG cùng khung đọc 5 dòng; 223510 JPEG đọc offline 20 dòng giết, live 0. JPEG
     (lấy mẫu màu 4:2:0) làm nhạt màu chữ kem mảnh; ảnh thô quá bão hòa cho whiteness → chat_bands đọc vùng chat qua
     đúng JPEG q92 của recorder (lưới 16 px): live = offline. Chưa có ảnh thô để kiểm chứng → khi chat không đọc được
     (<2 dòng): log "chat not read: <lý do>" ≤1 dòng/10 s + lưu 3 ảnh raw/chat_fail_*.png vào bản ghi.
     Đếm (combat._tally): kills = kills_chat (1/dòng 획득, đánh lan 2 dòng = 2) + kills_corpse_only (corpse_cursor/die_box/
     frozen/vanished không có dòng). Dòng đến ≤3 s sau khi trận kết thúc không có dòng → của trận đó (xác → đổi thành
     chat, vẫn 1); no_progress/unreachable/gone/switch không bao giờ tự cộng. Dòng thấy lúc đi lang thang = +1.
     summary.json: kills_chat / kills_corpse_only / kills_total / detections_per_min; UI "Đã giết" = kills_total.
     events.jsonl fight_end: dist, melee, kill_source (chat/corpse/none); "kill_line" cho dòng đến trễ.
   • Kiểm tra: test_monsters.test_kill_lines_v13_hunt (f_00024/f_00058 đọc đúng 오염된 오크 + 오염된 오크 도끼병; 2 dòng
     giống nhau liên tiếp = 2). test_hunt_records chạy lại 223510: 0 trận melee kết thúc no_progress/unreachable (bản 13:
     38), side step 1 (bản 13: 66), 20/20 dòng giết đếm đúng 1 lần, ứng viên gần nhất trước + không có hộp nhân vật;
     190646: trận 54 s nay hết ở trần melee 25 s (trước: ≤10 s theo luật 0.28 — người dùng đổi luật). analyze_records:
     thời gian theo loại kết thúc, đánh / không đánh, quét/phút, detections/phút, detect_ms, giết chat vs xác
     (bản 13: đánh 835 s/906 s, trong đó no_progress 503 s; 9,5 quét/phút).
     CÒN: đo ms thật + kiểm đọc chat trên máy game (bản ghi săn 15 phút tiếp theo + session_log.txt).)
- [x] 0.32 v15 SỬA "BOT ĐỨNG IM" (bản ghi v14 thật: records_game/20261125_092741_hunt, 25/11 09:27-09:42, 오크의 땅,
      wizard, đêm, cửa sổ 1280x960, 849 khung / 911 s). Đọc chat ĐÃ CHẠY (21 dòng giết, 0 khung không đọc được),
      detect_ms 68,8 (416+ROI). Nhưng người dùng báo: bot đứng im, quái trong tầm / đang đánh mình cũng không đánh,
      8-10 s mới đánh 1 lần, không có quái thì không đi tìm. analyze_records: ĐỨNG IM 748 s / 910 s (82%), 33 đoạn
      dài hơn 5 s (dài nhất 121 s từ f_00549). Ba nguyên nhân, đã sửa:
   • 1 MELEE ĐỨNG IM (nặng nhất): 16 trận kết thúc "cap" đúng 25 s (391 s = 43% thời gian săn), anchor rỗng,
      melee=true, khóa cách nhân vật 31-69 px. Lỗi: melee chỉ cần "con trỏ attack + khóa ≤70 px", nên một anchor CŨ
      (chính sprite nhân vật / pet / người chơi khác, con trỏ vẫn đọc ra attack) giữ trận tới hết trần; thêm vào đó
      khi mất hộp mà còn con trỏ attack thì luật 0.27 reset bộ đếm "lost" → không bao giờ thoát. Sửa (features/combat.py):
      melee = con trỏ attack + khóa ≤70 px + HỘP CÓ TRONG LẦN NHẬN DIỆN MỚI NHẤT; mất hộp quá BOX_GONE_SEC = 1,0 s là
      kết thúc ngay (gone/vanished, dòng chat đến ≤3 s sau vẫn tính cho trận đó như luật 0.31); trong tầm melee mà
      KHÔNG có con trỏ attack quá NO_SWORD_SEC = 1,0 s → kết thúc "lost" (không chờ trần). Trần melee mặc định
      25 s → 10 s. "switch" sang hộp gần hơn phải HOVER xác nhận con trỏ attack trước (17 lần switch của bản ghi đều
      sang điểm cách nhân vật 26-62 px = chính nhân vật/pet; closer_than cũng bỏ qua điểm vừa hover trượt, miss_ttl 4 s).
      events.jsonl fight_end thêm box_seen_last_s + cursor_last.
   • 2 NHẬN DIỆN: ROI 416 kém hơn toàn khung 640. Đo lại trên 213 khung đêm của 092741 (mỗi khung thứ 4), hộp/khung ·
      khung trống · ms (máy dev, 1 tiến trình):
          cửa sổ      640 toàn khung    640+ROI      416 toàn khung   416+ROI      320+ROI
          1280x960    2,38 · 8% · 82    1,92·15%·84  1,85·14%·34      1,92·13%·35  1,72·16%·26
          1334x1008   2,38 · 8% · 98    1,92·14%·88  1,89·15%·37      1,92·12%·36  1,74·16%·23
      (1,92 hộp/khung của 416+ROI khớp 1,97 bản ghi v14 → đo đúng; con số 4,87 của v13 là bản ghi 223510 khác cảnh,
      không so trực tiếp được. Chỉ có ảnh ĐÊM: ảnh ngày của 193903/133425 không còn trên máy dev, 1334x1008 là ảnh
      đêm phóng to.) → MẶC ĐỊNH TRỞ LẠI toàn khung 640 (scan.input_size 640, detect_roi off): +24% hộp/khung và chỉ
      8% khung trống thay vì 13-15%. Cấu hình cũ do v14 ghi (416 + ROI + 25 s) bị coi là "không phải người dùng chọn"
      và trả về mặc định v15 (ScanSettings._detect_v15) — ai đã tự chọn 416+ROI thì mất lựa chọn đó. Tự hạ input khi
      chậm (detector._step_down) giờ chỉ xảy ra khi KHÔNG giữ nổi scan.detect_fps (640 ~165 ms trên máy game vẫn đủ
      5/s), trước đây ngưỡng 80 ms sẽ tự hạ về 416 và xóa luôn phần vừa sửa.
   • 3 KHÔNG CÓ MINIMAP → XOAY TẠI CHỖ: minimap=false cả 849 khung (người chơi tắt minimap), nên wander chạy nhánh
      "rotate": đổi hướng MỖI lần gọi (~0,3 s) → 141 lần wander, 92 "rotate" rải đủ 8 hướng = nhân vật chỉ quay tại chỗ.
      Sửa (features/exploration.py): không có minimap thì GIỮ MỘT HƯỚNG DWELL_SEC = 4 s (ưu tiên hướng con cuối cùng,
      PURSUE_CLICKS lần), chỉ đổi khi BỊ CHẶN = ảnh thu nhỏ 64x48 thay đổi < BLOCK_MOTION (1,0 mức xám trung bình)
      trong BLOCK_SEC = 2,5 s, và khi đó lấy hướng bị chặn lâu nhất (nhớ BLOCK_TTL 30 s). Ngưỡng 1,0 đo trên chính
      092741: 74% cửa sổ 2,5 s của bản ghi đứng im có mức thay đổi < 1. Giao diện (thanh dưới) cảnh báo
      "Minimap đang tắt - bật minimap để bot tìm đường tốt hơn" (i18n ko/en/vi) khi đang săn mà không thấy minimap.
   • 4 ĐO LƯỜNG: analyze_records in "still (no movement, no attack) X s of Y s (Z%)" + liệt kê các đoạn đứng im > 5 s
      (cùng phép đo ảnh thu nhỏ như luật chặn hướng ở trên).
   • Kiểm tra: test_hunt_records thêm check_092741 (bản ghi nào không còn ảnh trên máy này thì bỏ qua): 91 trận mô phỏng,
      trận dài nhất 9,5 s (v14: 25,2 s), 0 trận "cap", hộp mục tiêu mất lâu nhất 1,2 s ở lúc kết thúc (yêu cầu ≤ 3 s).
      smoke_test: mất hộp mà con trỏ còn attack → vanished (trước: cap), trong tầm melee mà không có con trỏ attack →
      lost, switch bị hover từ chối → giữ khóa cũ.
      CÒN: chạy thật trên máy game để xem thời gian đứng im và số giết/15 phút (dist/LineageAuto_20261125_v15.zip).

- [x] 0.33 v16 PHÉP TẤN CÔNG + GIẢM TẢI CPU (bản ghi v15 thật: records_game/20261125_112040_hunt, 25/11 11:20-11:35,
      오크의 땅, wizard Lv30, 1280x960, 758 khung / 892 s). Kết quả v15: 62 giết/15 phút (25 chat + 37 corpse),
      đang đánh 84% thời gian, trận dài nhất 10,3 s. Hai vấn đề người dùng nêu, đã sửa:
   • 1 ĐÁNH TAY QUÁ CHẬM → BẢNG PHÉP TẤN CÔNG (PLAN 1.6, phần đơn mục tiêu). 26/165 trận chạm trần 10 s
      (264 s = 30% thời gian săn) vì pháp sư đánh tay mất 12-15 s/con orc. Nguyên nhân gốc: skills/policy.py chỉ
      cho tự dùng 5 id (hồi máu/buff/giải độc), nên MỌI phép tấn công gán vào ô đều KHÔNG BAO GIỜ được bấm.
      Sửa: mọi skill có role="attack" trong catalog (46 cái, đọc thẳng JSON để công cụ offline không cần cv2)
      đều được tự dùng và gán được trong modal; cơ chế chung = "target_click".
      Mỗi ô có thêm 3 cổng (config/models.AttackSkillSetting): MP% tối thiểu (dưới ngưỡng → đánh tay), tầm dùng
      tính bằng px từ nhân vật tới mục tiêu, hồi chiêu riêng (0 = nhịp mặc định của class). Sửa kèm: can_cast chỉ
      đọc MP khi mp_reader.available, mà mp_template chưa bao giờ được ship → MP KHÔNG BAO GIỜ được đọc trong trận;
      giờ đọc qua số HUD (runtime/context.can_cast).
      THỨ TỰ BẤM CẤU HÌNH ĐƯỢC (AccountSettings.cast_order, chọn trong modal "Cài đặt skill" → tab Đánh) vì chưa
      kiểm chứng được client nhận phép kiểu nào: "rê chuột → phím → click" (mặc định, như code cũ),
      "phím → click mục tiêu", "click mục tiêu → phím". Đổi ngay trên máy game, không cần build lại.
      Ô phép đặt ở TRANG F1 (người dùng chọn 25/11); đổi trang F2/F3 để sang 2.1.
      Ghi events.jsonl: spell_cast (ô, skill, thứ tự, MP trước/sau, giây thứ mấy của trận), fight_end thêm
      spells + skipped (vì sao bỏ nhịp: out_of_range / low_mp / no_nameplate / mp_empty), timing kill_sec_spell
      vs kill_sec_hand. analyze_records in "spells:" + "kill time: with spells ... bare hands ...".
   • 2 KHỰNG KHI ĐÔNG QUÁI → GIẢM TẢI CPU. Log máy game: "[detect] size 640 roi off threads 2 max 5/s:
      175-187 ms avg, 4.8/s" suốt 15 phút ≈ 0,86 × 2 luồng ≈ 1,7 nhân CPU liên tục; t=600-830 s (10-17 hộp/khung)
      game khựng. Bốn thay đổi:
      a) Tiến trình bot chạy BELOW_NORMAL_PRIORITY_CLASS (winapi/console.set_below_normal_priority, gọi từ main.py).
      b) onnxruntime intra_op_num_threads = 1 (scan.detect_threads, cấu hình trong khung "Quét" → Nâng cao;
         đặt vào yolox_mobs.THREADS TRƯỚC lần nạp model đầu tiên trong session.start / start_observe).
      c) scan.detect_fps mặc định 5 → 2 (5 bị coi là "không phải người dùng chọn" và trả về 2, như luật 0.32);
         detector tự hạ thêm 1/s khi detect_ms × fps × số luồng > 30% một nhân (CPU_SHARE).
      d) ĐANG ĐÁNH thì CỨ 2 LẦN NHẬN DIỆN có 1 lần dùng 416 + ROI quanh nhân vật (~35 ms thay vì ~180 ms), lần
         còn lại vẫn là 640 toàn khung để thấy quái xa; ĐANG TÌM QUÁI luôn là 640 toàn khung (scan.adaptive_detect,
         tắt được). combat báo trạng thái qua ctx.state["fight_until"].
      ĐO (tests/eval_detect_modes.py, ảnh thật của 092741 849 khung + 112040 4 khung, so với v15 = 640 mọi khung):
          cắt ROI MỌI khung đánh:      2,37 → 1,97 hộp/khung (-17%)  → VƯỢT ngưỡng 10% người dùng đặt, BỎ
          xen kẽ 1 đầy / 1 ROI:        2,37 → 2,18 hộp/khung ( -8%)  → ĐẠT, thành mặc định
      Hộp nằm trong 120 px quanh nhân vật (thứ duy nhất một trận đánh đọc tới) gần như không đổi: 0,37 → 0,35.
      CPU ước tính trên máy game: v15 ~1,7 nhân; v16 đang đánh (300 ms + 60 ms)/2 × 2/s × 1 luồng ≈ 0,36 nhân,
      đang tìm quái 300 ms × 2/s ≈ 0,6 nhân → luật 30% tự hạ xuống 1/s ≈ 0,3 nhân. CẦN XÁC NHẬN BẰNG LOG THẬT:
      nếu log v16 dừng ở 1/s mà tìm quái quá chậm thì tăng scan.detect_threads lên 2.
      Ghi log mỗi phút: "[detect] ...: X ms avg, Y/s, cpu Z%, N boxes/frame" (CPU lấy từ time.process_time, không
      cần psutil) + events.jsonl "detect_stats"; analyze_records in "detector load (n min): cpu ... boxes/frame".
   • 3 CHỌN MỤC TIÊU KHI BỊ VÂY: 4 lần "closer monster, switching ... at 26px" = chính sprite nhân vật →
      targeting.SELF_R 25 → 30 px. Hover xác nhận trước khi chuyển đã có từ 0.32 (combat._confirm_switch).
   • Kiểm tra: smoke_test thêm 3 thứ tự bấm phép + 3 cổng MP/tầm/hồi chiêu + events + vòng lưu/đọc config, và
      kiểm tra detector mặc định (640, không ROI, 2/s, xen kẽ 416+ROI khi đánh, tự hạ fps). test_ui mở modal
      "Cài đặt skill", gán 에너지 볼트 vào F12 với MP 20% / 400 px / 2,5 s và thứ tự "click → phím", rồi kiểm tra
      file config đã lưu. test_hunt_records (092741) và eval_detection không đổi kết quả.
      CÒN: chạy thật trên máy game (dist/LineageAuto_20261125_v16.zip) để biết thời gian giết khi có phép và
      CPU/độ khựng thực tế. Thứ tự bấm phép ĐÃ CÓ CÂU TRẢ LỜI (xem 0.34 mục 3: phím → elip → click).

- [x] 0.34 v16 HOÀN THIỆN TRƯỚC KHI CÀI LÊN MÁY GAME (tiếp 0.33, chưa chạy thật). Trang F1 của người dùng đã kín 8 ô
      (F5 Hồi phục, F6 Bình máu, F7 Bình máu lớn, F8 Cuộn về làng, F9 Tăng tốc, F10 Khiên, F11 Ban phước giáp,
      F12 Tăng cường sức mạnh) nên phép tấn công phải nằm ở trang F2.
   • 1 Ô KỸ NĂNG = (TRANG F1/F2/F3, Ô F5–F12). Thêm `page` vào AttackSkillSetting / BuffSkillSetting /
      PotionSetting và `skill_page` / `potion_page` / `return_page` cho HP. Cấu hình cũ chỉ có "F5" → trang F1.
      Bấm một ô = `BotContext.press_slot(page, key)` (mixin HotbarPages): nếu game đang ở trang khác thì bấm
      F1/F2/F3, chờ PAGE_SETTLE = 0,1 s, rồi bấm ô. Bot NHỚ trang hiện tại nên không bấm thừa; hồi máu/bình
      khẩn cấp cũng đi qua đúng đường này nên luôn tự đổi về trang của nó. Lúc Start, trang đang mở là KHÔNG
      BIẾT → đặt state về None và bấm trang nhà một lần. Hết trận → quay về `AccountSettings.home_page`
      (mặc định F1, đặt "" là không quay). events.jsonl: page_switch {from_page, to_page}.
      "Một ô chỉ thuộc một vai trò" giờ so theo (trang, ô): F1+F5 hồi máu và F2+F5 phép cùng tồn tại.
      HẠN CHẾ CÓ CHỦ Ý: mỗi vai trò vẫn lưu theo ô, nên KHÔNG thể có 2 phép tấn công cùng ô F5 ở 2 trang khác nhau.
   • 2 LUẬT CPU 30% TÁCH THEO VIỆC ĐANG LÀM: đang TÌM QUÁI không bao giờ xuống dưới 2 lần/giây (FPS_FLOOR), đang
      ĐÁNH được xuống 1 lần/giây. Luồng ONNX cũng tách: scan.search_threads = 2 khi tìm quái (640 toàn khung,
      1 luồng không kham nổi 2/s), scan.detect_threads = 1 khi đánh. Cache session của yolox_mobs nay khoá theo
      (đường dẫn, số luồng) vì số luồng bị nướng vào session lúc tạo. Log mỗi phút tách 2 dòng:
      "[detect] ...: search 180 ms 2.0/s 36%core 1.52 boxes | fight 120 ms 2.0/s 24%core 2.23 boxes |
      process cpu 42%"; analyze_records in từng mode.
   • 3 DÙNG PHÉP CÓ MỤC TIÊU ĐÚNG CÁCH GAME (người dùng xác nhận bằng ảnh màn hình): bấm phím ô → con trỏ đổi
      thành HÌNH ELIP NGẮM → click trái vào quái. Mặc định cast_order = "key_click" (bỏ bước rê chuột).
      Thêm loại con trỏ "cast" (Ngắm phép/elip) vào CURSOR_KINDS → tab Con trỏ có đủ nút/phím tắt Ctrl+Alt+5/
      danh sách "Con trỏ đã thấy", và bộ phân loại trả về "cast" chứ không phải đất/NPC/không rõ.
      Sau khi bấm phím: chờ tối đa CAST_CURSOR_WAIT = 0,3 s cho elip. Thấy → click. KHÔNG thấy (hết MP, hồi
      chiêu, sai trang) → KHÔNG click (click chỉ làm nhân vật đi bộ tới đó), ghi spell_cast {ok:false,
      reason:"no_target_cursor"}, đánh tay tiếp; 3 lần liên tiếp → tạm ngưng phép NO_CAST_PAUSE = 10 s
      (dùng lại ctx.state["skill_pause_until"] của 0.29). Chưa đăng ký con trỏ elip → cách cũ (bấm, chờ
      CAST_BLIND_WAIT = 0,15 s, click) và thanh dưới cảnh báo "Chưa đăng ký con trỏ ngắm phép".
   • 4 GIAO DIỆN: modal "Cài đặt skill" có ô chọn TRANG cạnh ô chọn phím cho mọi skill (đánh/buff/tiện ích),
      dòng nhắc cam "Gán phép tấn công vào trang F2 (vd. F2 → F5) trong game"; khung HP có ô trang cho hồi máu /
      bình chính / cuộn về làng / 3 bình phụ; dòng tóm tắt ở tab Kỹ năng hiện "F2+F5 에너지 볼트"; khung Quét
      thêm "Số luồng ONNX khi tìm quái".
   • Kiểm tra: smoke_test thêm chuỗi phím đúng thứ tự ("F2","F5",click rồi "F1","F5" cho hồi máu ngay sau đó;
      lần sau ở lại F2 thì không bấm trang nữa), con trỏ elip (có elip → click; không có → không click + 3 lần
      là ngưng 10 s; chưa đăng ký → chờ mù rồi click), và detector (2/1 luồng, sàn 2/s khi tìm, 1/s khi đánh).
      test_ui gán 에너지 볼트 vào F2+F5 trong modal, kiểm tra F1+F5 hồi máu vẫn còn và file config lưu đúng.
      test_hunt_records chạy đúng logic trang thật (ctx replay dùng mixin HotbarPages).
      CÒN: chạy thật trên máy game — trước hết ĐĂNG KÝ CON TRỎ NGẮM PHÉP, rồi xem phép có bắn không.

- [x] 0.35 v17 SỬA THEO BẢN CHẠY THẬT CỦA v16 (records_game/20261125_145650_hunt: 35 giết/15 phút, v15 được 62).
      Số liệu: 144/144 spell_cast ok=false reason=no_target_cursor, NHƯNG chat game có 45 dòng
      "마법 사용: 실패(올바른 대상이 아니거나 취소함)" → elip ĐÃ hiện, phép ĐÃ lên tay, bot không click nên phép bị huỷ.
      Người dùng đo trên máy game: elip hiện sau KHOẢNG HƠN 1 GIÂY, còn v16 chỉ chờ 0,3 s.
   • 1 CHỜ ĐÚNG THỜI GIAN THẬT, RỒI LUÔN CLICK. Sau khi bấm ô phép: đọc con trỏ mỗi AIM_POLL = 0,1 s, tối đa
      `AccountSettings.aim_wait_sec` (mặc định 1,8 s, sửa được ở modal "Cài đặt skill": "Chờ con trỏ ngắm (giây)").
      Thấy elip → click vào VỊ TRÍ MỚI NHẤT của quái đang khoá (lấy từ lần nhận diện mới nhất qua
      `targeting.track_current`, không dùng vị trí lúc bấm phím vì quái đã đi tiếp trong hơn một giây đó).
      Hết thời gian mà không thấy elip → VẪN click một lần vào quái (vô hại: không có phép thì chỉ là đánh tay)
      và ghi log. Trong lúc chờ KHÔNG click, KHÔNG bấm phím khác, KHÔNG đổi mục tiêu, KHÔNG đi bộ — mọi thao
      tác khác đều huỷ phép; chỉ `poll_escape` chạy để ESC vẫn dừng được bot.
      Quái chết/mất trong lúc chờ → click con gần nhất còn lại (phép vẫn trên tay); không còn con nào → CLICK
      PHẢI để huỷ phép (KHÔNG dùng ESC: ESC chính là phím dừng bot của chính mình), ghi
      spell_cast {ok:false, reason:"no_target_left"}.
      BỎ HẲN luật "3 lần không thấy elip → ngưng phép 10 s" (nó tự tắt phép cả trận).
      Log/events mỗi lần: aim_delay_s (từ lúc bấm phím đến lúc thấy elip) + cursor_after_key [{at, hash, md5,
      kind}] mỗi hình con trỏ khác nhau đọc được; analyze_records in aim_delay_s trung bình / nhỏ nhất / lớn
      nhất để chỉnh lại mặc định 1,8 s.
      Tab Con trỏ cảnh báo khi hai loại có hình GẦN GIỐNG nhau (hamming aHash ≤ 4, `CursorProfile.near_duplicates`):
      máy game có attack fc92fe3800000000 và cast fcfefe3800000000 — lệch đúng 4 bit, nghĩa là một trong hai
      hình bị chụp sai, người dùng nên xoá hình nhầm.
   • 2 GIẢM ĐỔI TRANG. Hết trận KHÔNG quay về trang nhà nữa (101 trong 202 lần đổi trang của 145650 là lần quay
      về mà trận ngay sau đó lại đổi lại). Ở lại trang mà trận vừa rồi để lại; chỉ về `home_page` khi KHÔNG CÒN
      quái quanh đó: `session.HOME_IDLE_SEC` = 3 s không có mục tiêu. Hồi máu / bình / buff / giải độc vẫn tự
      đổi sang trang của nó khi cần rồi phép tiếp theo tự đổi lại F2. analyze_records in số lần đổi trang/phút.
      Mô phỏng lại trên bản ghi (`python tests/sim_v17.py records_game/20261125_145650_hunt`):
      202 lần (13,4/phút) → ~114 lần (7,6/phút) = 100 lần F1→F2 cho trận có phép + 14 lần F2→F1 khi hết quái.
   • 3 Tab Kỹ năng: xoá dòng "Chỉ dùng ô ở trang F1" (từ 0.34 một ô là (trang, phím) nên câu đó đã sai).
   • 4 analyze_records thêm: số phép thật sự bắn (MP tụt sau khi bấm), số lần chat báo huỷ phép + có đổi thứ tự
      bấm hay không, trung bình aim_delay_s, các hình con trỏ đọc được, số lần đổi trang/phút. Thời gian giết
      có phép vs đánh tay đã có từ 1.6.
   • 5 Chat "마법 사용: 실패" nay ghi event spell_fail_chat {last_key, strikes, order, switched_to} và sau
      `targeting.SPELL_FAIL_STRIKES` = 3 lần thì tự đổi cast_order key_click → hover_key_click MỘT LẦN rồi ghi log
      (vẫn giữ ngưng phép 5 s của 0.29 cho mỗi dòng báo lỗi).
   • Kiểm tra: smoke_test (3 thứ tự bấm, trang hotbar, chờ elip đúng/hết hạn, click vào hộp mới nhất, chuyển
      sang con gần nhất khi quái chết, click phải huỷ phép khi hết quái, aim_delay_s/cursor_after_key vào
      events, đổi thứ tự sau 3 lần chat báo lỗi, cảnh báo con trỏ gần giống nhau, aim_wait_sec lưu/đọc lại).
      `python tests/sim_v17.py <bản ghi>` mô phỏng số lần đổi trang + giá phải trả cho việc chờ elip.
      RỦI RO ĐÃ BIẾT: chờ 1,8 s mỗi lần bấm phép, nếu elip không bao giờ hiện thì mất tới 259 s trong 904 s
      (29%) của bản ghi 145650. Chạy thật xong phải xem aim_delay_s trung bình rồi hạ aim_wait_sec cho khớp.
- [x] 0.36 v18 = v17 + MODEL orc_v2 + CON TRỎ ELIP THEO KHOẢNG CÁCH (25/11).
   • 1 orc_v2 (docs/TRAINING.md 6.8): thêm 092741 (132 ảnh đêm 1280x960, người chơi/cung thủ/slime/nhân vật = nền),
      434 ảnh, 17,3 phút GPU. Test mới: 30 ảnh duyệt cuối của 092741 (split "test"). Ở conf 0.3 so với orc_v1 @0.2:
      ngày 83%/P89% (v1 83/84), đêm 133425 76%/P84% (= v1), đêm 1280x960 96%/P96% (v1 95/90); hai tập chỉ có
      điểm con trỏ (183803, 223510 1334x1008) v2 54/58 và 56/58, v1 58/58 (điểm do bot rê theo box v1 → nghiêng
      về v1; 1 ca sót thật: 오크 전사 trong cỏ cao). Người dùng chọn đóng gói v2. ms/khung như nhau.
      Mặc định `blessed_orc` = orc_v2 (640/416/320), conf 0.3. orc_v1 = HuntMap `blessed_orc_v1` (variant_of,
      conf 0.2, chỉ 640), chọn ở tab Săn → Quét → Nâng cao → "Model" (không hiện như một bãi riêng; chọn lại
      bãi/khu vẫn giữ model đã chọn). `pyinstaller_onnx_datas` chỉ đóng gói file của từng map (+416/320 của map
      gốc) — file thừa trong model/ không lọt vào bản build.
   • 2 ELIP NGẮM PHÉP nhiều hình theo nền: v17 chạy thật 42/42 "no aiming ellipse within 1.8s". Bản ghi quan
      sát "타락한 축복의 땅의 봄" có fc92fe38 / fc96fe38 / fcbafe38, máy game đăng ký fcfefe38.
      `CursorProfile.classify`: aHash cách ≤ `CAST_MAX_DIST` (6) bit với `CAST_DEFAULTS` (4 hình trên) hoặc hình
      cast đã đăng ký → "cast", xét TRƯỚC mọi khớp khác → elip không bao giờ thành attack (fc92fe38 từng bị đăng
      ký vào attack trên máy game). Cast coi như luôn đã đăng ký (mặc định). Kiếm c0c02018/c0e07830 cách ≥ 14 bit,
      xác f0f0f038 cách 8 bit.
      Cảnh báo "hai hình gần giống" chỉ khi ≤ 2 bit: xác f0f0f038 và NPC f0f06020 lệch 4 bit, cả hai đúng.
      Test: tests/test_cursor.py test_cast_ellipse_variants.
- [x] 0.37 타락한 축복의 땅 4 MÙA (orc tím) → orc_v3 (25/11). Chi tiết + bảng: docs/TRAINING.md 6.9.
   • XONG: nhập 8 bản ghi 1334x1008 (7 orc: xuân/hạ/thu/đông ngày + hạ/thu/đông đêm; 1 khu yêu tinh xuân ngày),
      real_map sửa đúng mùa. Catalog `fallen_blessed.json` (4 mùa trong `real_maps` — monsters.Catalog đọc được
      nhiều tên khu; export_dataset/analyze_records --map lọc theo cả 4) + `fallen_blessed_elf.json` (3 loại, cùng bản
      đồ mùa xuân; ô chọn khu theo loại quái = `zone_name`, bản ghi mang `"zone"` = khoá catalog);
      cả hai hiện trong ô chọn khu, `hunt_map: null` → khu chọn vào là chế độ thu dữ liệu.
   • XONG: zero-shot orc_v2 = 1–6 % điểm con trỏ (conf 0.1) ở cả 7 bản → giả thuyết 0.20 "cùng chủng loại khác
      màu" sai; cần train.
   • XONG: prelabel `--glow purple` 273 ảnh (217 train / 56 test, 8 test mỗi bản từ 30 % cuối).
   • XONG: người dùng duyệt 273 ảnh (1355 box). orc_v3 = một model orc chung (11 bản ghi). 4 mùa: 78–94 % /
      P87–100 % (v2: 0 %). 오크의 땅: không bằng v2 ở mọi chỉ số → 2 model: blessed_orc = v2, bãi mới
      `fallen_blessed` = v3 (conf 0.3). Tốc độ như nhau.
   • XONG: ảnh tên dòng chat 5 orc tím (đếm giết ở bãi mới).
   • Khu yêu tinh CÙNG bản đồ mùa xuân (game ghi 타락한 축복의 땅의 봄), khu vực khác: ô chọn khu theo LOẠI QUÁI
      (`zone_name`), bản ghi mang `"zone"` = khoá catalog.
   • Để sau: khu yêu tinh (model), ảnh tên/chat của 5 loại orc tím (analyze_records đọc 0 lượt giết vì chưa có
      ảnh tên dòng chat), xuân ĐÊM.
- [x] 0.42 KILL GIẢM 78 → 43 (26/11, 20261126_225217_hunt v21rc3 đêm minimap BẬT vs 20261126_090350_hunt v20rc1
      ngày minimap TẮT, cùng 오크의 땅, ~15 phút mỗi bản).
      Thời gian đánh gần bằng nhau (652 s vs 687 s) nhưng ít trận hơn (173 vs 230) → mất thời gian ở ĐI LANG THANG.
   • NGUYÊN NHÂN CHÍNH: viền tối của mũi tên nhân vật nằm NGAY NGOÀI vòng ép-đi-được `minimap.ARROW_R` = 7 →
      thành một vòng "vật cản" quanh nhân vật. Mọi đường thẳng từ tâm cắt vòng đó ở bước 7-8 px minimap:
      - 13/14 trận `wall` (98-166 px, kể cả con 152 px) là vòng viền đó, KHÔNG có rào (xem frame: orc đứng
        trên cỏ trống); chỉ con 524 px còn "blocked" thật.
      - Chỉ 14% hướng đi bộ 160 px đọc là thông (27 khung không hướng nào thông) → `_smart` bỏ hướng đang
        giữ (`minimap_keep` chỉ giữ khi hướng còn thông) gần như mỗi nhịp, đổi W↔E mỗi 0,3-1 s, đi qua đi lại
        (pos x 65↔81) → wander 371 → 600, engage 230 → 173.
      - Box trên khung: "blocked" 36 → 4, "detour" 236 → 174 khi sửa.
   • SỬA: `ARROW_R` = 10 (= `ODO_ARROW_R`, đã dùng cho odometry ở 1.2b): 69% hướng đi bộ thông, 0 khung kẹt.
      Thêm luật người dùng yêu cầu: `combat.WALL_MIN_DIST` 250 px - quái gần hơn LUÔN thử đánh (không kết thúc
      `wall`; rào thật vẫn kết thúc bằng unreachable/cap). Test `check_walls_225217` (test_hunt_records).
   • Wander khi màn hình còn quái: khung gần nhất có box ở 174/600 lần wander (29%) vs 142/371 (38%) bản cũ →
      KHÔNG tệ hơn theo tỉ lệ; số lần tăng là do đổi hướng liên tục ở trên (box của recorder ≠ box bot dùng).
   • Đêm: recall orc_v1 @416 conf 0,2 trên nhãn đêm 133425 = 80%, 092741 = 72%; ngày 130457 = 79%,
      111355 = 80%, 193903 = 73% → đêm KHÔNG kém. conf 0,08 chỉ +1-5 điểm, thêm 6-13% box sai → GIỮ 0,2,
      chưa cần dữ liệu đêm. hits/frame 1,89 vs 2,39 là do đứng/đi qua lại ở một chỗ đã dọn, không phải detector.
   • low_mp 1084 / crowd_cast 12: `fight_end.skipped` đếm MỖI NHỊP đánh (0,1-0,3 s) mà ô phép bị chặn, không
      phải số phép bị mất (1084 / 173 trận ≈ 6 nhịp/trận). crowd_cast 12 = số phép ĐƯỢC bắn nhờ luật đông quái
      (≥2 box trong 200 px, dưới min_mp của ô, MP ≥ 25%). MP bản này nằm 22-32% (median 24%) so với 39% bản cũ:
      phép bắn xuống tới MP 25 (43/66 phép dưới 40%) nên phép bị giới hạn bởi tốc độ hồi MP; 66 vs 98 phép
      đi theo số trận ít hơn. Không sửa thêm.
- [x] 0.41 v21rc3: "KHỰNG KHI ĐÔNG QUÁI" (26/11, bản ghi 20261126_101941_hunt, quay bằng v20rc1).
      Đo: 23 idle_gap = 115 s / 515 s, nhưng 109 s nằm TRONG trận (giữ chuột trên quái không chết); sau mỗi
      fight_end trận kế bắt đầu sau 0,1-0,2 s → KHÔNG có chờ giữa trận, không cần ép detect. search.fps 0,03 trong
      detect_stats = số lần detect ở chế độ search chia cho CẢ phút (bot gần như luôn ở chế độ fight), tổng vẫn ~2/s.
      idle_gap chỉ tính click/bắt đầu giữ/phím là "hành động", nên giữ chuột đánh tay 10 s cũng là "idle".
      Unreachable 70-92 px sau 1,8 s: bản ghi có TRƯỚC rule NEAR_UNREACH_SEC 4 s (v21rc1, b866c96 11:31; bản ghi
      10:19). Replay bằng code hiện tại: 0 trận ≤ 100 px bị bỏ trước 4 s.
      Phép: 0 spell, 798 low_mp: ô F2+F5 = 386 có min_mp 65 % (config máy game) mà MP chỉ 30-45 % (tối đa 51 %).
      Sửa: ≥ CROWD_SPELL_N (2) box trong CROWD_SPELL_PX (200) của detect mới nhất → bỏ qua min_mp của ô, vẫn giữ
      CROWD_MP_FLOOR = dự trữ hồi máu 25 % (`combat._crowd`, state mobs_seen/char ghi ở `targeting._detect`;
      fight_end.skipped.crowd_cast đếm số phép nhờ luật này). Test `check_idle_101941` (replay với phép như máy
      game, AIM_DELAY 1 s): idle mô phỏng 179,8 s → 150,9 s, phép 0 → 29. Phần idle còn lại: trận cap đánh tay
      1-1 dưới min_mp (≈68 s) và cửa sổ bị cắt của replay. Gợi ý: hạ min_mp của ô 386 xuống ~30 % trên máy game.
- [ ] 0.40 v21rc1: BÃI ORC TÍM — RÀO, AN TOÀN, BÌNH MANA (26/11, yêu cầu người dùng trên
      records_game/20261126_101941_hunt: fallen_blessed/orc_v3 @416, 8,6 phút, đêm, MINIMAP BẬT ở cả 412 khung;
      8 giết, 55/114 trận unreachable, 11 cap 10 s, 0 phép (MP tụt tới 2 % vì hồi máu), HP 90→46 % trong 2 s
      ở cuối → về làng).
   • ĐO TRƯỚC KHI SỬA (quan trọng): trong 55 trận unreachable, **44 trận kết thúc ở 70–92 px** với con trỏ attack
      và box CÒN trong khung mới nhất; chỉ 11 trận ở 200–533 px. `minimap.route` ở điểm kết thúc: 39 "clear",
      8 "detour", 8 "blocked". Lý do 39 trận "clear": 70 px = 7 px minimap, mà vòng tròn mũi tên nhân vật
      (`ARROW_R` 7) BỊ ÉP thành đi được → **minimap không bao giờ thấy rào ở gần**. Đánh tay giết mất 3,8 s
      (`kill_sec_hand`) nhưng `UNREACH_SEC` = 1,5 s → bot bỏ trận nó đang thắng: 5/6 dòng chat giết đến NGAY SAU
      khi trận vừa bị bỏ (`late_chat_kill` = 5).
   • SỬA 1 (rào): trước cú click đầu tiên, `combat.engage` hỏi `targeting.route(anchor)`; "blocked" → KHÔNG click,
      ghi đen chỗ đó 60 s theo toạ độ minimap (`targeting.block`, đã là toạ độ odometry từ 0.39) và kết thúc
      outcome mới `wall` (0 s). Trận chạm trần 10 s mà CHƯA BAO GIỜ vào tầm đánh (`melee_seen`) cũng bị ghi đen.
   • SỬA 2 (gần): còn con trỏ attack và box sống trong `NEAR_FIGHT_DIST` 100 px → chờ `NEAR_UNREACH_SEC` 4,0 s
      (> 3,8 s giết tay) thay vì 1,5 s. Ngoài 100 px vẫn 1,5 s.
   • KẾT QUẢ REPLAY (`tests/test_hunt_records.check_101941`, 91 → 83 trận mô phỏng): unreachable 33 (36 %) →
      **8 (10 %, đạt mức < 15 %)**, thêm 14 trận `wall` kết thúc ở 0,0 s (trước mỗi trận mất 2,4 s), cap vẫn 7.
      CHƯA KIỂM ĐƯỢC: replay chạy trên khung đã lưu nên KHÔNG thể sinh thêm lượt giết — "chờ 4 s thì giết được"
      chỉ máy game trả lời được.
   • AN TOÀN (`features/survival.py`): HP tụt ≥ 20 % trong 2 s HOẶC ≥ 3 box trong `MELEE_DIST` quanh nhân vật
      (`state["mobs_near"]`, do `targeting._detect` ghi) = nguy cấp, giữ 3 s: hồi máu/bình NGAY (bỏ qua
      `threshold_pct`, nhưng chỉ khi HP < 90 % — bắn hồi máu lúc đầy máu chỉ tốn đúng cái MP đang thiếu), lùi
      120 px ra khỏi tâm đám quái (1 lần/1,5 s, không lùi khi đang có trận giữ chuột), và `combat.engage` rời
      trận (outcome `danger`). Không còn gì hồi máu (phép không đủ MP + không bật bình HP nào) và HP < 80 %
      → cuộn về làng NGAY (trước khi HP < 50 %).
      Đo: ≥ 3 box sát nhân vật xảy ra 0/412 khung ở bản ghi này nhưng 24/736 khung ở 20261126_090350_hunt (buổi
      chạy tốt 5,25 giết/phút) → QUYẾT ĐỊNH (người dùng 26/11): luật "≥ 3 quái sát người" CHỈ chạy ở bãi
      `HuntMap.mp_hungry` (fallen_blessed); ở 오크의 땅 và các bãi khác chỉ còn luật HP tụt ≥ 20 %/2 s, để không
      làm giảm 5,25 giết/phút của v20.
   • BÌNH MANA: `HuntMap.mp_hungry` (bật cho `fallen_blessed`); chọn bãi đó mà chưa bật bình MP nào trong
      "Bình thêm 1–3" → cảnh báo cam ở thanh dưới (`warn_no_mp_potion`, ko/en/vi).
   • Test: smoke (nguy cấp: hồi máu / lùi / về làng sớm) + `tests/test_hunt_records.py` (replay 101941).
   • CHẾT (0.3, yêu cầu 26/11): `survival._die` — HP HUD = 0 (2 lần đọc) → thả hết phím/chuột, log WARNING, lưu
      `DEATH_SNAPSHOTS` 3 ảnh PNG THÔ records/deaths/death_<n>_<giờ>.png, dừng (trạng thái đỏ "Nhân vật chết -
      đã dừng"). Nhịp có HP HUD = 0 KHÔNG bấm gì (trước đây vẫn bấm hồi máu ở 0 %).
   • SỬA (yêu cầu 26/11, sau khi làm): số HP HUD MẤT > `HUD_GONE_DEAD_SEC` 2 s khi HP < `LOW_FOR_DEATH_PCT` 50 %
      KHÔNG còn bị kết luận là chết — màn hình tải/dịch chuyển và hộp thoại che HUD trông y như vậy. Nay:
      `survival._hud_gone` → loại trừ trước (`_loading_screen`): màn hình tối toàn bộ (trung bình sáng <
      `LOADING_DARK` 30; đo 83 khung ĐÊM của 20261126_101941_hunt là 54–62 nên đêm không bị tính) hoặc đọc được
      TÊN BẢN ĐỒ khác zone đang săn (`vision/map_name` + `monsters.fits_map_name`) → khởi động lại đồng hồ 2 s,
      chỉ log, không dừng. Cuộn về làng vẫn thoát trước đó bằng `returned` (trạng thái "Đã về làng"). Hết loại
      trừ → `_stop_hud_lost`: thả hết, WARNING "not counted as a death", 3 ảnh hud_lost_<n>_*.png, trạng thái
      VÀNG "Mất HUD - đã dừng" (`SessionState.HUD_LOST`, `state_hud_lost` ko/en/vi) — KHÔNG đếm vào thống kê
      `death`. Cùng trạng thái đó cho luật 60 s `session._hud_lost` (mất kết nối). CHƯA LÀM: nhận "cửa sổ hồi
      sinh" làm bằng chứng chết thứ hai — không có ảnh bản ghi nào có cửa sổ đó trên máy dev để cắt mẫu.
      Test: smoke (ảnh HUD giả "0/432"; mất số HUD trên màn hình tối = chờ, trên nền bãi = dừng an toàn).
   • BUFF LẠI KHI HẾT (2.1b, yêu cầu 26/11): mỗi buff một câu chat khác nhau ("블레스드 아머: … 사라집니다",
      "쉴드: 쉴드가 사라집니다", nhưng "인챈트 덱스터리티: 몸놀림이 둔해지는 것이 느껴집니다" KHÔNG có 사라집니다)
      → so CẢ DÒNG với một ảnh dòng chat trong `lineage_auto/data/chat/buff_gone/<skill_id>[_ghi chú].png`
      (`name_reader.buff_gone_skill`, ngưỡng 0,72 + bề rộng ±8 %). Tên file = bảng map chat ↔ skill_id.
      `KillWatcher` thu các dòng này → `state["buff_gone"]` → `BuffFeature.expired_from_chat()` xoá đồng hồ ô đó
      (buff lại ở nhịp sau, SAU hồi máu); dòng của skill không gán ô nào → log "no slot is set to it".
      Đã cắt được 399 (인챈트 덱스터리티) từ records_game/20261126_101941_hunt f_00275: trong 63 dòng chat mới của
      bản ghi, chỉ dòng đó khớp — dòng BẬT buff ngay sau (cùng bề rộng 653 px) không khớp.
      CHƯA CÓ ảnh cho 실드 (385) / 블레스드 아머 (397): bản ghi 001245 không còn ảnh trên máy dev → cắt trên máy game:
      `python tests/build_chat_phrases.py <bản ghi> --save 385 --line <n>` (xem sheet_NN.png do lệnh in ra).
   • THỐNG KÊ (4.1, yêu cầu 26/11): `runtime/stats.py` (một Stats trên mỗi BotContext; features gọi `bump`/`kill_name`),
      tab "Thống kê" thứ 7, và records/stats_<ngày>.json mỗi 10 phút + khi dừng (để xem sau một đêm 24/24).
   • BẢN THỬ v21rc1: BUILD TRÊN PC NHÀ bằng Python 3.12 theo main.spec (người dùng 26/11; KHÔNG build trên laptop
      — .venv ở đây là 3.14 — và KHÔNG build trên máy game), KHÔNG tag.
      Cần một buổi 15 phút có ghi ảnh + minimap BẬT để so: giết/phút (mốc v20 5,25), unreachable/phút
      (mốc 1,88 ở 오크의 땅 / 6,4 ở bãi orc tím), số `wall`, `danger`, `retreat`, MP thấp nhất.
- [x] 0.38 CHẠY 24/24 (25/11; người dùng để tool săn liên tục, 15 phút chỉ là cấu hình thu dữ liệu).
   • LỖI: "Tự dừng sau" = 75 nhưng bot dừng sau 15 phút: record.max_frames = 900 với nhịp 1 s, và hết khung ghi
      thì `_limit_reached` DỪNG CẢ LƯỢT SĂN. Nay hết khung chỉ dừng GHI (`session._recording_tick`: lưu bản ghi,
      log "recording cap reached, hunting continues"); chế độ quan sát vẫn dừng khi đầy (không còn việc gì làm).
      UI: "Tối đa (khung): 0 = theo thời gian tự dừng (n); đầy thì chỉ dừng ghi, vẫn săn".
   • `auto_stop_min` = 0 → không giới hạn; mặc định (config mới / thiếu khoá) = 0. Config cũ giữ giá trị đã lưu.
      `frame_cap()` = None khi cả hai là 0 (trước là 1200 khung).
   • Ghi lâu: `recorder.ROTATE_SEC` = 15 phút một thư mục (giới hạn khung tính trên tổng các thư mục), records/
      giữ ≤ `record.max_gb` (mặc định 5 GB, ô "records/ tối đa (GB)"): `recorder.prune_records` xoá bản ghi cũ
      nhất (<stamp>_* và .zip của nó, CHỈ trong records/, không bao giờ bản đang ghi, không đụng deaths/…).
   • session_log.txt xoay vòng > 20 MB, giữ 3 file (session_log.1.txt, .2.txt). RSS mỗi 10 phút vào log +
      events.jsonl ("memory"), cảnh báo khi tăng > 5 MB 6 lần liên tiếp (1 giờ).
   • Lỗi trong một nhịp săn: log + traceback, thả hết phím/chuột, chờ 1 s, chạy tiếp vòng lặp; 20 lỗi trong 5 phút
      = hỏng thật → dừng (ERROR). HUD "HP:x/y" đọc được rồi mất 60 s (mất kết nối / đăng xuất) → dừng an toàn +
      log, không click gì thêm. (Chỉ khi đọc số HUD đang bật; cửa sổ game đóng thì đã dừng từ trước.)
   • Test: tests/test_24h.py (giới hạn khung + xoay vòng, xoá bản cũ, xoay log, HUD mất, RSS) + smoke (lỗi 1 nhịp).
   • Còn cho 24/24: 1.3b "Quay lại bãi săn" sau khi về làng (chưa làm, xem 1.3b).
- [x] 0.39 v20: 오크의 땅 QUAY VỀ orc_v1 (25/11). v19 chạy thật (records_game/20261125_225906_hunt, orc_v2 conf 0.3,
      input 416): 2,28 box/khung ngày, 1,29 đêm, 2,8 giết/phút, 110 trận "gone"; v17 (20261125_202634_hunt, orc_v1
      0.2, 416, ngày): 5,68 box/khung, ~5 giết/phút. Máy game chưa từng chạy v18. Ảnh khung của 2 bản ghi này KHÔNG
      có trên máy dev (chỉ jsonl) → box/khung trên ảnh thật chưa đo lại được; chấm trên 3 tập đã duyệt (split test):
      | tập | v1@0.2 640 / 416 / 320 | v2@0.3 640 / 416 / 320 | v2@0.2 416 |
      | ngày 193903 | 83 / 72 / 50 % | 83 / 68 / 36 % | 72 % |
      | đêm 133425 | 76 / 67 / 37 % | 76 / 58 / 42 % | 62 % |
      | đêm 092741 | 95 / 88 / 61 % | 96 / 85 / 64 % | 88 % |
      → orc_v2 chỉ hơn ở 640; ở 416 kém (nhất là đêm) và conf 0.3 bớt thêm. 416 mất ~10 điểm recall với CẢ HAI model
      so với 640 (fp ít hơn). Khoảng cách 5,68 → 2,28 lớn hơn mức model giải thích (~1,1–1,15×): phần còn lại là cảnh
      (202634 chỉ 193 khung ban ngày, 0 khung trống) — kiểm lại bằng hộp/khung của v20 trên máy game.
   • `blessed_orc` = orc_v1 conf 0.2, `model/yolox_tiny_blessed_orc{,_416,_320}.onnx` (416/320 xuất lại từ
      train/YOLOX_outputs/orc_v1/best_ckpt.pth; 640 giống hệt file đã giao). orc_v2 = biến thể `blessed_orc_v2`
      (`yolox_tiny_blessed_orc_v2{,_416,_320}.onnx`, chỉ 640 được đóng gói → chọn nó trên máy game là chạy 640).
      Khoá cũ "blessed_orc_v1" trong config v18/v19 → `hunt_maps.get` đổi thành "blessed_orc".
   • QUY TẮC: model mới chỉ thành mặc định sau khi chấm ở ĐÚNG cỡ đầu vào máy game:
      `tests/eval_detection.py --config <lineage_auto_config.json của máy game>` (lấy scan.input_size/detect_roi).
   • Tab Kỹ năng: cảnh báo đỏ khi phép tấn công bật có min_mp ≥ 80 % (`skill_summary.high_min_mp_names`).
   • HỒI QUY v17→v19 (yêu cầu 26/11): `git diff v17 v19` KHÔNG đụng detector/targeting/combat/exploration
      (chỉ session: 24/7 + đo RAM + xoay bản ghi; recorder; logging; cursor_profile: elip; config). Đo trên
      session_log máy game (21 bản ghi v17 15:58–22:10): v17 = 1,56–4,98 giết/phút, các bản có wander ≥ 20/phút
      trung bình ~2,75 → v19 225906 (2,80, wander 32,8/phút) nằm GIỮA phân bố v17. 202634 (5,68 box, ~5 giết/phút)
      là 4 phút đỉnh ở chỗ đông (wander 0,5/phút) → không dùng làm mốc. Hộp/khung trận v17 trung bình 3,37 (322 phút).
      detect_ms 250 của 233615 = biến thể `blessed_orc_v1` của v19 chỉ có file 640 → chạy 640 dù input 416
      (`yolox_mobs.ensure_session` rơi về 640). v20: orc_v1 là mặc định có 416 → ~90 ms như v17.
   • PHÉP (233615): 15/18 trận "lost" có phép kết thúc với con trỏ ground: sau phép bot click + giữ ở tâm box
      + 25 px (`NAMEPLATE_BODY_DROP`, vốn cho bảng tên) = mặt đất → 1 s không thấy kiếm → lost. Sửa: click/giữ
      đúng tâm box; `CAST_GRACE` 1 s không tính "lost" sau phép. Elip 94/94 ở 0,0 s cùng hash fc92 → nay đọc
      con trỏ TRƯỚC phím (`cursor_before_key`), elip đã có sẵn trước phím không tính. MP sau phép đọc lại sau
      `MP_SETTLE` 0,8 s (event `spell_mp`; mp_after cũ luôn = mp_before). Phép dừng khi MP < `HEAL_MP_RESERVE`
      25 % nếu hồi máu bằng phép (233615 bắn tới 20 %, MP rơi còn 2 %).
   • TƯỜNG: `UNREACH_SEC` 2,5 → 1,5 s (233615: 20 trận unreachable đứng 2,8–7,4 s), `DETOUR_AFTER` 1,2 → 0,8,
      chỗ không tới được nhớ 60 s theo toạ độ minimap (`BLOCK_TTL_WORLD` 40 → 60). Ứng viên cùng phía (đường
      thẳng trên minimap không chặn) đã xếp trước từ 0.27.
   • ĐỔI MỤC TIÊU: chỉ khi khoá hiện tại KHÔNG sát (> `MELEE_DIST`) và con kia sát nhân vật (đang đánh mình).
   • DI CHUYỂN: hướng minimap giữ 4–8 s ngẫu nhiên khi đường thẳng còn thông (`minimap_keep`); hướng kết thúc ở
      chỗ vừa đi qua 8–90 s trước bị trừ `W_BACK`; không minimap: giữ 4–8 s; điểm nhấp lệch ±10 px (không vượt
      rào), nghỉ 0,05–0,15 s. "hold" của v19 KHÔNG phải đứng chờ: đó là bước đi tiếp cùng hướng khi minimap không
      đọc được; đứng im thật là "rescan" (200 lần ở 233615).
   • TỰ VỆ + KHỰNG: HP HUD giảm trong 2 s + box ≤ 70 px mà không xác nhận được mục tiêu → rê chuột lên box gần nhất, CHỈ đánh khi thấy con trỏ attack (bãi đông người chơi)
      (count `defend`). `idle_gap` = > 1,5 s không click/giữ/bấm phím khi có quái < 150 px hoặc HP đang tụt.
      `analyze_records` in: đổi hướng/phút, quay lại vùng < 60 s, px minimap/phút, idle_gap (cần `pos` trong
      event wander, có từ v20). Mốc v19 233615: 10,7 đổi hướng/phút.
   • CHƯA KIỂM ĐƯỢC TRÊN MÁY DEV: 202634 / 225906 / 233615 không có ảnh khung trên máy dev → không mô phỏng lại
      được box/khung, giết/phút. Điều kiện "≥ v17" chỉ đo được trên máy game.
   • 7) ORC TÍM (records_game/20261126_001245_hunt, 타락한 축복의 땅의 봄, orc_v3, 5,5 phút, CÓ ẢNH): 3,2 box/khung,
      detect 91 ms. Đếm giết 1 vì zone (record.real_map) vẫn là 오크의 땅 → chat đọc bằng catalog blessed_orc.
      Sửa: `session._zone_catalog` khi bắt đầu săn/quan sát: tên bản đồ trên màn hình (`vision/map_name`) thắng
      zone đã lưu; không đọc được → zone của bãi đang chọn (`monsters.for_hunt_map`); sửa thì log WARNING và ghi
      lại record.real_map (cả cảnh báo khi model không phải của bãi đó). Chọn bãi ở khung Bản đồ cũng kéo zone
      theo (`map_panel.store`). Đọc lại offline với catalog đúng: 6 dòng giết trên các khung đã lưu (bot: 0).
      Tên bản đồ đọc được 210/263 khung (phần còn lại: chữ nằm trên hoa anh đào trắng; không lần nào đọc sai).
      Tường trên ảnh thật (`test_hunt_records.check_001245`): unreachable TB 3,9 → 3,1 s, tối đa 6,8 → 5,2 s,
      thời gian mất 47 → 40 s. MP 84 → 2 %: KHÔNG do phép tấn công (0 lần bắn, `low_mp` chặn 644 nhịp vì
      min_mp 90) mà do hồi máu: 10 trận đánh tay sát người hết trần 10 s với orc tím → HP tụt → hồi bằng phép.
   • BẢN THỬ dist/LineageAuto_20261126_v20rc1.zip (KHÔNG tag). Tự vệ: một lần rê chuột, chỉ đánh khi thấy con trỏ
      attack (người dùng 26/11: bãi đông người chơi). Chạy 15 phút có ghi ảnh trên máy game; đạt "≥ v17" (box/khung,
      giết/phút) + đổi hướng / quay lại giảm rõ → build v20 chính thức + tag. Ảnh 225906/233615 còn trên máy game.
   • 8) ĐO BẢN THỬ 20rc1 TRÊN MÁY GAME (records_game/20261126_090350_hunt, 오크의 땅, orc_v1 416, 14,9 phút,
      CÓ ẢNH 736 khung) → ĐẠT, đã build v20 + tag v20:
      | điều kiện | v15 112040 | v17/16 145650 | v19 233615/225906 | v20rc1 090350 |
      | giết/phút | 4,17 (62) | 2,32 (35) | 2,80 | **5,25 (78 = 53 chat + 25 xác)** |
      | box/khung (chung / trận) | 5,28 | 2,54 / 2,81 | 2,28 | 2,42 / 2,65 |
      | đổi hướng/phút | 11,5 | 13,1 | 10,7 | **2,6** |
      | quay lại vùng < 60 s | - | - | - | KHÔNG ĐO ĐƯỢC (xem dưới) |
      | idle_gap | - | - | - | 23 lần, 131 s (14,7 %) |
      | unreachable (đánh qua rào) | 6 (0,40/ph, 2,4 s TB) | 20 (1,33/ph) | 20 | 28 (1,88/ph, 2,4 s TB, tối đa ~6 s) |
      | lost sau phép | 0 | 0 (0 phép bắn) | 15/18 trận lost | 3/11 trận lost |
      | MP thấp nhất | 265/317 (84 %) | 41 % | 2 % | 29 % |
      | defend / defend_no_cursor | - | - | - | 0 / 0 (HP không bao giờ xuống dưới 71 %) |
      · 5,25 giết/phút CAO NHẤT từ trước tới nay, trên cả dải v17 (1,56–4,98) → điều kiện "≥ v17" về giết/phút đạt.
      · box/khung trận 2,65 THẤP hơn mốc 3,37 của v17 (322 phút trên máy game, gồm cả chỗ đông) nhưng chỉ kém 5 %
        so với bản ghi cùng cấu hình gần nhất (145650: 2,54 chung). Mật độ quái của cảnh, không phải bot: người dùng
        26/11 quyết định phát hành.
      · PHÉP đã bắn thật: 98/102 lần có elip (4 lần "no_target_left"), 74/97 lần MP tụt sau phép (bản 19: mp_after
        luôn = mp_before), chat "마법 사용: 실패" 22 (bản 17: 45). `low_mp` chặn 643 nhịp vì min_mp 90 % → nên hạ min_mp.
      · MINIMAP TẮT TRONG GAME suốt buổi chạy (`vision/minimap.read` trên ảnh thật = None ở mọi khung đã thử,
        frames.jsonl "minimap": false, wander why: 318 "hold" = bước tiếp cùng hướng). Vì vậy KHÔNG có `pos` →
        "quay lại vùng < 60 s" và "px minimap/phút" chưa đo được, và 2,6 đổi hướng/phút là của đường dự phòng
        (giữ hướng 4–8 s) chứ không phải của BFS minimap. CẦN: một buổi 15 phút nữa với minimap BẬT trong game.
      · Vẫn mở: 66 % thời gian "đứng im" (28 đoạn > 5 s, dài nhất 42,9 s) — 12 trận chạm trần 10 s (`melee_max_sec`)
        và 108 trận "gone" (2,6 s TB) cho thấy box mất khi đang đánh; 577 lần rê chuột đều ra con trỏ "unknown"
        (cấu hình máy game đăng ký trùng hash attack/corpse/ground → analyze cảnh báo, cần đăng ký lại con trỏ).
   • BẢN PHÁT HÀNH v20 (26/11): dist/LineageAuto_20261126_v20.zip = ĐÚNG binary của 20rc1 (sha256 main.exe trùng,
      1212 file, chỉ thay HUONG_DAN.txt sang "bản 20 chính thức" + số đo) theo tiền lệ v15_release. KHÔNG build lại
      từ code trên laptop: .venv của laptop là Python 3.14, cả dòng sản phẩm là 3.12 (xem CLAUDE.md), bản 3.14 chưa
      từng chạy trên máy game. Muốn build lại từ code phải có Python 3.12 (`py -3.12 -m venv .venv`).

## Giai đoạn 0 — Sửa lỗi & tốc độ (làm trước tiên)

### 0.1 Nhận diện chậm và bot "đứng im" không săn  [ƯU TIÊN CAO NHẤT]
Nguyên nhân đã xác định trong code:
- `runtime/session.py` (~dòng 156): nếu YOLOX thấy điểm nhưng không xác nhận được con trỏ kiếm
  (`last_scan_points > 0`) thì bot KHÔNG đi tiếp (`pass`) và quét lại mãi → đứng một chỗ khi có
  nhận diện nhầm (NPC, người chơi, đá...).
- `features/targeting.py`: mỗi điểm rê chuột chờ HOVER_SETTLE 0.08s + tối đa 3 lần đọc × 0.08s
  ≈ 0.32s; tối đa 24 điểm (MAX_PROBE_POINTS) → một lần quét thất bại mất ~7–8 giây.
- YOLOX chạy CPU ~150ms/khung, gọi lại mỗi nhịp combat (`track_current`, BURST_INTERVAL 0.1s).
Việc cần làm:
- Đếm số lần quét liên tiếp không xác nhận được → sau N lần (cấu hình, mặc định 2) thì wander.
- Nhớ các điểm vừa rê mà không ra kiếm (blacklist tạm theo vị trí, hết hạn vài giây) để không rê lại.
- Giảm số điểm rê mỗi lượt (mặc định ~6, gần nhân vật trước), đọc con trỏ nhanh hơn (đọc ngay,
  thử lại ngắn), đưa các hằng số này vào cấu hình.
- Lọc kết quả YOLOX: ngưỡng tin cậy theo từng bãi săn, bỏ box lớp "figure"/"die".
- Đo thời gian: log thời gian từng bước (detect, probe) vào session_log để so sánh trước/sau.
- Tùy chọn: thử onnxruntime DirectML (GPU) có công tắc bật/tắt, mặc định CPU như cũ.
- KẾT QUẢ THỬ MODEL TRÊN ẢNH VIDEO (5 khung, CPU ~130ms/khung): model `dragon_valley` gần như KHÔNG thấy
  hổ (0 quái ở 4/5 khung, dù khung 0:30 có 4 con hổ), `abandoned` thấy 3–4, hai model còn lại 0–2.
  → Model không khớp bãi đang săn là nguyên nhân lớn thứ hai của việc "chậm/không săn": bot không
  thấy quái nên đi lang thang hoặc rê nhầm. Cần: đúng model cho đúng bãi (hỏi Q6), công cụ chụp ảnh
  để huấn luyện lại (4.2), và chế độ dự phòng không cần model (rê chuột tìm con trỏ kiếm theo vùng
  chuyển động — code cũ vision/play_motion.py vẫn còn).
Tiêu chí xong: test giả lập cho thấy sau N lần quét nhầm bot gọi wander; thời gian một vòng quét
không thấy quái < 1.5s.

### 0.5 Nhận diện đủ mọi quái trong phạm vi săn  [YÊU CẦU NGƯỜI DÙNG 23/11 — ƯU TIÊN CAO]
Mục tiêu: mọi con quái nằm trong phạm vi săn (bán kính 1.2) đều được phát hiện, kể cả ban đêm, quái nhỏ,
quái đứng sau nhãn đồ rơi, quái đứng sát nhân vật.
Hiện trạng trong code (vision/yolox_mobs.py):
- Ảnh 1280×960 bị thu nhỏ còn 640 (INPUT_SIZE) trước khi đưa vào model → quái nhỏ/xa dễ bị mất.
- Một ngưỡng tin cậy cố định CONF_THRESH 0.15; một model riêng mỗi bãi; không có bãi 풍룡의 상흔.
- Mỗi khung hình nhận diện độc lập, không ghép kết quả nhiều khung → quái bị che 1 khung là "biến mất".
- Thử trên ảnh video: khung 0:30 có 4 con hổ, model dragon_valley thấy 0, abandoned thấy 3–4.
Việc cần làm:
1. BỘ ĐO (làm trước tiên): gán nhãn tay vị trí quái trên các ảnh docs/game_reference/ (+ tách thêm khung từ
   video, gồm khung ban đêm) → file tests/data/monster_labels.json. Script tests/eval_detection.py in ra
   recall (tỉ lệ quái thấy được), số nhận nhầm, thời gian/khung cho từng model và từng cấu hình.
   Mọi thay đổi nhận diện phải chạy bộ đo này và báo số trước/sau.
2. Độ phân giải: thử chia ảnh thành ô (tiling, vd 2×2 có chồng lấn) hoặc input 960/1280, so recall và tốc độ.
3. Tiền xử lý ban đêm: tự tăng sáng/CLAHE khi khung tối (đã có hàm _clahe_bgr trong play_motion.py).
4. Theo dõi qua nhiều khung (tracking): ghép kết quả 2–3 khung gần nhất, giữ quái đã thấy dù 1 khung bị che.
5. Ngưỡng tin cậy theo bãi + "xác nhận bằng con trỏ": ngưỡng thấp để không bỏ sót, con trỏ kiếm/cung loại nhận nhầm.
6. Dự phòng khi model không thấy gì nhưng có chuyển động: dò vùng chuyển động (motion_centroids) + rê chuột xác nhận.
7. Chỉ giữ quái trong phạm vi săn (1.2) và ưu tiên gần nhân vật / đang đánh mình (A8).
8. Model chung mọi bãi (4.2) là đích cuối; công cụ thu ảnh khi săn sẽ tự lưu khung có quái để huấn luyện.
Tiêu chí xong: recall ≥ 90% trên bộ ảnh đo (ngày và đêm), nhận nhầm thấp, ≤ 200ms/khung trên CPU máy game.

Tiến độ 0.5 (23/11/2026) — `python tests/eval_detection.py [-v] [--conf X]`, 10 ảnh / 21 quái (17 ngày, 4 đêm),
nhãn gán bằng mắt (±20px) trong tests/data/monster_labels.json:
| thử nghiệm                         | recall      | đêm  | nhận nhầm | ms/khung (máy dev) |
| dragon_valley conf 0.15 (cũ)       | 8/21 38%    | 3/4  | 2         | 39 |
| fallen_spirit conf 0.15            | 8/21 38%    | 2/4  | 3         | 39 |
| dragon_valley conf 0.04            | 15/21 71%   | 3/4  | 4         | 37 |
| dragon_valley conf 0.02 (ĐÃ ÁP DỤNG)| 16/21 76%  | 3/4  | 7         | 38 |
| dragon_valley conf 0.01            | 16/21 76%   | 3/4  | 12        | 37 |
| tiling 2×2 (bước 2)                | 1–7/21      |      | 5–8       | ~148 | → BỎ: model học ở tỉ lệ toàn khung
| CLAHE khi tối (bước 3)             | 7–8/21      | ≤3/4 | 1–4       | ~40–66 | → BỎ: không tăng
| ghép 2 model fs+dv conf 0.08       | 13/21 62%   | 2/4  | 14        | ~250 | → kém hơn dv 0.02 một mình
Đã áp dụng: ngưỡng theo bãi (HuntMap.conf; dragon_valley = 0.02, bãi khác giữ 0.15 vì chưa có ảnh đo) +
ô "탐지 기준" trên UI (AccountSettings.scan.detect_conf, 0 = theo bãi). Nhận nhầm tăng được 0.1 xử lý
(con trỏ loại, nhớ điểm nhầm, sau 2 lượt thì wander).
Còn lại: tracking nhiều khung (4), dự phòng chuyển động (6), lọc theo phạm vi (7, cần 1.2), model chung (8 / 4.2).
Giới hạn bộ đo: chỉ 10 ảnh 1 bãi — cần thêm khung từ video và ảnh bãi khác.
Quái nằm ở cột buff phải (x > 1100) bị che bởi _blank_play_hud → không bao giờ thấy (1/21 nhãn).
LƯU Ý ĐỌC SỐ: 10 ảnh đo đều ở bãi 풍룡의 상흔 (vùng 아덴, hổ 밀림 호랑이 + thằn lằn xanh) — bãi này KHÔNG có model riêng
(dragon_valley = 풍룡의 산맥, bãi khác). Bảng trên chỉ trả lời "model nào hợp nhất với 풍룡의 상흔"; số thấp của
abandoned/fallen_spirit/toi là do thử ở bãi lạ. Độ chính xác của từng model trên ĐÚNG bãi của nó: CHƯA BIẾT
(chưa có ảnh 버림받은자들의 땅 / 타락한자의 땅 정령방 / 오만의탑 / 풍룡의 산맥) → CẦN DỮ LIỆU GAME: chế độ "chỉ quan sát"
(0.6) ở từng bãi, gửi về, gán nhãn, đo. File nhãn chưa ghi tên bãi từng ảnh → nên thêm trường "map".
Kiểm tra trên ảnh (23/11): cả 10 ảnh đo góc trái dưới đều ghi "아덴" (tên vùng, game KHÔNG hiện tên bãi cụ thể); quái
có bảng tên "밀림 호랑이"; nhân vật Lv47 (khác nhân vật Lv30 trong video 23/11). Tên "풍룡의 상흔" là SUY RA từ tra web,
không thấy trên màn hình. Chưa rõ 풍룡의 산맥 (tên trong hunt_maps) có phải cùng nơi không → nếu cùng nơi thì 76% chính
là số của dragon_valley trên bãi của nó. HỎI NGƯỜI DÙNG: model dragon_valley được huấn luyện ở bãi nào / có hổ không.

Video 23/11 (LC_2026_11_23_075954_Screen.mp4 ở gốc repo, 17:42, 1280×960 30fps, toàn ban ngày):
- Bãi 오염된 축복의 땅 (chưa có trong hunt_maps). 0:00–6:00 bãi cát ven nước, đông 오염된 인간 검사/투사/궁수;
  6:30–16:00 rừng rậm, quái lẫn trong cây; 16:30–17:42 đầm lầy tối, nhiều 오염된 아라크네 phát sáng xanh.
- Thử nhanh 3 khung (chưa gán nhãn): cả 4 model đều kém — 1:30 (~7 quái) dragon_valley thấy 2, toi nhận nhầm nhiều
  trên cát trống; 10:00 dragon_valley khoanh nhầm vào nhân vật; 17:00 (~10 nhện) dragon_valley thấy 0.
- HUD "HP:x/y MP:x/y" đọc đúng 1062/1062 giây (hud_numbers). HP thấp nhất 123/190 → KHÔNG chết, không có ảnh cửa sổ hồi sinh (0.3).
- Bị độc (thanh HP xanh) 4 lần: 16:30, 16:33, 16:50, 17:27 → dùng thử CurePoisonFeature.
- Chat "아데나 [n] 획득: <tên quái>" mỗi lần giết → tín hiệu quái chết cho 0.4 và đếm kill cho 4.1.
  "회복의 기운이 느껴집니다" khi hồi máu.
Việc tiếp: tách ~30–40 khung (đủ 3 địa hình) → gán nhãn → thêm vào bộ đo; dùng video làm dữ liệu huấn luyện 4.2.

Tiến độ 0.1 (xong 23/11/2026): AccountSettings.scan + khung UI "타겟 탐색"; sau 2 lượt quét không xác nhận → wander;
điểm rê không ra kiếm bị bỏ qua 4s; 6 điểm/lượt; đọc con trỏ 40ms + 3×40ms, thoát sớm khi thấy kiếm;
log "detect Xms probe Yms". Test (smoke_test): 1 lượt quét thất bại ≈ 0.87s (cũ ≈ 7–8s).
Không làm: DirectML (tùy chọn; code cũ ghi GPU làm box không ổn định). Lọc lớp figure/die: code đã chỉ giữ lớp monster.

### 0.6 Thu thập số liệu trên máy game  [XONG 23/11/2026]
Lý do: máy game không phải máy dev, chỉ xem qua TeamViewer → không đo được recall/thời gian bằng mắt.
Khung UI "데이터 기록 (테스트용)" (ui/panels/record_panel.py, runtime/recorder.py, AccountSettings.record):
- Chế độ 1 "관찰만 기록 시작": chỉ chụp + YOLOX, KHÔNG chuột/phím, không cần đăng ký con trỏ. Người chơi tự chơi.
  ESC / "전체 중지" KHÔNG dừng chế độ này (người chơi dùng ESC trong game) — dừng bằng chính nút đó hoặc nút Stop.
- Chế độ 2 "사냥 중 기록" (ô tích): khi bot săn, ghi thêm kết quả mỗi lần rê chuột (attack/ground/npc/corpse/unknown)
  = nhãn tự động, và đếm engage / rescan / wander, thời gian detect/probe.
- Ghi vào records/<thời gian>_<observe|hunt>/ cạnh main.exe: f_00001.jpg (khung gốc 1280×960), frames.jsonl,
  hovers.jsonl, meta.json, summary.json. Mặc định 1 khung / 3s, tối đa 600 khung (~600 × 0.2–0.4MB).
- Nút "최근 기록 압축": nén bản ghi mới nhất thành .zip và mở thư mục → gửi bằng TeamViewer File Transfer.
Phía máy dev: `python tests/analyze_records.py <thư mục hoặc .zip>` → in số liệu + tạo labels.json (quái đã xác nhận
bằng con trỏ; khung "todo" cần gán thêm quái bị bỏ sót) → `python tests/eval_detection.py --labels <dir>/labels.json --images <dir>`.
Quy trình đề xuất trên máy game: (1) chọn cửa sổ + bãi săn đúng (풍룡의 상흔 → Dragon Valley), (2) chế độ 1 khoảng
20–30 phút, cả ngày và đêm, (3) chế độ 2 khoảng 20 phút, (4) nén, gửi 2 file zip về.

### 0.2 Chọn nhầm cửa sổ
`WindowPicker.guess_game_titles` (winapi/window.py) chọn "lineage_auto_src - File Explorer".
Chọn cửa sổ theo TÊN PROCESS = LC.exe (pid → tên exe qua win32process + psutil/QueryFullProcessImageName),
không dựa vào chữ "lineage" trong tiêu đề. Nhiều cửa sổ LC.exe (2 nhân vật) → liệt kê đủ, cho chọn mỗi tab một cái.
Loại File Explorer, cửa sổ tool, trình duyệt.
XONG 23/11/2026: winapi/window.py process_exe (QueryFullProcessImageNameW, quyền limited → đọc được cả game chạy Admin).
Nhãn cửa sổ = "tiêu đề (WxH) [exe:pid]" (pid tách 2 client cùng tiêu đề). Đoán: cửa sổ LC.exe trước; không có thì theo
tiêu đề nhưng bỏ explorer/trình duyệt/TeamViewer/IDE/tool. Danh sách trên UI xếp cửa sổ game lên đầu.
Thử thật trên máy dev: "lineage_auto_src - File Explorer" không còn bị chọn; một process đổi tên LC.exe được chọn đúng.
Lưu ý: nhãn cũ đã lưu (không có [exe:pid]) không khớp nữa → tool tự chọn lại LC.exe lần đầu mở bản mới.

---------------------------------------------------------------------------------------------------
## Giai đoạn 1 — Săn cơ bản

### 1.1 Cách đánh tự động (attack mode) — thêm lựa chọn trong cấu hình
Hiện tại (`features/combat.py: _hold_and_drag`): giữ chuột trái, kéo nhẹ 15px, GIỮ nguyên chuột trong lúc đánh.
Yêu cầu thêm 2 chế độ, khi rê lên quái thấy con trỏ kiếm:
- `drag_release`: nhấn giữ chuột trái trên quái → kéo xuống dưới (khoảng cách cấu hình) → THẢ chuột.
  Nhân vật tự đánh đến khi quái chết.
- `drag_to_chat`: nhấn giữ trên quái → kéo đến khung chat → THẢ chuột. Tự đánh đến khi quái chết.
  Vị trí khung chat: cấu hình theo tỉ lệ cửa sổ (mặc định gần CHAT_TOP_FRAC/CHAT_RIGHT_FRAC trong
  vision/play_motion.py), có nút "lấy vị trí" trên UI.
- `hold` (cũ) giữ làm mặc định để tương thích.
Sau khi thả: theo dõi đến khi quái chết (con trỏ X / box biến mất / timeout), KHÔNG nhấn lại liên tục.
Nếu quái chưa chết mà nhân vật ngừng đánh (phát hiện qua box vẫn còn + không có chuyển động) thì làm lại 1 lần.

### 1.2 Phạm vi săn và quay về điểm xuất phát  [BỎ — LÀM LẠI Ở 1.7 (27/11), giữ lại để đối chiếu]
Chế độ: tại chỗ (1), 3, 5, 10, 15, 20, 30 bước, 0 = không giới hạn. Khi bấm Start: lưu vị trí xuất phát
(odometry minimap, KHÔNG gõ "/위치" vào chat — người dùng yêu cầu 26/11).
Không chọn quái ngoài phạm vi, lang thang chỉ trong vòng tròn, ra ngoài thì đi bộ về; "tại chỗ" không đi.
Trận đang đánh mà quái kéo ra ngoài: đánh xong rồi mới về. Không có minimap = không có phạm vi (cảnh báo trên UI).
Hiệu chỉnh: nút "Đo bước" (tab Săn) đo px minimap/bước và lưu vào `scan.step_mm` — làm 1 lần trên máy game (1.2b).

### 1.3 Về làng khi HP thấp
Ngưỡng cấu hình 30–40% (mặc định 35%), phím cuộn về làng cấu hình. Khi HP < ngưỡng (đọc 2 lần liên tiếp):
thả chuột, dừng đánh, bấm phím về làng, chờ, rồi dừng phiên (trạng thái mới "về làng") và ghi log.
Thứ tự ưu tiên: skill hồi máu / bình máu ở ngưỡng cao hơn trước, về làng là bước cuối.

### 1.4 Tự dùng vật phẩm hồi phục
Mở rộng `features/survival.py`: nhiều bình (HP nhỏ/lớn, MP, …) mỗi loại có phím + ngưỡng + thời gian
chờ riêng. Cần đọc MP (xem 2.2) cho bình MP.

### 1.5 Tự nhặt đồ
Feature mới `features/loot.py`: sau khi quái chết, tìm nhãn tên vật phẩm rơi gần xác (đã có
`_box_is_loot_label` trong vision/play_motion.py), click nhặt hoặc bấm phím nhặt (cấu hình),
giới hạn thời gian/số lần, bật/tắt trên UI. CẦN DỮ LIỆU GAME: ảnh chụp màn hình có đồ rơi.

---------------------------------------------------------------------------------------------------
## Giai đoạn 2 — Buff & MP

### 2.1 Hệ thống buff 15 ô (dùng khoảng 10 buff siêu cấp)  [YÊU CẦU XÁC NHẬN]
Yêu cầu người dùng: một khung 15 ô buff; thường dùng khoảng 10 ô cùng lúc, tự chọn ô nào bật.
Không giới hạn cứng 10 — cho bật tối đa 15, giao diện hiện số ô đang bật (vd "10/15").
Hiện có 8 phím F5–F12 (`characters/base.py: HOTKEYS`) dùng chung cho attack/buff/utility → tách riêng:
buff có danh sách 15 ô độc lập (`AccountSettings.buff_slots`, list 15 phần tử).
Mỗi ô:
- bật/tắt
- loại: skill trong catalog HOẶC vật phẩm (buff siêu cấp: bình/cuộn, tên tự đặt, icon tùy chọn)
- phím bấm (do người dùng gán, xem Q2; kiểm tra không trùng phím HP/bình/về làng/attack)
- thời gian hiệu lực (phút/giây), thời gian chờ sau khi bấm
- thứ tự ưu tiên (kéo thả hoặc nút lên/xuống)
- tùy chọn "chỉ buff khi không đang đánh" / "buff cả khi đang đánh"
Chạy: lúc Start bấm lần lượt các ô đang bật (giãn cách CAST_GAP), sau đó tự buff lại khi hết giờ
(giữ cơ chế đếm giờ hiện có trong features/buff.py, theo khóa (ô, skill/vật phẩm)).
Giao diện: cửa sổ "Cài đặt buff" dạng lưới 15 ô (3 hàng × 5 hoặc 5 × 3), mỗi ô hiện icon + phím +
thời gian còn lại khi đang chạy.
Tương thích: cấu hình cũ (buff_skills F5–F12) tự chuyển sang 15 ô khi tải.

### 2.2 Đọc MP
Thêm nút "Lấy mẫu thanh MP" trên UI: người dùng kéo chọn vùng thanh MP trên cửa sổ game → lưu
`mp_template.png` cạnh chương trình. StatBarReader đã hỗ trợ MP (BarColor.BLUE, from_right=True).

---------------------------------------------------------------------------------------------------
## Giai đoạn 3 — Nhiều nhân vật & tổ đội

### 3.0 SĂN THEO NHÓM Ở 타락한 축복의 땅 (ghi 25/11/2026 — CHỜ DỮ LIỆU, chưa làm)
Lý do: bãi orc tím (타락한 축복의 땅 봄/여름/가을/겨울) quái mạnh, đi một mình dễ chết (game KHÔNG bắt buộc nhóm).
Nhóm gồm cả nhân vật của mình (mỗi máy 1 bot, vd. Pháp sư SKCU724 + Kỵ sĩ G1RN30H) và người chơi thật.
Người dùng cần cả 4 việc: đi theo trưởng nhóm · đánh cùng mục tiêu (assist) · hồi máu/buff đồng đội · tự mời/nhận lời mời.

- [ ] DỮ LIỆU CẦN TRƯỚC (người dùng chụp, chép vào records_game/party_ui/):
  1. cửa sổ/thanh nhóm 2–3 người (tên + thanh máu) — lúc đầy máu và lúc có người mất máu;
  2. hộp thoại được mời vào nhóm (nút đồng ý/từ chối);
  3. cách mời người khác (lệnh chat kiểu /초대 tên hay menu chuột phải);
  4. minimap khi có đồng đội (có chấm màu riêng không);
  5. ảnh đang đánh quái cùng nhóm, thấy tên đồng đội trên đầu;
  6. hồi máu cho đồng đội bằng tay: F1+F5 (Hồi phục) có hiện elip để click người khác không.
- [ ] Thiết kế (tab "Nhóm", mặc định TẮT):
  a) vai trò Trưởng nhóm / Thành viên + tên trưởng nhóm + danh sách đồng đội cho phép;
  b) đọc nhóm: tên + % máu từng thành viên → frames.jsonl party[];
  c) đi theo trưởng nhóm: tìm bằng tên trên đầu (OCR như name_reader) hoặc chấm minimap, giữ 80–200 px, mất dấu >10 s → đứng yên + cảnh báo;
  d) assist: chỉ đánh quái trong bán kính R quanh trưởng nhóm, ưu tiên quái đang đánh trưởng nhóm/đồng đội, không đuổi xa;
  e) hồi máu/buff đồng đội (phím → elip → click vào đồng đội), bản thân vẫn ưu tiên khi HP mình thấp hơn;
  e2) CÁCH LÀM ĐƠN GIẢN (người dùng 26/11): game có KHUNG PARTY — cố định vị trí khung Party trên màn hình, rồi hồi máu/buff
      từng thành viên bằng cách nhắm (elip) vào ô tên/thanh máu của họ TRONG KHUNG PARTY, không cần tìm và click nhân vật
      trên bản đồ. Đọc % máu từng thành viên cũng từ thanh máu trong khung này. Cần: ảnh khung Party (records_game/party_ui/),
      vị trí khung cố định + toạ độ từng ô thành viên (cấu hình được / tự dò).
  e3) VAI TRÒ THEO CLASS (người dùng 26/11): trong nhóm, PHÁP SƯ và ELF chủ yếu SĂN TẠI CHỖ (Phạm vi săn = 1, PLAN 1.2:
      đứng yên, đánh/bắn phép quái tới gần, hồi máu/buff qua khung Party). Chỉ HIỆP SĨ (Kỵ sĩ) di chuyển để GOM QUÁI:
      đi một VÒNG LỚN quanh khu vực bán kính ~30 bước (dùng điểm xuất phát + odometry minimap của 1.2), kéo quái theo
      rồi QUAY VỀ vị trí ban đầu (chỗ pháp sư/elf đứng) để cả nhóm đánh. Chế độ mới "Gom quái (vòng tròn)" cho tab Săn:
      bán kính (bước, mặc định 30), số điểm trên vòng, không dừng đánh giữa đường (chỉ chạm quái để kéo), về tới gốc thì
      đánh như bình thường, hết quái quanh gốc thì đi vòng tiếp; HP thấp giữa đường → quay về gốc ngay.
  f) mời/nhận lời mời chỉ với tên trong danh sách cho phép, không nhận người lạ, không gửi chat khác;
  g) an toàn: không bao giờ click/đánh người chơi; trưởng nhóm chết/rời nhóm → dừng, về làng nếu HP thấp;
  h) events: party_state, follow_dist, assist_target, party_heal, invite.
- [ ] Làm từng bước có test bằng ảnh party_ui: (b) → (c) → (d) → build thử trên máy game → (e) → (f).
- Thứ tự trước đó: v18 (orc_v2 + nhận elip nhiều biến thể) → duyệt nhãn orc tím + train orc_v3 (8 bản ghi records_game/spring_summer_autumn) → dữ liệu nhóm → 3.0.


#### 3.0 CHỐT MÔ HÌNH NHÓM CỐ ĐỊNH (khách chốt 27/11 — thay e3 ở trên; 3.0-L/3.0-P KẾ HOẠCH, CHƯA CODE)
Mỗi máy 1 bot, mỗi class một vai, ĐIỂM GỐC CHUNG = chỗ cả nhóm đứng (điểm bắt đầu săn, `ctx.state["home"]`).

| Class | Vị trí | Việc chính | Việc phụ |
|---|---|---|---|
| Tiên (Elf) | đứng yên ở gốc | đánh thường bằng cung, quái trong `attack_range` (mặc định 9 ô) | phép theo luật 1.9 (MP >= `spell_min_mp_pct`, danger/vây, ngoài tầm cung) |
| Hiệp sĩ | ở gốc | BẢO VỆ: chỉ đánh quái trong `guard_steps` (4) bước quanh gốc, không đuổi xa | khu vực sạch `lure_idle_sec` thì ĐI DỤ (3.0-L) |
| Pháp sư | đứng yên ở gốc | HỒI MÁU NHÓM qua khung Party (3.0-P) | tự vệ: đánh thường/phép theo 1.9 khi không ai cần hồi |

**THỨ TỰ LÀM** (mỗi bước test + build thử riêng):
0. Sửa 0.47 của bản ghi 191624: crop gần (CPU), MAX_PROBE_POINTS, danger đếm lặp, analyze_records in near_ms.
1. 1.9 đánh thường là chính (attack_range, spell_min_mp_pct, "Đo tầm đánh", range_walk, melee_attack) — CODE XONG 27/11.
   Vai Tiên = 1.9 + hunt_range > 0 (đứng gốc), không cần code riêng.
2. 3.0-L hiệp sĩ đi dụ 30 bước.
3. 3.0-P pháp sư hồi máu nhóm — CHỈ KHI có ảnh khung Party trong records_game/party_ui/.

**3.0-L HIỆP SĨ ĐI DỤ QUÁI** (dựng trên pull_mode của 1.7: PULL_HITS 2, đi về, chờ PULL_FOLLOW_SEC):
- Cấu hình (tab Săn, chỉ hiện khi class = Knight): `lure` bật/tắt (mặc định TẮT), `guard_steps` (mặc định 4),
  `lure_idle_sec` (mặc định 8, cho phép 5–10+), `lure_steps` (mặc định 30).
- Ở GỐC (bảo vệ tiên/pháp sư, người dùng 27/11): hiệp sĩ chỉ nhận quái trong `guard_steps` bước quanh gốc (đo từ gốc như
  out_of_range của 1.7, không phải từ nhân vật) và không đuổi quá đó. `lure_steps` 30 CHỈ áp dụng trong chuyến dụ.
- Kích hoạt chuyến dụ: đang ở gốc (steps_from_home <= GO_HOME_STOP), KHÔNG có box nào trong tầm phát hiện suốt
  `lure_idle_sec`, HP >= 70%, không danger. Chuyến kế chỉ đi khi khu vực lại sạch đủ `lure_idle_sec` sau khi về.
- Đi: hướng = 8 hướng xoay vòng (N, NE, E, ... mỗi chuyến +1; hướng bị rào trên minimap thì bỏ qua sang hướng kế); mỗi click
  đi WALK_PX theo hướng đó. ĐẾM BƯỚC = CỘNG DỒN CLICK (1 click = 2 bước, như ctx.note_walk của 1.7); ĐƯỜNG VỀ = đi
  NGƯỢC LẠI đúng các click đó (lưu danh sách click của chuyến). Minimap chỉ đối chiếu (log lệch), không dùng để lái:
  30 bước có thể vượt vùng minimap nhìn thấy.
- MỖI CHUYẾN CHỈ DỤ CON ĐẦU TIÊN GẶP: box hover xác nhận bằng con trỏ attack -> event `lure_found {steps, dir, dist}` ->
  engage ở chế độ pull (đánh PULL_HITS 1–2 phát, KHÔNG đánh tới chết) -> về NGAY theo các click ngược ->
  `lure_return {why: "found"}`. Không nhận con thứ hai trên đường về.
- Đủ `lure_steps` mà không gặp -> `lure_return {why: "max_steps"}`, về gốc, hướng kế tiếp ở chuyến sau.
- Huỷ giữa đường: HP < 70% / danger -> `lure_return {why}` về ngay.
- Event `lure_start {dir, idle_s, home_dist}`.
- XUNG ĐỘT phải xử lý: `targeting.out_of_range` bỏ box ngoài hunt_range -> ở gốc dùng guard_steps, trong chuyến dụ dùng
  lure_steps; `exploration.wander` với hunt_range > 0 chỉ biết đi về -> thêm nhánh lure, không đổi hành vi khi lure tắt.
- Test: đơn vị (hẹn giờ idle, xoay 8 hướng, bỏ hướng bị rào, đủ 30 bước thì về, HP thấp thì huỷ); replay bản ghi có minimap
  (101941) với lure bật: không chuyến nào vượt lure_steps + 3, mọi chuyến kết thúc bằng lure_return.

**3.0-P PHÁP SƯ HỒI MÁU NHÓM** (chờ ảnh; giữ thiết kế e2):
- Đọc khung Party: vị trí khung + ô từng thành viên (cấu hình được / tự dò từ ảnh), % máu từ thanh máu trong ô (như stat_bar).
- Luật: thành viên có HP < `party_heal_pct` (mặc định 60) -> chọn người MÁU THẤP NHẤT -> bấm ô phép hồi máu (page, key) ->
  chờ con trỏ elip (CAST_CURSOR_WAIT, như phép tấn công) -> click tên/ô của người đó trong khung Party. Bản thân HP thấp hơn
  -> tự hồi trước (HealthFeature giữ ưu tiên). Không elip = không click.
- Event `party_state {members: [hp%]}` (mỗi phút), `party_heal {member, hp, ok}`.
- Cần trong records_game/party_ui/: khung Party 2–3 người đầy máu + có người mất máu; có thì đo toạ độ, viết test ảnh trước.


### 3.1 Giao diện nhiều tài khoản
Bật `MULTI_ACCOUNT_UI` (ui/main_window.py) — phần lõi đã hỗ trợ (SessionManager, InputArbiter).
Kiểm tra: lưu/đọc nhiều account, mỗi tab chọn cửa sổ riêng, nút Dừng tất cả.

### 3.2 1 PC chạy 2 nhân vật
Hai cửa sổ game trên cùng màn hình, KHÔNG chồng lên nhau, không thu nhỏ (bot đọc pixel màn hình).
Hai phiên thay phiên giữ chuột qua InputArbiter. Cần: kích hoạt đúng cửa sổ trước mỗi thao tác,
giảm thời gian giữ khóa mỗi lượt để cả hai nhân vật đều phản ứng kịp (đặc biệt hồi máu),
ưu tiên khóa cho nhân vật đang thấp máu.

### 3.3 Hồi máu / buff cho thành viên tổ đội
Đọc thanh HP các thành viên trong khung party (CẦN DỮ LIỆU GAME: ảnh khung party).
Khi thành viên < ngưỡng: chọn skill hồi máu → click vào tên/thanh HP thành viên đó. Buff định kỳ cho
thành viên tương tự. Với 2 nhân vật cùng PC: nhân vật hỗ trợ (vd Elf/Wizard) hồi/buff nhân vật kia.

### 3.4 Săn bán tự động theo nhóm 2 nhân vật ở bãi săn đặc biệt
Vai trò: nhân vật chính (đánh) + nhân vật phụ (theo sau, hỗ trợ, đánh cùng mục tiêu).
"Bán tự động" = người dùng điều khiển di chuyển nhân vật chính, bot tự đánh/hồi/buff (xem Q4).
Cấu hình theo bãi săn đặc biệt (model YOLOX riêng — xem 4.2).

### 3.5 Các nhân vật tương tác và hỗ trợ lẫn nhau  [YÊU CẦU NGƯỜI DÙNG 23/11]
Nền tảng: một "bảng trạng thái chung" (PartyBoard) trong SessionManager mà mọi phiên đọc/ghi:
HP%/MP%, vị trí (tọa độ /위치 + vị trí trên màn hình của đồng đội), mục tiêu đang đánh, đang bị quái đánh hay không,
buff còn/hết, còn bình/cuộn không, trạng thái (săn / về làng / chết).
Hành vi hỗ trợ (mỗi hành vi bật/tắt, theo vai trò cấu hình của từng nhân vật):
- Hồi máu cho nhau: nhân vật có skill hồi (Elf/Wizard: Heal, Greater Heal, Heal All) thấy đồng đội < ngưỡng →
  chọn skill → click vào đồng đội (trên màn hình hoặc khung party). Ưu tiên người máu thấp nhất.
- Buff cho nhau: buff có thể niệm lên người khác (Haste, Bless Weapon, Shield…) → giữ buff liên tục cho cả nhóm.
- Đánh cùng mục tiêu (assist): nhân vật phụ đánh đúng con nhân vật chính đang đánh → giết nhanh, không kéo thêm quái.
- Bảo vệ: quái đánh đồng đội → nhân vật kia đánh con quái đó trước.
- Đi theo: nhân vật phụ giữ khoảng cách với nhân vật chính (theo tọa độ), không đi lạc.
- Đồng bộ về làng / tiếp tục săn: một người phải về làng (HP thấp, hết bình) → cả nhóm cùng về hoặc người còn lại
  đứng phòng thủ (cấu hình); "Tiếp tục săn" đưa cả nhóm quay lại cùng bãi.
- Đồng đội chết: báo động, người còn lại về làng hoặc đứng chờ (cấu hình); hồi sinh nếu có skill/vật phẩm.
- Ưu tiên chuột (InputArbiter): phiên có đồng đội nguy cấp hoặc chính mình máu thấp được giữ chuột trước.
Giai đoạn đầu: 2 nhân vật trên CÙNG 1 PC (chia sẻ trực tiếp trong bộ nhớ). Nếu sau này 2 nhân vật ở 2 PC khác nhau:
đồng bộ PartyBoard qua mạng LAN (socket đơn giản) — để sau, cùng A9.

---------------------------------------------------------------------------------------------------
## Giai đoạn 4 — Tiện ích

### 4.1 Bảng thống kê
Thời gian chạy, số quái đã giết, số bình đã dùng, số lần về làng, lần chết; hiển thị trên tab và ghi log.

### 4.2 Bãi săn mới / huấn luyện lại YOLOX
Thêm bãi = thêm HuntMap trong hunt_maps.py + file ONNX trong model/. Viết công cụ thu thập ảnh
(chụp khung hình định kỳ khi đang săn) và hướng dẫn huấn luyện YOLOX-tiny 3 lớp (monster, figure, die)
→ xuất ONNX đầu vào 640x640. CẦN DỮ LIỆU GAME: ảnh các bãi săn mới.

---------------------------------------------------------------------------------------------------
## Quan sát từ video (LC_2026_09_24_151955_Screen.mp4, 15 phút) — ảnh mẫu trong docs/game_reference/
- Cửa sổ game 1280×960. Bãi săn đang quay: vùng "아덴", có hổ (밀림 호랑이) và thằn lằn xanh; góc phải dưới
  ghi "Normal zone". Khi rê chuột lên quái, tên quái hiện trên đầu (vd "밀림 호랑이").
- Nhân vật "TOP" có thanh HP/MP nhỏ trên đầu; luôn ở gần giữa màn hình.
- HUD dưới: thanh HP/MP CÓ SỐ CHÍNH XÁC ("HP:356/432", "MP:36/221") → đọc số (OCR chữ số bằng
  template) chính xác hơn đo độ dài thanh; dùng cho về làng theo % và cho MP (thay mp_template).
- Thanh phím góc phải dưới: 8 ô (2 hàng × 4) có 3 trang F1/F2/F3. Đang gắn: bình đỏ (1312),
  bình cam (244), biểu tượng mũi tên vòng, cuộn (33), skill Hồi máu (+), cuộn môi đỏ, cuộn (22), cuộn (43).
  → Cần hỏi: phím bấm tương ứng từng ô (F5–F12?) và cách đổi trang F1/F2/F3.
- Cột biểu tượng buff đang hiệu lực ở mép phải (2 cột, ~8 hàng ≈ 15–16 ô; video thấy ~12 buff).
  Trùng vùng DEFAULT_BUFF_VISION (vision/buff_icons.py) → dùng để kiểm tra buff còn/hết.
- Minimap góc trái trên (~220×200), mũi tên đỏ = nhân vật. KHÔNG thấy tọa độ số trên màn hình.
  → 1.2 dùng minimap: lúc Start chụp minimap làm mốc, sau đó đo độ dịch chuyển (phase correlation /
  template matching giữa minimap hiện tại và mốc) để biết nhân vật cách điểm xuất phát bao nhiêu bước.
  Lưu ý: góc minimap có chữ "REC 00:xx" của phần mềm quay video — không phải của game.
- Đồ rơi: nhãn khung trắng "아데나 [số]" (adena) kèm đồng xu vàng ngay dưới nhãn; trong video rất nhiều
  adena nằm lại không được nhặt → 1.5 nhặt đồ: nhận diện khung nhãn + click vào đồng xu dưới nhãn,
  ưu tiên gần nhân vật, giới hạn thời gian. Các nhãn này cũng làm YOLOX/nameplate dễ nhận nhầm.
- Khung chat (trái dưới, ~230..960 × 800..935) — đích kéo thả cho chế độ đánh `drag_to_chat` (1.1).

### Bổ sung từ video A (LC_..._144855, 19:42) và B (LC_..._150850, 10:35)
- Cùng bãi săn (vùng 아덴 / 풍룡의 상흔), quái: hổ 밀림 호랑이 + thằn lằn xanh.
- BAN ĐÊM: video A đầu là cảnh tối, chỉ sáng từng vùng tròn → nhận diện phải chạy được khi tối
  (ảnh: night_A0060s.png). Cần đưa ảnh ban đêm vào dữ liệu huấn luyện YOLOX (4.2).
- Nhân vật tấn công TẦM XA (thấy tia tên bắn tới thằn lằn, ảnh arrow_attack_B0400s.png) → có thể là
  Elf dùng cung. Khi dùng cung con trỏ tấn công có thể khác hình kiếm (characters/elf.py đã ghi chú).
- Nhân vật đang biến hình (chat: "해골 선장 외형이 적용되었습니다" = cuộn biến hình Thuyền trưởng xương).
  Biến hình là một "buff siêu cấp" dạng vật phẩm, có thời hạn → đưa vào hệ thống 15 ô (2.1).
- Chat báo buff BẮT ĐẦU/HẾT: "실드: 방어력이 향상됩니다", "실드: 실드가 사라집니다",
  "어스 스킨: …방어력이 향상됩니다", "인챈트 웨폰: …마력이 사라집니다", "갑자기 빠르게 움직입니다"
  (bình tăng tốc). → Đọc khung chat (OCR/template dòng chữ) là cách chắc nhất để biết buff hết
  và buff lại ngay, tốt hơn chỉ đếm giờ. Ảnh: chat_buff_msg_B0420s.png.
- Rê chuột lên biểu tượng buff ở cột phải hiện thời gian còn lại ("가속 효과 … 남은시간: 12분 29초",
  ảnh buff_tooltip_A0940s.png) → có thể đọc thời gian thật của từng buff lúc Start.
- Chat báo nhặt đồ: "상쾌한 빨간 물약(100) 획득" → dùng để đếm đồ nhặt được (thống kê 4.1).
- Thanh phím trang F1 (ảnh hotbar_F1_zoom.png): bình đỏ (E 1421), bình cam (E 251), biểu tượng mũi tên
  vòng (biến hình?), cuộn có số 33, skill Hồi máu (+), cuộn môi đỏ, cuộn 23, cuộn 43. Ở phút 17:20 video A
  thấy trang F2 toàn biểu tượng skill buff (8 ô).
- Max HP thay đổi giữa các video (432 ↔ 402) → về làng theo % phải tính trên max HP đọc được lúc đó.
- Đường cài game (thấy trong chat lúc lưu video): C:\Program Files (x86)\NC\Lineage Classic\
- Mở túi đồ (inventory) có che một phần màn hình → bot phải bỏ qua vùng cửa sổ đang mở hoặc tự đóng.

## Thông tin game tra cứu trên web (11/2026) — dùng làm căn cứ thiết kế
Nguồn chính: inven.co.kr (board lineageclassic), invenglobal.com, diễn đàn chính thức lineageclassic.plaync.com,
lineage.plaync.com (phím của Lineage gốc — Classic giữ nguyên bố cục).

Phím (Lineage gốc, Classic giữ cách dùng F5–F12; diễn đàn chính thức có người xin đổi phím → hiện không đổi được):
- F1/F2/F3: đổi trang thanh phím (3 trang). F5–F12: dùng ô 1–8 của trang hiện tại. Ctrl+1..8 = F5..F12.
- F4: nhặt đồ dưới đất (Lineage gốc) → CẦN KIỂM TRA TRONG CLASSIC.
- Tab / Ctrl+I: túi đồ; Ctrl+A: thông tin nhân vật.
→ Hệ quả: 3 trang × 8 ô = 24 ô. "15 ô buff" = gán vào các ô của trang F2/F3; bot phải bấm F2/F3 đổi trang,
  bấm F5–F12, rồi bấm F1 quay lại trang chính (bình máu/hồi máu). Thêm cấu hình "ô nào ở trang nào".

Cách đánh liên tục (đã được nhiều người chơi xác nhận, đây đúng là yêu cầu 1.1 của người dùng):
- Nhấn giữ chuột trái lên quái rồi kéo xuống khung chat và thả → đánh liên tục đến khi quái chết.
- Ở Classic chỉ cần kéo NHẸ một chút theo hướng bất kỳ rồi thả cũng được.
- Không tự đuổi theo: quái chạy xa thì phải đánh lại. Di chuyển cũng vậy: kéo ra khung chat → nhân vật đi mãi theo hướng đó.
→ 1.1: chế độ mặc định nên là "nhấn – kéo nhẹ – thả" (khoảng cách kéo cấu hình), sau đó chỉ theo dõi;
  nếu quái còn sống mà nhân vật ngừng đánh (quái chạy xa) thì đánh lại.

Vật phẩm (tên trong game, dùng cho buff 15 ô / về làng):
- 귀환 주문서: về làng gần nhất/đã đăng ký. 순간 이동 주문서: dịch chuyển ngẫu nhiên. 축복받은 순간 이동: tới nơi đã ghi nhớ.
- 변신 주문서: biến hình tối đa 1800s (tùy alignment). 초록 물약: tăng tốc di chuyển. 용기의 물약: mọi động tác nhanh hơn.
  파란 물약: tăng hồi MP. 빨간/주홍 물약: hồi HP. 엘븐 와퍼 (Elf).
- Trong video nhân vật dùng 상쾌한 빨간 물약 (hồi HP) và cuộn biến hình.

Bãi săn:
- Video = 풍룡의 상흔 (Scar of the Wind Dragon), phía bắc Aden, đi từ làng Gypsy. Lối vào có lizardman, thằn lằn, harpy;
  sâu bên trong mạnh hơn (killer bee, wyvern…). Lizardman CHỦ ĐỘNG tấn công và chạy nhanh → bot phải ưu tiên
  quái đang đánh mình, phản ứng HP nhanh. Tool hiện KHÔNG có model cho bãi này (dragon_valley không nhận ra hổ).
- Các bãi trong tool: 버림받은 자들의 땅 (Lv30–50, 3h/ngày, toàn bộ là combat zone) và 타락한 자의 땅 là bãi ATS —
  game có săn tự động chính thức (ATS) ở đó. Tool có ích nhất ở bãi KHÔNG có ATS (như 풍룡의 상흔).
- Bãi đặc biệt khác: 잊혀진 섬 (Lv40+, không dùng được cuộn về làng/teleport), 그림자 신전 (ATS, Lv40–59, 1h/ngày).

Chính sách: NC xử phạt rất mạnh macro/chương trình không phép (hàng triệu tài khoản mỗi tháng trong 2026, xử phạt cả
theo "mẫu hành vi bất thường" dù không bắt được chương trình). Báo chí ghi NC cho phép chạy nhiều client.
→ Ảnh hưởng thiết kế: thao tác chuột cần tự nhiên (đường di chuyển, thời gian ngẫu nhiên), không lặp chính xác.

## Câu trả lời của người dùng (23/11/2026) + thông tin bổ sung → QUYẾT ĐỊNH THIẾT KẾ
Phím Lineage Classic (xác nhận ở diễn đàn Classic gall.dcinside talkingisland/108):
  Tab túi đồ · F1–F3 đổi trang phím tắt · F4 NHẶT ĐỒ · F5–F12 ô 1–8 · Ctrl+1..8 = F5..F12 · Ctrl+A trạng thái ·
  Ctrl+S phép · Ctrl+X chế độ niệm phép liên tục · lệnh chat "/위치" (/loc) HIỆN TỌA ĐỘ HIỆN TẠI · "/기억 tên" lưu vị trí ·
  "/getall" cài cách nhặt đồ. Bố cục ô (Lineage gốc): hàng trên F5 F6 F7 F8, hàng dưới F9 F10 F11 F12.

- A1 Bãi săn: hỗ trợ TẤT CẢ bãi, nhận diện MỌI quái.
  → Làm 1 model YOLOX "chung" (lớp monster/figure/die) huấn luyện trên ảnh nhiều bãi + ngày/đêm, giữ cơ chế model
    riêng theo bãi làm tùy chọn. Công cụ thu thập ảnh + gán nhãn bán tự động (dùng con trỏ kiếm/cung lúc rê làm
    nhãn "monster" tự động). Dự phòng không cần model: dò vùng chuyển động + xác nhận bằng con trỏ.
  → Quét nhanh hơn (Giai đoạn 0.1) và PHÁT HIỆN NHÂN VẬT CHẾT NHANH: đọc số "HP:0/xxx" trên HUD (OCR chữ số) +
    nhận cửa sổ hồi sinh/restart, thay vì chờ 3 lần đọc thanh 0%.
- A2 Class (catalog trong tool): 군주 Prince (9 attack, 5 buff), 기사 Knight (cận chiến, Shock Stun, Reduction Armor),
  요정 Elf (cung + tinh linh, 24 buff: Haste, Bless Weapon, Earth Skin…, Triệu hồi tinh linh), 마법사 Wizard (phép,
  Heal All, Haste, Mass Teleport). Elf/Wizard có Greater Heal / Heal All → vai trò hỗ trợ tổ đội.
  → Mỗi class có bộ mặc định riêng (khoảng cách đánh: cận chiến vs tầm xa; con trỏ kiếm hoặc cung).
- A3 Phím/buff: buff KHÔNG cố định, đổi theo thói quen → thêm CHẾ ĐỘ HỌC: khi người chơi tự chơi, tool ghi lại phím
  nào được bấm lúc nào (kèm trang F1–F3, thông báo chat buff bắt đầu/hết, HP/MP lúc đó) → tự đề xuất lịch buff
  (ô nào, bao lâu bấm lại, điều kiện). Người dùng duyệt rồi lưu.
- A4 Buff có thể ở MỌI trang/ô → cấu hình mỗi buff = (trang F1/F2/F3, ô F5–F12). Bot: bấm trang → bấm ô → về trang F1.
- A5 Về làng: cuộn về làng (귀환 주문서) — ảnh người dùng: trang F1, hàng trên ô thứ 4 = F8
  (docs/game_reference/hotbar_F1_return_scroll_user.jpg; bố cục khác video → luôn cho cấu hình).
  Khi HP < ngưỡng (30–40%) → về làng → DỪNG. Thêm nút "TIẾP TỤC SĂN": đi đến bãi săn đã chọn rồi săn tiếp.
  Đi đến bãi: ưu tiên 축복받은 순간 이동 주문서 tới vị trí đã "/기억"; hoặc NPC dịch chuyển; hoặc đi bộ theo
  lộ trình ghi sẵn bằng tọa độ "/위치". (Cần người dùng cho biết cách họ thường quay lại bãi.)
- A6 Cách đánh: mặc định "nhấn – kéo nhẹ – thả"; tùy chọn "kéo vào khung chat".
- A7 Nhặt hết đồ: F4 (chính) + click vào đồ (dự phòng).
- A8 Bot lo đánh/hồi máu/buff/di chuyển tìm quái. Con trỏ trên quái = KIẾM hoặc CUNG; quái chết = hình THÁNH GIÁ.
  ĐÁNH TỪNG CON: giết xong con này mới sang con khác; KHÔNG đánh lan nhiều con (quái kéo tới, hồi máu không kịp)
  → chỉ chọn quái gần nhất, không chạm quái khác khi đang đánh, ưu tiên quái đang đánh mình.
  Nhân vật thứ 2: bất kỳ class/vai trò nào người chơi chọn → vai trò cấu hình được (đánh / hỗ trợ hồi máu-buff / theo sau).
- A9 2 nhân vật trên 1 PC: để sau (báo chí ghi NC cho phép nhiều client).
- A10 Tên exe game: LC.exe (C:\Program Files (x86)\NC\Lineage Classic\LC.exe — ảnh người dùng 23/11).
  Thư mục game có thư mục Capture (video ghi hình) và log. Tiêu đề cửa sổ game: chưa biết.

Vị trí nhân vật (cập nhật 1.2): dùng lệnh "/위치" — bot gõ lệnh vào chat, đọc tọa độ trả về (OCR dòng chat).
Lưu tọa độ lúc Start làm tâm; bán kính 3/5/10/15/20/30 ô tính bằng khoảng cách tọa độ. Minimap chỉ là dự phòng.

### Bổ sung (23/11/2026, lần 2)
- A1+ NHẬN BIẾT QUÁI ĐÃ CHẾT (để chuyển con khác ngay, nhặt đồ, đếm số quái giết): kết hợp nhiều tín hiệu,
  tín hiệu nào tới trước dùng tín hiệu đó:
  1) con trỏ trên quái đổi sang hình THÁNH GIÁ (corpse) — đã có, đọc nhanh hơn;
  2) YOLOX lớp "die" (xác) tại vị trí đang khóa / box "monster" biến mất ở chỗ khóa;
  3) vùng quanh mục tiêu ngừng chuyển động (motion_watch.DeathWatch — đã có code, chưa dùng);
  4) thanh HP nhỏ trên đầu quái (nếu game hiện) về 0;
  5) dòng chat nhặt đồ/kinh nghiệm (nếu có).
  Khi xác nhận chết: thả chuột → F4 nhặt đồ → chọn quái kế tiếp gần nhất. Ghi thống kê số quái đã giết.
- A3/A4+ BUFF LIÊN TỤC: các buff kiểu giáp (Shield, Earth Skin, Blessed Armor…), tốc độ (Haste, bình xanh lá
  초록 물약, bình dũng khí 용기의 물약…), biến hình… → HẾT LÀ BUFF LẠI NGAY, không để trống.
  Phát hiện hết buff: (a) chat báo "...사라집니다"/hết hiệu lực, (b) icon biến mất ở cột buff mép phải,
  (c) đồng hồ đếm ngược theo thời gian hiệu lực — cái nào báo trước dùng cái đó. Bỏ giới hạn REBUFF_FLOOR 8s cũ
  cho loại "liên tục" (vẫn chống spam: chờ xác nhận buff lên hoặc tối đa vài giây giữa 2 lần bấm cùng một buff).
  Nếu đang đánh: chèn buff giữa các nhịp đánh (thả chuột → bấm buff → đánh tiếp), không bỏ quái.
- A5+ QUAY LẠI BÃI SĂN: cấu hình THEO TỪNG BÃI một "lộ trình quay lại" gồm các bước nối tiếp:
  · "teleport_memory": dùng 축복받은 순간 이동 주문서 (trang/ô cấu hình) → chọn vị trí đã "/기억" trong danh sách;
  · "npc_teleport": đi tới NPC dịch chuyển trong làng (tọa độ /위치) → click NPC → chọn điểm đến (theo chữ/ảnh mẫu);
  · "walk": đi bộ qua danh sách điểm tọa độ đã ghi (nút "Ghi lộ trình": người chơi tự đi một lần, tool ghi /위치 mỗi vài giây).
  Nút "Tiếp tục săn": chạy lộ trình của bãi đang chọn → tới nơi thì buff đầy đủ → bắt đầu săn.
  Trước khi đi: tùy chọn mua thuốc (để sau). CẦN DỮ LIỆU GAME: ảnh hộp thoại NPC dịch chuyển, danh sách /기억.

Còn mở: tiêu đề cửa sổ game; 2 client (A9); ảnh hộp thoại NPC dịch chuyển + danh sách "/기억" để làm A5+.

## Dữ liệu cần lấy từ máy game (khi có thể)
Ảnh chụp toàn cửa sổ game: đang săn bình thường, có đồ rơi, khung party có thành viên, thanh MP,
minimap/tọa độ, khung chat; ảnh 2 cửa sổ game đặt cạnh nhau.

---------------------------------------------------------------------------------------------------
## Để sau: triển khai lên máy game
Bot phải chạy trên chính máy game (đọc con trỏ Windows thật + Interception). TeamViewer chỉ để quan sát.
CÁCH NHANH (từ 23/11/2026): gửi dist\LineageAuto_<ngày>.zip (gồm main\, Interception\, deploy\*.bat, HUONG_DAN.txt;
nguồn script ở deploy\). Máy game: giải nén → 1_CAI_DAT.bat (chép vào C:\LineageAuto\main, giữ config/records,
shortcut Desktop, hỏi cài Interception) → đo → 2_GUI_SO_LIEU.bat (zip records + log + config lên Desktop) → gửi về.
Các bước thủ công bên dưới vẫn đúng.
Bản 2 (23/11/2026): dist\LineageAuto_20261123_v2.zip (có 1.3 về làng, 1.4 bình thêm, 1.5 F4 nhặt đồ) + hướng dẫn
tiếng Hàn deploy\GUIDE_KO.txt (có 5 câu hỏi Q1–Q5: F4, 풍룡의 산맥 vs 상흔, bãi hay săn, log chat, cách quay lại bãi).
Bản 2 có cả HUONG_DAN.txt (tiếng Việt, đã cập nhật) và GUIDE_KO.txt; cả hai có mục 7 "Quay video" (yêu cầu + danh sách cảnh cần quay).
BẢN PHÁT HÀNH CHO KHÁCH (25/11/2026): dist\LineageAuto_20261125_v15_release.zip — dựng từ CHÍNH zip bản 15
(dist\LineageAuto_20261125_v15.zip, bản đã chạy thật 11:20-11:35: 62 quái/15 phút), KHÔNG dùng code v16.
Không có commit nào đúng là v15 (v15 nằm trong working tree và đã bị gộp vào commit v16 c29f0a6), nên không thể
checkout lại để build; cách làm là giải nén zip v15 rồi chỉ thay 3 thứ, nguồn ở deploy
elease_v15\:
  · main\lineage_auto_config.json MỚI: scan.detect_fps 2 thay vì 5 (nút duy nhất bản 15 có để giảm CPU; 5/s
    chiếm ~1,7 nhân và làm game khựng lúc đông quái). CHƯA chạy thử thực tế ở mức 2/s.
  · 1_CAI_DAT.bat: thêm 1 dòng chép cấu hình mặc định CHỈ KHI máy chưa có cấu hình (robocopy vẫn /XF file này,
    nên nếu không thêm dòng đó thì cấu hình mặc định không bao giờ tới máy khách). Đã thử cả 2 trường hợp.
  · HUONG_DAN.txt: thêm phần đầu nói rõ đây là bản phát hành dựa trên bản 15 và điểm khác duy nhất.
  main.exe và toàn bộ _internal giống hệt bản 15 (sha256 trùng; 1175/1177 file y nguyên).
Bản 3 (23/11/2026): dist\LineageAuto_20261123_v3.zip — thu dữ liệu (0.6b) + dừng qua TeamViewer (0.7); thêm 3_DUNG_BOT.bat
(1_CAI_DAT.bat tạo thêm lối tắt "DUNG Lineage Auto"). HUONG_DAN.txt đã cập nhật v3, GUIDE_KO.txt vẫn là bản 2.
1. Máy dev: `.venv\Scripts\pyinstaller --noconfirm main.spec`, nén `dist\main\` thành zip.
2. Gửi zip đó + `C:\Tool\Interception.zip` sang máy game qua TeamViewer.
3. Máy game: giải nén Interception, CMD quyền Admin trong `command line installer`,
   chạy `install-interception.exe /install`.
4. Bật TeamViewer "Start with Windows" trên máy game, khởi động lại máy game.
5. Chạy `main.exe`; dòng trạng thái phải là "입력 장치: 정상".
6. Chọn cửa sổ game, đăng ký con trỏ 몬스터 (칼) (+ 시체 (X)), bấm 시작.
7. Lỗi → gửi `session_log.txt` cạnh `main.exe`.
8. Đo nhận diện: khung "데이터 기록" (mục 0.6) → nén → gửi zip trong `records\` về máy dev.
Driver Interception KHÔNG cần cài trên máy dev.

---------------------------------------------------------------------------------------------------
## Bổ sung 27/11/2026 — hai việc lớn (CHƯA CODE, chờ người dùng xác nhận)

### 1.7 PHẠM VI SĂN N BƯỚC — LÀM LẠI (thay thế 1.2 và 1.2c)  [CODE XONG 27/11, CHỜ ĐO TRÊN MÁY GAME]
ĐÃ LÀM: `runtime/context.WalkOffset` (mixin, test dùng đúng code thật) giữ `state["offset"]` = px client từ
gốc tới nhân vật; `note_walk` cộng mỗi click đi bộ (<= `CLICK_STEPS` 2 bước), `note_arrival` dùng khi trận vào
cận chiến (nhân vật đã đi tới chỗ quái). `vision/minimap.step_px` = 1 bước = `step_mm` x 10 px/px minimap
(23 px ở 1280). `targeting.from_home` / `steps_from_home` / `out_of_range` đo TỪ GỐC bằng offset (không cần
minimap); `home_drift` so với odometry chỉ để ghi log. `in_place()` = `hunt_range > 0 and ranged()` (theo
CLASS). N > 0 thì `exploration.wander` chỉ đi về gốc, không bao giờ lang thang (và không lang thang mù khi
không biết đường). `combat.engage_ranged` kết thúc trận khi mục tiêu ra ngoài phạm vi (thay vì hằng 350 px).
`scan.pull_mode` + ô "Kéo quái (1 = bật)" cạnh "Phạm vi săn"; `combat.pulling/_pull_danger/_start_follow_watch`
+ `session._walk_home/_pull_follow`. Test: `tests/test_in_place_101929.py` (tầm từ gốc, vùng chết, 1 click =
2 bước, sổ sách kéo quái) và `check_range` + `check_in_place_101941` trong `tests/test_hunt_records.py`.
CHƯA ĐO ĐƯỢC Ở LAPTOP: quái có bám theo không, kill rate của chế độ kéo -> cần bản ghi mới trên máy game.

LÝ DO LÀM LẠI: bản 1.2/1.2c hiểu sai ý khách. Đã làm: "phạm vi" = vòng tròn trên minimap, bot vẫn lang thang
trong vòng tròn, và "tại chỗ" bị gán cho riêng mức N=1 (`hunt_range == IN_PLACE_RANGE`), tầm bắn là một hằng số
350 px không liên quan tới N. Ý khách: GỐC + N bước, không lang thang, đánh xong VỀ GỐC, và "đứng im" là tính
chất của LỚP NHÂN VẬT (pháp sư/tiên), không phải của mức N.

Quy tắc mới (N = `scan.hunt_range`):
- Gốc = vị trí lúc bấm "Bắt đầu săn" (`ctx.state["home"]`, như cũ) + offset = (0,0).
- N = 0: giữ nguyên hành vi săn tự do hiện tại (lang thang, không giới hạn). N > 0: KHÔNG wander.
- 1 bước = 1 ô game = `scan.step_mm` px minimap (mặc định `minimap.STEP_MM` 2.3) = step_mm × `minimap.scale`
  px màn hình ≈ 23 px ở cửa sổ 1280; 1 click = 2 bước ≈ 46 px. Minimap vẽ theo hướng màn hình và hệ số
  ~10 px client/px minimap gần như đều theo cả x và y (ghi chú đo ở đầu `vision/minimap.py`: 8,5–12,5), nên
  dùng MỘT hệ số vô hướng, không tách trục isometric. shortcut: nếu kiểm trên bản ghi thấy lệch x/y > 20%
  thì mới tách thành hai hệ số.
  Kiểm lại bằng `records_game/20261126_192615_observe`: 2 lượt x 5 click = **10 click = 20 BƯỚC**
  (sửa 27/11 theo người dùng; mục 1.2b cũ ghi "10 bước" là sai) → px/bước = tổng dịch chuyển / 20.
- Pháp sư/Tiên (`character.style != MELEE`) — SỬA 27/11 (1.7b), lý do: N bước CHỈ dành cho DI CHUYỂN, không
  phải tầm đánh. Khi săn nhóm, nếu bắt pháp sư/tiên chờ quái vào trong N bước quanh gốc thì hiệp sĩ kéo quái
  về sẽ đứng một mình, nhóm vỡ. Nay: ĐỨNG IM ở gốc (bị đẩy lệch thì về theo vùng chết/hysteresis), tầm nhắm =
  TẦM THẬT tính từ NHÂN VẬT (`targeting.shot_reach()`: "tầm px" lớn nhất của các ô phép đang bật, không đặt thì
  `IN_PLACE_SHOT_PX` 350 px), KHÔNG lọc theo N bước nữa. Quái vào tầm là bắn, ưu tiên con gần nhất (danh sách
  đã xếp gần-trước) và con đang đánh mình (`closer_than(hurt=True)`, 0.43). N bước chỉ còn (1) giới hạn hiệp sĩ
  đi kéo, (2) vùng chết + đường về gốc.
  CHƯA LÀM: ưu tiên riêng cho "con đang lại gần gốc/nhóm" - cần lưu lịch sử chuyển động từng box, chưa thấy
  bằng chứng là cần (xếp gần-trước đã đủ trên các bản ghi).
- (bản cũ 1.7, đã bỏ) Pháp sư/Tiên: chỉ nhắm quái cách GỐC ≤ N bước, chỉ
  bắn phép (`combat.engage_ranged`, đã có), không bao giờ click/giữ chuột để đi. Không có quái trong tầm thì
  đứng chờ. Bị đẩy lệch > `IN_PLACE_DRIFT` (3 bước) thì click về gốc.
- Cận chiến (VIẾT LẠI 27/11 theo yêu cầu mới: hiệp sĩ đi tới để KÉO quái, không cần đánh chết tại chỗ).
  Tuỳ chọn mới `AccountSettings.pull_mode`, MẶC ĐỊNH BẬT khi N > 0 (có ô bật/tắt trên tab Săn, ko/en/vi).
  * BẬT ("Kéo quái"): quái cách gốc ≤ N bước thì đi thẳng tới, đánh 1-2 phát (chỉ tính là đã đánh khi có
    con trỏ KIẾM trên quái VÀ lệnh đánh đã bấm - `PULL_HITS` 2), rồi đi ngược đúng quãng đã đi về gốc.
    Về tới gốc thì đánh những con đã theo về, ĐỨNG TẠI CHỖ (không đuổi ra ngoài N bước).
    Quái không theo về: sau `PULL_FOLLOW_SEC` ~5 s không có box nào trong `PULL_HOME_PX` 100 px quanh gốc
    thì đi kéo lại con đó, tối đa `PULL_RETRIES` 2 lần rồi blacklist nó.
    Đang kéo mà HP tụt nhanh (`HealthFeature.hp_falling`) hoặc >= 3 quái vây (`state["mobs_near"]`,
    ngưỡng `DANGER_MOBS`) -> về gốc NGAY, bỏ lượt kéo đó.
  * TẮT: đi tới đánh chết rồi mới về gốc (hành vi đã mô tả trước đó).
  * Mỗi lượt kéo ghi event: `pull_start` (anchor, bước từ gốc), `pull_hit` (lần đánh thứ mấy, con trỏ),
    `pull_return` (lý do: đủ phát / nguy hiểm / mất quái), `pull_follow_ok` / `pull_follow_fail`
    (số quái quanh gốc sau `PULL_FOLLOW_SEC`, lần kéo lại thứ mấy) -> đo được trên máy game.
  * KHÔNG MÔ PHỎNG ĐƯỢC BẰNG REPLAY: quái có bám theo nhân vật hay không. Replay chỉ kiểm được phần
    "đi tới - đánh đủ phát - quay về đúng quãng - đứng tại chỗ ở gốc" trên các khung đã ghi; phần
    `pull_follow_ok/fail` và kill rate thật sự PHẢI ĐO TRÊN MÁY GAME (bản ghi mới, chế độ 2).
- Theo dõi vị trí = CỘNG DỒN DỊCH CHUYỂN trên màn hình (camera luôn giữ nhân vật ở giữa):
  `ctx.state["offset"]` (px client, so với gốc) được cộng tại CHỖ RA LỆNH ĐI:
  * click đi bộ (exploration, về gốc, `survival` bước lùi): += vector đơn vị tới điểm click × min(46 px,
    khoảng cách tới điểm click);
  * đuổi theo quái trong trận (`combat._hold_and_drag` / `_refresh_hold`): KHÔNG cộng từng nhịp (sẽ cộng quá);
    khi trận chuyển sang cận chiến (box trong `MELEE_DIST`) thì đặt offset = offset lúc vào trận +
    (điểm neo lúc đó − tâm nhân vật), vì nhân vật đã đi tới chỗ con quái.
  * Minimap (odometry 2,3 px/bước) nếu đang bật: dùng để ĐỐI CHIẾU và sửa offset (odometry là chuẩn khi có);
    tắt minimap vẫn chạy đủ, chỉ sai số lớn hơn (cảnh báo trên UI đổi lại cho đúng nghĩa mới).
- Về gốc: lặp click theo vector −offset (mỗi click ≤ 46 px) đến khi |offset| ≤ 1 bước hoặc quá
  `GO_HOME_MAX_SEC` (10 s) → log + chọn mục tiêu tiếp. Mỗi nhịp vẫn `poll_escape` + `ctx.running`.

Sửa ở đâu (dự kiến, diff nhỏ nhất):
- `features/targeting.py`: `in_place()` = `hunt_range > 0 and ranged()` (bỏ nghĩa riêng của N=1);
  `out_of_range()` đo từ GỐC bằng offset (không cần minimap nữa), tầm = N × step_px; bỏ hằng
  `IN_PLACE_SHOT_PX` khỏi việc chặn mục tiêu (tầm thật của phép vẫn do `range_px` từng ô phép quyết định —
  UI cảnh báo nếu N × 23 px > range_px lớn nhất đang bật).
- `features/exploration.py`: N > 0 → không wander, chỉ `go_home`; `IN_PLACE_DRIFT` áp cho lớp đứng im.
- `features/combat.py`: cuối mỗi trận của lớp cận chiến đặt `ctx.state["go_home"] = True`.
- `runtime/session.py`: trước khi chọn mục tiêu, nếu `go_home` thì về gốc xong mới `targeting.acquire`.
- `runtime/context.py` (hoặc targeting): hàm cộng offset duy nhất, mọi chỗ click đi bộ gọi qua nó.
- UI: `scan_panel` giữ nguyên ô "Phạm vi săn" (0/1/3/5/10/15/20/30), đổi chữ giải thích + cảnh báo
  (ko/en/vi) cho đúng nghĩa mới; không thêm thông số mới.
Test: `tests/test_hunt_range.py` — (a) step px tính từ 192615 khớp 10 bước ±10%; (b) sai số offset cộng dồn so
với odometry trên toàn bản ghi 101941 (minimap bật mọi khung) ≤ 2 bước mỗi chu kỳ trận; (c) pháp sư ở N=10
không phát ra click đi nào; (d) cận chiến: sau mỗi trận có một pha về gốc trước mục tiêu kế tiếp; (e) N=0 giữ
nguyên số trận/kill như hiện tại trên các bản replay cũ (không hồi quy).

### 0.43 NHẬN DIỆN QUÁI Ở GẦN (khách báo: quái gần bị sót / không nhận lại / bot đánh con khác)
THỨ TỰ (người dùng 27/11): làm 0.43 TRƯỚC, 1.7 sau.
ĐIỀU KIỆN BẮT ĐẦU: chưa sửa gì liên quan tới tường cho tới khi có `records_game/20261126_225217_hunt` và
`20261127_003555_hunt` trên laptop (đang kéo từ máy game). Khi có: chạy `test_near_miss` trên CẢ 4 bản ghi
(101941, 090350, 225217, 003555) để lấy số "trước". Sau khi sửa phải: `check_walls_225217` vẫn PASS và số
trận/kill mô phỏng trên 003555 KHÔNG giảm.
Phần làm được ngay (không đụng tường): khung đầy theo thời gian >= 1 s, giữ vết quái qua 3 lần quét, khoá mục tiêu.
Phần CHỜ bản ghi: TTL blacklist 1 s cho quái < 100 px (đó là phần đụng 0.40/0.42).

B1 — ĐO TRƯỚC KHI SỬA (`tests/test_near_miss.py`), trên `20261126_101941_hunt` và `20261126_090350_hunt`
(`20261127_003555_hunt` không có trên laptop này → bỏ qua, chạy khi có):
- mỗi khung: các box cách nhân vật < 150 px (bỏ `SELF_R` 30 và box "die");
- chỉ số 1: tỉ lệ khung có box gần mà bot không rê/không đánh con đó trong 2 s ("quái gần bị sót");
- chỉ số 2: số lần đổi mục tiêu khi box của mục tiêu cũ vẫn còn trong khung ("đổi mục tiêu sai");
- tách NGUYÊN NHÂN bằng các bộ đếm đã có + thêm log: `out_of_range_skip`, `_recent_miss` (miss_ttl 4 s),
  `is_blocked`, bị cắt bởi `scan.max_probe_points` (5), hoặc rê lên mà con trỏ không phải con trỏ tấn công.
LƯU Ý ĐÃ CÓ SẴN (không code lại): trong trận detector đã CHẠY XEN KẼ khung đầy 640 và 416+crop ở 2 lần/s,
tức khung đầy đã ~1 lần/s (`runtime/detector._mode`) — KHÔNG phải "chỉ ROI 320"; và quái < `NEAR_KEEP` 100 px
đã được miễn miss/blacklist và xếp trước trong `targeting.candidates`. Nên chỉ sửa cái mà B1 chứng minh là sai.
B2 — SỬA (theo kết quả B1):
- [XONG 27/11] khung đầy trong trận theo THỜI GIAN (`detector.FULL_EVERY` 1 s kể từ khung đầy trước) thay cho
  `seq % 2`, nên fps tụt xuống 1/s vẫn còn khung đầy;
- [XONG 27/11] GIỮ VẾT QUÁI QUA KHUNG: `targeting._update_tracks` giữ [x, y, số lần quét liên tiếp không thấy],
  xoá sau `TRACK_MISSES` 3 lần, ghép theo box gần nhất trong `TRACK_MATCH_PX` 48 px; `targeting.tracked` =
  hits + các điểm còn nhớ. CHỈ việc ĐUỔI THEO mục tiêu (`track_current`) dùng danh sách này → một khung trượt
  không làm mất khoá, nhưng `candidates` / `mobs_near` / `closer_than` vẫn chỉ dùng box THẬT (nếu không, điểm
  nhớ sẽ thổi phồng "đám quái" của luật danger 0.40 và làm trận kết thúc oan). Điểm nhớ không di chuyển theo
  nhân vật — chấp nhận được trong ~1,5 s nó tồn tại. Wander (`reset_misses`) xoá hết vết.
- [XONG 27/11] khoá mục tiêu đến khi chết/mất thật: `BOX_GONE_SEC` nay tính trên vết đã giữ, không cần code mới.
  QUAN TRỌNG: điểm "nhớ" KHÔNG được tính là tiến triển/cận chiến (`targeting.lock_live`, `combat.live`) - lần
  thử đầu để nó tính đã làm một trận ở 82 px kết thúc "unreachable" sau 1,8 s và `check_idle_101941` FAIL,
  tức là nó lấn sang luật tường 0.40/0.42 (phần đang chờ bản ghi). Vết chỉ GIỮ trận, không đổi luật bỏ trận.
  SỐ ĐO replay (HEAD 01689f3 -> sau sửa, `tests/test_hunt_records.py`):
  092741: 92 -> 87 trận, kill 6 -> 8, gone 50 -> 28, lost 3 -> 15, unreachable 18 -> 17, blacklist 18 -> 17,
  dòng chat kill 21 -> 21; 101941: 78 -> 75 trận, kill 2 -> 2, gone 19 -> 13, unreachable 9% -> 9%, wall 3 -> 2,
  phép 23 -> 23, "đứng im" 64 -> 70 phép, idle sau 161 -> 167 s (trận giữ lâu hơn một chút). Không giảm kill.
- quái < 100 px không vào blacklist dài: `targeting.block` dùng TTL 1 s cho điểm trong `NEAR_KEEP`.
  RỦI RO: điều này nới lỏng phần "wall/unreachable" của 0.40/0.42 → có thể quay lại cảnh đứng kẹt trước hàng
  rào; bản ghi `20261126_225217_hunt` (bản ghi về tường) KHÔNG có trên laptop này nên không kiểm được tại chỗ.
- [XONG 27/11] quái < 100 px không vào blacklist dài: `targeting.BLOCK_TTL_NEAR` 1 s (xa vẫn 60 s / 8 s).
  `check_walls_225217` (bản ghi đã kéo về 27/11) vẫn PASS: 14 trận wall, còn 1 blocked ở 524 px >=
  `WALL_MIN_DIST`, hướng đi bộ clear 1019/1464 (70%); replay không đổi (092741 kill 8, 101941 kill 2,
  unreachable 9%). NHƯNG xem B3: thay đổi này ĐO ĐƯỢC LÀ KHÔNG ĂN GÌ - không có box gần nào từng bị bỏ
  vì blacklist trong các bản ghi này. Giữ vì vô hại và đúng ý khách, không tính là đã sửa lỗi.

B3 — SỐ ĐO (`tests/test_near_miss.py`, quái < 150 px, 27/11):
| bản ghi | A không vào danh sách mục tiêu | lý do | B gần hơn mục tiêu >= 2 lần, không trỏ tới trong 2 s | C đổi mục tiêu khi còn box gần |
|---|---|---|---|---|
| 090350 | 135/585 (23%) | 135/135 = `scan.max_probe_points` cắt | 6/12 | 9/10 |
| 225217 | 24/329 (7%) | 24/24 = `max_probe_points` cắt | 5/9 | 7/8 |
| 101941 | 0/10 | - | 2/2 | 0/0 |
TRƯỚC (01689f3) và SAU giống hệt nhau trên cả ba chỉ số -> hai sửa đổi vòng đầu (khung đầy theo thời gian,
giữ vết quái) KHÔNG cải thiện ba chỉ số này; chúng chỉ hiện ở bảng kill/gone của replay.
KẾT LUẬN QUAN TRỌNG (khác giả thuyết ban đầu):
1. Đường CHỌN MỤC TIÊU không bỏ quái gần vì miss_ttl / blacklist / corpse / ngoài tầm: 0 trường hợp.
   Toàn bộ A là `max_probe_points` = 5 cắt phần CUỐI của một đám quái, mà danh sách xếp gần-trước, nên
   những con bị cắt vẫn xa hơn 5 con được chọn -> KHÔNG phải lỗi.
2. Chỗ còn lại là trong TRẬN: `targeting.closer_than` chỉ đổi mục tiêu khi con gần hơn nằm trong
   `MELEE_DIST` 70 px (và mục tiêu hiện tại ngoài 70 px). Một con ở ~100 px trong khi bot đang đánh con ở
   300-400 px thì bot giữ nguyên -> đúng cảnh khách báo "bot đánh con khác". 11/21 lần (090350 + 225217).
   CHỜ NGƯỜI DÙNG QUYẾT: nới ngưỡng đổi mục tiêu lên `NEAR_KEEP` 100 px (hoặc bỏ hẳn, chỉ còn
   `SWITCH_SHARE`) thì ngược với yêu cầu "khoá mục tiêu tới khi chết/mất" - hai việc này chống nhau.
   Mẫu nhỏ (12 và 9 khung đủ điều kiện), nên nếu nới thì phải đo lại kill trên replay.

### C (1.8) THỜI GIAN BUFF NHẬP THEO GIÂY  [XONG 27/11]
Ô thời gian buff trong "Cài đặt skill → Buff" nhập theo GIÂY, nhãn "giây" (`unit_sec`, ko/en/vi đã có),
bước 10 s, khoảng 10 s - 86400 s. Config VẪN lưu phút (`BuffSkillSetting.duration_min`) nên config cũ không
cần chuyển đổi gì và không thể lệch nhịp buff: 11,5 -> 690 s, 19,5 -> 1170 s, 30 -> 1800 s (x60, đọc ngay ở
giao diện). Hai hàm đổi đơn vị duy nhất: `ui/skill_summary.buff_seconds` / `buff_duration_min`
(+ `BUFF_MIN_SEC`/`BUFF_MAX_SEC`/`BUFF_STEP_SEC`); `ui/skill_setup_modal` và dòng tóm tắt dùng chúng
(tóm tắt in "690s" thay cho "11.5m"). Ô "chờ" của bình (1.4b) GIỮ NGUYÊN hộp giây/phút: bình cần cả 1,5 s
(bước 10 s không biểu diễn được) lẫn 10 phút; hai chỗ thống nhất ở chỗ đều hiện giây theo mặc định.
`ui/panels/skills_panel.BuffSkillsPanel` (bảng cũ, KHÔNG được dùng trong UI thật) vẫn để phút - không sửa.
Test: `python tests/test_buff_duration.py` (config cũ ra đúng giây; lưu-rồi-load mọi bước 10 s không đổi;
giá trị ngoài khoảng bị kẹp; dòng tóm tắt in giây).

### 0.44 LƯỢT "TẠI CHỖ" v21rc5 TRÊN MÁY GAME HỎNG  [SỬA 27/11]
Bản ghi: `records_game/20261127_101929_hunt` (pháp sư, hunt_range 1, minimap bật, 6 phút, MP 61-87%),
101258 (minimap tắt, 96 s), 101711/101807 (ngắn, CÓ bắn phép).

1. KHÔNG BẮN PHÉP (ưu tiên cao nhất, đã sửa). 101929: 68 trận, `spell_cast` 0, `page_switch` 0, kill 0, mọi
   `fight_end` có `spells: 0` và `skipped: {}`. Nguyên nhân: `engage_ranged` khi `active_skills()` rỗng (hoặc
   mọi ô đang trong cooldown) chỉ `continue` cho hết 10 s cap - KHÔNG log, KHÔNG ghi gì. Không liên quan MP:
   replay chính bản ghi đó với phép của máy game (F2+F5 386) cho **55 spell_cast / 41 trận (46 lên ellipse)**,
   nên code bắn phép vẫn đúng; lượt thật đơn giản là KHÔNG CÓ ô phép nào đang bật (các lượt 101258-101807
   trước đó có `page_switch` + `spell_cast`, từ 101849 thì cả hai = 0).
   Sửa: `combat._no_spell` - cảnh báo WARNING một lần/phiên, `skipped {"no_skill": 1}`, FALLBACK đánh tay
   (`engage(..., force_melee=True)`) khi quái trong `MELEE_DIST`, còn lại kết thúc ngay với outcome mới
   `no_spell` thay vì nhắm im 10 s; `_pick_skill` nay ghi cả lý do `cooldown` và nhánh `paused` ghi `paused`
   (không còn đường nào im lặng); cảnh báo trên UI `warn_in_place_no_skill` (ko/en/vi) khi săn tại chỗ mà
   không có ô phép nào bật.
2. ĐI QUA ĐI LẠI (đã sửa phần cấp cứu, phần gốc thuộc 1.7). 113 `go_home` luân phiên N/S trong khi
   `home_dist` đọc 3,3-7 bước và pos nhảy 10 px = nhiễu odometry, ngưỡng cũ `IN_PLACE_DRIFT` 3 bước quá chặt.
   Sửa: `exploration.GO_HOME_START` 4 bước (= 2 click) mới bắt đầu về, `GO_HOME_STOP` 1 bước mới dừng
   (hysteresis), KHÔNG về khi còn quái trong tầm (`_monster_in_reach`), và "tại chỗ" không bao giờ lang thang
   mù khi không biết đường về. Cách tính vị trí đúng (cộng dồn dịch chuyển màn hình) vẫn làm ở 1.7.
3. out_of_range_skip 346 KHÔNG phải lỗi: 269/743 box của bản ghi nằm ngoài 350 px (`IN_PLACE_SHOT_PX`), và
   test mới kiểm trực tiếp 300 px được giữ / 400 px bị bỏ, cả khi minimap bật và tắt - vòng tròn hunt_range
   không thu nhỏ tầm bắn.
4. `scan.step_mm = 0.0` trong meta: bản cài KHÔNG ghi đè config (`deploy/1_CAI_DAT.bat` robocopy `/XF
   lineage_auto_config.json`), và các giá trị tự đặt khác vẫn còn (max_probe_points 2, conf_map blessed_orc),
   nên config không bị thay - phép đo bước chưa từng được lưu (nút "Đo bước" bỏ qua kết quả ngoài 1-20 px
   hoặc khi không có minimap). 1.7 không cần nó nữa (đo bằng px màn hình).
Test: `python tests/test_in_place_101929.py` (tầm bắn; 0 go_home trên nhiễu đã ghi + hysteresis + quái trước;
không có phép -> `no_spell` + 0 cap im lặng + 1 WARNING; có phép -> 55 lần bắn).

### 0.45 MẤT CẤU HÌNH PHÉP TẤN CÔNG KHI BẤM "ÁP DỤNG" (LỖI NGHIÊM TRỌNG)  [SỬA 27/11]
Khách báo (máy game, v21rc5): cả tab "Đánh" trong Cài đặt skill bị reset - Tia Năng Lượng (386) về
F1 / trống / không tích / MP 0 - còn buff, bình thêm, về làng nguyên vẹn.
NGUYÊN NHÂN (đã dựng lại được 100% trên laptop, `tests/test_skill_setup_modal.py` FAIL ở bản 01689f3 với đúng
giá trị khách thấy `(False, '', 'F1', 0, 0, 0.0)`): các bước kiểm trùng phím trong `ui/skill_setup_modal.py`
PHÁT HIỆN theo đúng ô (page, key) nhưng TRẢ VỀ phím trần ("F5"), rồi `_clear_row_hotkeys` /
`_disable_draft_hotkeys` / `_hp_overlap_messages` lại so sánh bằng phím trần → xoá MỌI dòng dùng F5 ở MỌI
trang. Chỉ cần 1 buff ở F1+F5 (đúng ô phím hồi máu của tab Máu chiếm) là lần "Áp dụng" sau xoá luôn phép
tấn công ở F2+F5. Buff ở các phím khác không bị gì → khớp đúng hiện tượng khách thấy.
SỬA: mọi chỗ mang (page, key) suốt đường đi (`_conflict_slots`, `_clear_row_hotkeys`, `_disable_draft_hotkeys`,
`_hp_overlap_messages`, bỏ `_keys_of`). THÊM LỚP CHẶN: "Áp dụng" dựng lại toàn bộ map từ các dòng đang hiện,
nên nay những ô đang gán một skill mà modal KHÔNG hiện (danh sách của class khác, catalog đổi) được GIỮ
NGUYÊN thay vì bị xoá âm thầm.
`cast_order`: không có đường code nào ghi `click_key` - chỉ có combobox (người dùng chọn) và luật thất bại
chat (0.35) chỉ đặt `hover_key_click`. Test mới khoá `cast_order` qua đổi ngôn ngữ ko/en/vi + mở/Áp dụng/Huỷ.
Test: `python tests/test_skill_setup_modal.py` (đổi ngôn ngữ + lưu; mở rồi Huỷ; mở rồi Áp dụng với buff ở ô
phím hồi máu -> phép ở trang F2 còn nguyên; trùng ô thật vẫn cảnh báo và chỉ xoá đúng dòng đó).
0.45b (27/11, theo yêu cầu khách): trùng ĐÚNG MỘT Ô giờ chỉ CẢNH BÁO (nêu tên ô, ví dụ "F2+F5") và CHẶN
"Áp dụng", không xoá dòng nào - người dùng tự sửa. Xung đột với phím của tab Máu cũng vậy. Bỏ hẳn
`_clear_row_hotkeys` / `_disable_draft_hotkeys`.
GHI CHÚ: lỗi này giải thích luôn 0.44 mục 1 - lượt 101929 không có ô phép nào bật vì nó vừa bị xoá lúc
~10:18:4x khi khách mở Cài đặt skill và bấm Áp dụng.

### 3.0b Chế độ "KÉO QUÁI" cho hiệp sĩ — ĐÃ CHUYỂN VÀO 1.7 (27/11)
Khách yêu cầu làm ngay cho một nhân vật, nên phần "đi kéo rồi về gốc" nằm trong 1.7 (`pull_mode`).
Còn lại ở 3.x: kéo về cho NHÓM (hiệp sĩ kéo, pháp sư/tiên ở gốc bắn) - cần nhiều nhân vật, chưa làm.

GHI CHÚ MÁY: laptop này là Python 3.14, chỉ chạy test, KHÔNG build bản phát hành (bản phát hành phải dựng
trên máy có 3.12).

### 0.46 NHẬN DIỆN QUÁI GẦN GẦN NHƯ KHÔNG SÓT — KẾ HOẠCH (27/11)
MỤC TIÊU: recall quái trong 150 px quanh nhân vật >= 97%; CPU của bot tăng <= 30% so với v21.
THỨ TỰ: B1 (đo, có bảng số) -> B2.1 detect vùng gần -> B2.2 tracker + chuyển động -> B2.3 vòng rê;
**mục 5 (hard cases) bật NGAY** vì nó chỉ ghi dữ liệu, không đổi hành vi. Không code B2 trước khi có bảng B1.

#### Đã có sẵn — KHÔNG viết lại
- `yolox_mobs.detect(frame, cx, cy, radius, conf=, size=, roi=)`: MỘT lần inference rồi `project(class, conf)`
  lọc theo ngưỡng → **ngưỡng conf thứ hai cho vùng gần tốn 0 ms**; `size` chọn bản export
  (`model/<map>_416.onnx` / `_320.onnx`, hiện chỉ blessed_orc và fallen_blessed có), `roi_box` đã biết cắt
  quanh nhân vật, `_blank_play_hud` đã xoá HUD.
- `vision/play_motion.motion_centroids(prev, curr, cx, cy, radius)`: **đã viết, hiện không được gọi ở đâu** —
  đúng việc của B2.2 (vùng chuyển động gần nhân vật, nearest-first, đã bỏ HUD). Chỉ cần nối lại.
- `targeting._update_tracks` (vết quái, `TRACK_MISSES` 3 / `TRACK_MATCH_PX` 48, chưa có dự đoán vị trí),
  `targeting.probe` (xác nhận con trỏ kiếm, 4 lần đọc, ~0,2 s/điểm khi trượt), `grid_scan.sweep` (quét vòng
  nhanh, 1 lần đọc/điểm ~0,05 s), `survival.hp_falling`, `session._defend`, `recorder.save_snapshot/event`,
  `hovers.jsonl`, `labels.json` (nhãn ĐIỂM, không phải box), `tests/eval_detection.score/evaluate`,
  `name_reader.is_night_frame`, `tests/prelabel.py` + `tests/label_tool.py`.

#### B1. ĐO (`tests/eval_near_recall.py`) — có 4 phần (a)-(d), báo bảng trước khi code B2
Chạy với `--config records_game/game_pc_config.json` (đúng input_size/detect_roi máy game).
(a) **BẢNG SÓT THEO KHOẢNG CÁCH**: cột = `< 100`, `100-200`, `> 200` px tính từ nhân vật; dòng = tất cả /
    **đè lên nhân vật** (nhãn <= 100 px và trong 40 px của một `figure`) / **bị che** (có nhãn khác hoặc
    figure trong 40 px) / **ngày** / **đêm** (`labels.json["night"]`); mỗi ô: nhãn / tìm được / recall % /
    box sai trên frame.
    GIỚI HẠN DỮ LIỆU: nhãn tay và ẢNH chỉ cùng tồn tại ở **092741** (162/849 frame đã nhãn, 467 quái) +
    `docs/game_reference` (10 ảnh). Các bộ ngày/đêm/bốn mùa (`*_observe_*`, 400+ frame đã nhãn, có cột
    `night`) **không có ảnh trên laptop này**; 090350 / 101941 / 225217 có ảnh nhưng nhãn còn `todo`.
    Nên B1 gồm: nhãn thêm 090350 + 101941 + 225217 (`prelabel.py` → `label_tool.py --review`, ưu tiên frame
    có hover kiếm gần), và xin lại ảnh các bản ghi observe ngày/đêm từ máy game. Chưa có thì ghi "chưa đo",
    không đoán.
    NHÃN YẾU bổ sung (miễn phí, cho frame chưa nhãn tay): hover con trỏ KIẾM trong `hovers.jsonl` = có quái
    tại điểm đó; dòng chat kill = có quái ở ô khoá. In thành recall "theo bằng chứng con trỏ", KHÔNG trộn với
    recall theo nhãn tay.
(b) **Lợi ích của conf thấp**: detect lại từng frame ở conf thường và ở 0,1, đếm box MỚI <= 150 px/frame,
    chia "có bằng chứng" (hover kiếm <= 24 px trong 2 s) và "không có bằng chứng".
(c) **Detect crop 400x400 ở độ phân giải gốc**: cùng frame, detect thêm trên crop `NEAR_CROP` 400 quanh nhân
    vật ở `size` 416 (tỉ lệ 1,04 = ảnh gốc) và 320 (0,8), so recall <= 150 px TRƯỚC/SAU khi gộp với lượt full,
    và **ms CPU thêm/lượt** (trung vị + p95, 1 luồng ONNX như máy game) → quy ra % một core ở 2 lượt/s.
(d) **Vùng chuyển động**: `motion_centroids` trên 2 frame liên tiếp, đếm số hover con trỏ KIẾM <= 150 px nằm
    trong một vùng chuyển động mà frame đó KHÔNG có box nào trong 48 px (= số quái mục này cứu được), và số
    vùng chuyển động không có kiếm (= rác: cây, nước, người khác).
CỔNG QUYẾT ĐỊNH: hướng nào trong (b)/(c)/(d) đưa recall 150 px lên gần 97% với ms thấp nhất thì làm trước;
hướng không chứng minh được lợi ích thì BỎ (bài học 0.43 B3: giả thuyết sai thì code thêm là nợ).

#### B1 — KẾT QUẢ ĐO VÒNG ĐẦU (27/11, input 640 — MỐC SAI, giữ để so sánh; xem bảng 416 bên dưới)
Hai nguồn sự thật, vì nhãn tay gần như không phủ vùng gần:
**(A) nhãn tay** — 092741, 162 frame, TOÀN ĐÊM, blessed_orc. **(B) hover con trỏ kiếm** — 092741 + 090350 +
101941, 443 frame, có cả ngày và fallen_blessed (hover gán cho frame gần nhất trong 1 s).

| nguồn | < 100 px | 100-200 px | > 200 px | box sai |
|---|---|---|---|---|
| (A) nhãn tay | 46/50 (92%) | 60/61 (98%) | 304/352 (86%) | 0,27/frame |
| (B) hover kiếm | 203/220 (92%) | 51/62 (82%) | 144/167 (86%) | (nhãn thưa, không đo được) |
| (B) ngày | 121/128 (95%) | 29/37 (78%) | 58/65 (89%) | |
| (B) đêm | 82/92 (89%) | 22/25 (88%) | 86/102 (84%) | |

recall trong 150 px, trước -> sau:

| cách | (A) nhãn tay | (B) hover kiếm | chi phí |
|---|---|---|---|
| hiện tại (full 640, conf bãi) | 94% | 90% | 65-70 ms/lượt |
| + conf 0,1 trên full frame | 96% | 92% | 0 ms, +0,01-0,03 box gần/frame |
| + crop 400 @ **416** | 99% | 92% | +28 ms (6% một core ở 2 lượt/s), +0,17 box/frame |
| + crop 400 @ **320** | 99% | **93%** | +21 ms (**4%** một core), +0,13 box/frame |
| **GỘP cả ba** | **99%** | **94%** | như trên |
| GỘP, riêng <= 100 px | 92% -> 98% | 92% -> 95% | |

(d) vùng chuyển động: hover kiếm <= 150 px KHÔNG có box = 70 ca, chỉ **28 (40%)** nằm trong một vùng chuyển
động; và **68% vùng chuyển động là rác** (1014/1493, ~3,4 vùng/frame).

KIỂM TRA LẠI PHÉP ĐO (quan trọng): thu hẹp cửa sổ gán hover từ 1 s xuống **0,3 s** (để quái không kịp đi xa)
cho ra gần như y nguyên: 91% -> gộp 94% (225 frame, 126 điểm gần). Vậy **6% sót còn lại là sót THẬT**, không
phải lỗi gán thời gian.

QUYẾT ĐỊNH (thay cho giả thuyết ban đầu):
1. **LÀM: crop 400 ở size 320** — không phải 416. 320 cho recall bằng hoặc hơn (93% vs 92%) và rẻ hơn
   (21 vs 28 ms). Ngân sách thực đo chỉ **4% một core**, nhỏ hơn nhiều so với ước tính 25% trong kế hoạch.
2. **LÀM: conf 0,1 cho vùng <= 150 px** — gần như miễn phí, +2 điểm recall, 0,02-0,03 box gần thêm/frame.
3. **BỎ: vùng chuyển động** (B2.2 phần motion) — chỉ phủ 40% ca sót và 68% là rác; với
   `max_probe_points` nó sẽ đẩy quái thật ra khỏi danh sách. `motion_centroids` vẫn để nguyên, không gọi.
4. **KHÔNG ĐẠT 97% bằng vision**: trần đo được là 94% (nguồn hover) / 99% (nhãn tay đêm). Phần sót còn lại
   tập trung ở vùng **<= 100 px, quái đè lên nhân vật** (220/251 điểm gần nằm trong 100 px). Hai thứ đóng
   được 6% đó: **vòng rê con trỏ (B2.3)** và **train lại từ hard case (mục 5/6)**. Vì vậy thứ tự làm giữ
   nguyên nhưng kỳ vọng đổi: B2.1 đưa 90% -> 94%, B2.3 + model mới mới tới 97%.
5. Tracker dự đoán (B2.2 phần tracker): dữ liệu này KHÔNG đo được (nó không sinh box mới, chỉ giữ lock) ->
   làm sau B2.3, chỉ nếu replay cho thấy còn mất lock.
GHI CHÚ ĐO: ms đo trên laptop (Python 3.14, CPU khác máy game) - chỉ tin TỈ LỆ so với lượt full (crop 320 =
~1/3 một lượt full); phải đo lại trên máy game trước khi đặt mặc định. Bảng (A) toàn đêm nên dòng "ngày" của
nhãn tay trống; dòng ngày/đêm của (B) là số dùng được. Bộ observe bốn mùa vẫn chưa có ảnh trên laptop.

#### B1 — KẾT QUẢ ĐO Ở ĐÚNG MỐC MÁY GAME: input **416** (27/11)
CẤU HÌNH THẬT lấy từ `meta.json` của các bản ghi mới nhất, KHÔNG dùng `records_game/game_pc_config.json`
(file đó 23-24/11, đã cũ và không có `input_size`): 20261127_101929_hunt và 20261126_225217_hunt + 101258 đều
ghi **`input_size` 416, `detect_roi` false, `max_probe_points` 2, conf 0,2, `detect_fps` 2,
`detect_threads` 1 / `search_threads` 2**. Mọi số dưới đây đo ở 416.
HAI LỖI PHÉP ĐO ĐÃ SỬA TRƯỚC KHI CHỐT:
1. vòng đo đầu chạy ở 640 (mốc sai) - ở 640 recall gần là 90-91%, ở 416 chỉ còn **85-86%**: chính cỡ input
   của máy game là một phần của vấn đề "quái gần bị sót";
2. `detect()` xoá HUD **theo tỉ lệ ảnh truyền vào**, nên truyền crop 400x400 vào nó sẽ xoá mất giữa vùng chơi.
   Bản sửa (`yolox_mobs.detect_near`) xoá HUD trên FULL frame rồi mới cắt; số của crop vì vậy tốt hơn vòng đo
   đầu nhiều.
Nguồn: (A) nhãn tay 092741 (162 frame, toàn đêm); (B) hover con trỏ kiếm trên **5 bản ghi** 092741 + 090350 +
101941 + 225217 + 101929 (**672 frame**, có ngày/đêm, blessed_orc + fallen_blessed).

| nguồn | < 100 px | 100-200 px | > 200 px | box sai |
|---|---|---|---|---|
| (A) nhãn tay | 40/50 (80%) | 56/61 (92%) | 244/352 (69%) | 0,15/frame |
| (B) hover kiếm | 261/305 (86%) | 90/109 (83%) | 207/277 (75%) | (nhãn thưa) |
| (B) ngày | 133/144 (**92%**) | 36/46 (78%) | 82/97 (85%) | |
| (B) đêm | 128/161 (**80%**) | 54/63 (86%) | 125/180 (69%) | |

recall trong 150 px:

| cách | (A) nhãn tay | (B) hover kiếm | chi phí |
|---|---|---|---|
| hiện tại (full 416) | 84% | 85% | 27-28 ms/lượt |
| + conf 0,1 full frame | 87% | 88% | 0 ms, +0,02-0,05 box/frame |
| + crop 400 @416 | 93% | 94% | +31 ms (6% một core ở 2 lượt/s) |
| + crop 400 @**320** | **99%** | **94%** | **+20 ms (4% một core)**, +0,19-0,28 box/frame |
| **GỘP cả ba** | **100%** | **95%** | như trên |
| GỘP, riêng <= 100 px | 80% -> **100%** | 86% -> **96%** | |

(e) **CẮT Ở `max_probe_points`**: trong 307 quái gần CÓ box, chỉ **7 (2%)** bị cắt khỏi danh sách rê ở mức 2
điểm, và ở mức 5 điểm là **0** -> nâng 2 lên 5 cứu được **7 ca** (nhãn tay: 0/71 bị cắt). Vậy việc cắt
KHÔNG phải nguyên nhân chính, nhưng nâng lên 5 là gần như miễn phí (mỗi điểm rê ~0,2 s) và nên làm trên máy
game. Lưu ý: thứ tự ở đây tính gần-trước, chưa tính kiểu sắp xếp "cùng phía hàng rào" của minimap (chỉ ảnh
hưởng box ngoài `NEAR_KEEP`).
(d) vùng chuyển động: 144 ca hover kiếm <= 150 px không có box, chỉ **62 (43%)** nằm trong vùng chuyển động;
**69% vùng chuyển động là rác** (1527/2207) -> GIỮ QUYẾT ĐỊNH BỎ.

KẾT LUẬN SAU KHI ĐO ĐÚNG MỐC:
1. **crop 400 @320 là thắng lớn, không phải nhỏ**: +9 điểm recall gần (85% -> 94%) và vùng <= 100 px
   86% -> 96% (nhãn tay 80% -> 100%), chỉ +20 ms (~70% chi phí một lượt full 416, = 4% một core ở 2 lượt/s).
   320 TỐT HƠN 416 ở cả hai nguồn và rẻ hơn -> `NEAR_SIZE` 320.
2. conf 0,1 giữ (+3 điểm, gần như miễn phí).
3. Mục tiêu 97% vẫn chưa đạt theo nguồn hover (95%), nhưng vùng <= 100 px đã 96% và nhãn tay 100%.
   Phần còn lại là ban ĐÊM (<=100 px chỉ 80% trước khi sửa) -> vòng rê con trỏ (B2.3) + train lại từ
   hard case vẫn cần, và `tests/eval_near_recall.py` là thước đo để nghiệm thu.
4. Máy game nên đổi `max_probe_points` 2 -> 5 (cứu 7/307 ca, không đổi code).

#### B2.1 DETECT VÙNG GẦN Ở ĐỘ PHÂN GIẢI GỐC
Mỗi lượt quét, sau lượt full, thêm MỘT lượt detect trên crop 400x400 quanh nhân vật (dùng `roi_box` với
nửa-cạnh cố định, kẹp vào vùng chơi), `conf = scan.near_conf` 0,1, `size` theo kết quả B1(c). Gộp box với
lượt full (dedupe `MOTION_DEDUPE` 18 px) và **gắn cờ nguồn**:
- box chỉ do lượt gần + conf thấp sinh ra CHỈ được làm ứng viên rê (vẫn phải con trỏ kiếm mới đánh), KHÔNG vào
  `mobs_near` / `mobs_seen` / `closer_than` / `_update_tracks` — nếu không sẽ thổi phồng "đám quái" của luật
  danger 0.40 và luật tường/unreachable 0.40-0.42 (cái bẫy đã mắc ở 0.43);
- **thứ tự khi cắt theo `scan.max_probe_points`: box conf thường TRƯỚC, box `near_conf` sau** (trong mỗi nhóm
  vẫn gần-trước). Máy game đang đặt `max_probe_points` = 2, nên thứ tự này là bắt buộc, không phải tuỳ chọn.
Làm trong `runtime/detector._run` (một lượt `detect` nữa trong cùng vòng, CÙNG frame — không grab thêm), kết
quả đi theo `Detection.near`. Guard CPU hiện có (`detector.CPU_SHARE` 30%, `_slow_down`) phải tính cả ms của
lượt gần, nếu không nó sẽ tự hạ fps lượt full và ăn mất kill (vết xe 0.33/0.34).
Các bậc lùi nếu vượt ngân sách (thử theo thứ tự): (a) 400@416 mỗi lượt; (b) 400@320; (c) chỉ khi ĐANG ĐÁNH /
HP tụt / đứng > 2 s không mục tiêu; (d) xen kẽ mỗi lượt thứ hai. Bản đồ không có export 416/320
(dragon_valley, fallen_spirit, toi, game): crop 400 bị phóng lên 640 = vô ích → tắt B2.1 cho các bản đồ đó
tới khi `train/export_onnx.py --size 416` chạy cho chúng.

#### B2.2 TRACKER CÓ DỰ ĐOÁN + VÙNG CHUYỂN ĐỘNG
- `_update_tracks` giữ `[x, y, vx, vy, misses]`: vị trí dự đoán = vị trí cuối + vận tốc (trung bình 2 lần khớp
  gần nhất) x thời gian trôi; vẫn khớp box gần nhất trong `TRACK_MATCH_PX`, vẫn xoá sau `TRACK_MISSES`. Dùng
  cho `track_current`; `lock_live` vẫn chỉ True khi có box THẬT — điểm dự đoán không bao giờ là
  "tiến triển"/"cận chiến" (learning 27/11: cho nó tính đã làm một trận ở 82 px chết oan). Cộng dồn dịch
  chuyển màn hình của 1.7 (`ctx.offset()`) để điểm nhớ đi theo nhân vật khi nhân vật bước.
- Nối lại `motion_centroids(prev, curr, char, radius=150)` trong `targeting.candidates`: vùng chuyển động
  trong 150 px mà không có box nào trong 48 px → thêm vào danh sách rê thử, đứng SAU box conf thường và box
  near_conf (thứ tự cuối cùng theo tỉ lệ "ra kiếm" đo ở B1(b)/(d)). Chỉ dùng 2 frame đã có trong detector.

#### B2.3 VÒNG RÊ CON TRỎ (`features/ring_probe.py`, ~40 dòng)
8 hướng x 2 bán kính (45, 90 px) = 16 điểm trong vùng chơi; quét như `grid_scan.sweep` (1 lần đọc con trỏ/
điểm, ~0,8 s cả vòng — `probe` 4 lần đọc sẽ là ~3 s, quá chậm khi đang bị đánh), dừng ở điểm đầu ra con trỏ
kiếm rồi **xác nhận lại bằng `targeting.probe([p])`** mới đánh. Nhả chuột trái trước, `poll_escape` trong
vòng. `RING_COOLDOWN` 2 s dùng chung cho mọi nguồn kích hoạt.
Kích hoạt: (a) HP tụt (`hp_falling`, luật danger hiện có) mà không có box <= 100 px — đặt trong
`session._defend`, nơi hiện trả None khi không có box <= `DEFEND_PX` 70; (b) không có mục tiêu >
`RING_IDLE_SEC` 5 s (kể cả chế độ đứng gốc `targeting.in_place()`), đặt trước nhánh `grid.sweep` / `wander`.
Gặp quái: lớp cận chiến → `combat.engage(target, rect, char, force_melee=True)`; pháp sư/tiên →
`engage_ranged` (bắn phép vào đúng điểm đó). KHÔNG nhét điểm rê vào `targeting.tracked`.
**Trận sinh từ vòng rê KHÔNG tắt theo `BOX_GONE_SEC`** (quái này vốn không có box — tắt theo box là tự thua):
nó sống bằng CON TRỎ. Mỗi `RING_HOLD_CHECK` 0,5 s đọc lại con trỏ tại điểm khoá (`rehover_last`, đã có); còn
kiếm thì giữ trận, **hết kiếm 2 lần LIÊN TIẾP** hoặc chạm `scan.melee_max_sec` thì kết thúc (outcome mới
`ring_gone` / `cap`). Cờ `ring_fight` trên `CombatFeature` bỏ qua đúng hai luật box (`BOX_GONE_SEC`,
`NO_SWORD_SEC`), các luật khác (danger, chết, kill line, ESC) giữ nguyên. Lưu ý rủi ro đã biết: con trỏ cũ
không chứng minh có quái (learning 25/11), nên hai lần đọc liên tiếp + cap là điều kiện tắt duy nhất, và
mọi trận kiểu này đều sinh hard case để kiểm lại bằng mắt.
Nếu B2.1 đạt 97% thì B2.3 gần như không bao giờ chạy — đó là dấu hiệu TỐT, không phải lỗi.

#### 5. HARD CASES — BẬT NGAY, ĐỘC LẬP VỚI TUỲ CHỌN GHI HÌNH (chỉ ghi dữ liệu)
Bằng chứng có quái mà model không có box trong 48 px — con trỏ KIẾM (mọi nguồn: `probe`, `_defend`, vòng rê,
`rehover_last`) hoặc một dòng chat kill ở ô khoá — thì lưu một hard case.
- **Một thư mục duy nhất `records/hard_cases/`**, KHÔNG nằm trong `records/<stamp>/`: nó phải chạy cả khi
  người dùng tắt ghi hình, và một chỗ duy nhất thì chỉ có một hạn mức, một nút xuất, một file nhãn.
  `runtime/hard_cases.py` (~60 dòng, `HardCases.save(frame, point, kind, src, map_key, night)`), tạo trong
  `session.start` **không phụ thuộc `record.enabled`**, dùng `records_root()` đã có. Ảnh ghi bằng
  `cv2.imwrite` JPEG (dùng lại `save_snapshot` với `root=records_root()`), tên `hc_<stamp>_<n>.jpg`.
- **Hạn mức: 500 ảnh HOẶC 200 MB, cũ nhất xoá trước** (`HARD_CASE_MAX_N` 500, `HARD_CASE_MAX_MB` 200), kiểm
  sau mỗi lần lưu bằng `os.scandir` + `st_mtime`; xoá ảnh thì xoá luôn dòng nhãn của nó. KHÔNG tính vào
  `record.max_gb` (độc lập với ghi hình), nhưng nêu trong UI cho người dùng biết nó chiếm tối đa 200 MB.
  Chống trùng: bỏ qua nếu đã lưu một hard case trong `HARD_CASE_GAP` 2 s ở cùng điểm (<= 48 px).
- **Nhãn YOLO kèm theo, box ước lượng cỡ orc quanh điểm con trỏ**: một `.txt` cùng tên ảnh, định dạng YOLO
  (`0 xc/w yc/h bw/w bh/h`), box `HC_BOX` **57x95 px** (trung vị 3100 box nhãn tay của các bản ghi hiện có;
  giữ là hằng số một chỗ, ghi rõ "ước lượng, phải duyệt tay"), kẹp vào biên ảnh. Kèm `hard_cases.jsonl`
  (`t`, `point`, `kind`, `src`, `dist`, `map`, `night`, `file`) và `labels.json` đúng định dạng của
  `tests/label_tool.py` (`{"images": {"hc_….jpg": {"night":…, "map":…, "monster": [[x, y]],
  "boxes": [box ước lượng], "ignore": [], "todo": true}}}` — `todo: true` vì box chưa ai duyệt).
  Hai file nhãn vì hai người dùng khác nhau: `.txt` cho `train/`, `labels.json` cho công cụ duyệt.
- Event + `rec.count` `hard_case` khi đang ghi hình (để `analyze_records.py` in ra), nhưng việc LƯU không
  phụ thuộc vào recorder.

#### 6. ĐƯỜNG DỮ LIỆU: XUẤT → DUYỆT → TRAIN → SO SÁNH
a) **Tab Dữ liệu, nút "Xuất dữ liệu học"** (`ui/panels/record_panel.py`, cạnh nút zip hiện có — dùng lại
   `_zip_latest` làm mẫu, cùng kiểu chạy nền + `set_busy`): zip toàn bộ `records/hard_cases/` thành
   `records/hard_cases_<stamp>.zip` kèm `stats.json` + một `README.txt` một dòng. Thống kê in trên UI và nằm
   trong zip: **số ảnh, theo bãi (`map`), ngày/đêm**, khoảng thời gian, số ảnh đã duyệt / còn `todo`.
   Chuỗi i18n mới ở `ui/i18n.py` cho cả ko/en/vi.
b) **Công cụ duyệt mở thẳng zip**: `tests/label_tool.py <file.zip>` — giải nén vào thư mục tạm rồi chạy
   `run()` như thường (dùng lại đúng 3 dòng `zipfile.ZipFile(arg).extractall(out)` của
   `tests/analyze_records.py:77`), và lưu `labels.json` trở lại CẠNH zip (`<zip>.labels.json`) để không mất
   khi thư mục tạm bị xoá. Box ước lượng đã có trong `labels.json` nên nó **hiện sẵn để chỉnh** — không cần
   code vẽ mới, `label_tool` đã biết vẽ/sửa/xoá box; chỉ thêm phím "chấp nhận box này" nếu B1 cho thấy phải
   duyệt hàng trăm ảnh (chưa làm nếu `--review` đủ dùng).
c) **Train + SO SÁNH TRÊN BỘ TEST CỐ ĐỊNH**: `train/compare_models.py <model_cũ> <model_mới>` —
   bộ test cố định = `tests/data/monster_labels.json` + `docs/game_reference` + các frame đã nhãn tay của
   092741 (và các bản ghi nhãn thêm ở B1), **không bao giờ gồm ảnh hard_cases đã dùng để train**.
   In bảng: recall toàn màn, **recall <= 150 px**, precision (box sai/frame), ms/lượt, ở đúng input máy game
   (`--config`). **Chỉ in "ĐỀ XUẤT THAY" khi recall gần TĂNG và precision KHÔNG giảm** (và ms không tăng quá
   20%); mọi trường hợp khác in "GIỮ model cũ" kèm lý do. Dùng lại `tests/eval_detection.evaluate` +
   `tests/eval_near_recall.py` (gọi hàm, không copy) — đây là luật PLAN 0.39 viết thành script, nên không ai
   bless model bằng cảm giác nữa.
d) **Tab Thống kê: `hard_case/giờ`** — `Stats.bump(ctx, "hard_case")` ở chỗ lưu, rồi một dòng trong
   `Statistics` panel: `hard_case` và `hard_case/giờ` = đếm / `Stats.runtime_sec()` (panel đã có cách tính
   theo giờ cho các bộ đếm khác). Con số này là thước đo chính của 0.46: nó phải GIẢM sau B2.1/B2.2.

#### B2 — ĐÃ CODE (27/11), chưa build
**B2.1 crop vùng gần** [XONG]: `yolox_mobs.detect_near()` + `near_crop_box()` (crop `NEAR_CROP` 400 quanh
nhân vật, `NEAR_SIZE` 320, bán kính `NEAR_R` 150). **XOÁ HUD TRÊN FULL FRAME RỒI MỚI CẮT** — `_blank_play_hud`
làm việc theo TỈ LỆ ảnh nó nhận, nên cắt trước rồi xoá sau sẽ xoá mất giữa vùng chơi (đây chính là lỗi đã làm
sai vòng đo đầu, xem B1); `detect(..., blank=False)` là tham số mới cho đúng việc đó. Bản đồ không có export
320 thì lượt gần TẮT (nếu không `ensure_session` sẽ lùi về 640 = tốn cả một lượt detect mà không lợi gì).
Chạy trong `detector._run` trên CÙNG frame (không grab thêm), đi theo `Detection.near`; ms của nó **cộng vào
ngân sách của mode** nên guard `CPU_SHARE` thấy đúng chi phí, và log riêng `near_ms` / `near_boxes_per_frame`
+ `near_size` trong `detect_stats` (để đo thật trên máy game sau khi build).
`targeting._detect` nhận `found.near` -> `self.last_near`; `candidates()` nối chúng vào SAU box thật
(`(unique + extras)[:max_probe_points]`), và `last_monsters` được gán TRƯỚC khi nối, nên `closer_than`,
`mobs_near`, `mobs_seen`, `_update_tracks` chỉ thấy box thật (luật danger 0.40 và luật tường 0.40/0.42 không
bị box conf thấp làm nhiễu). Cấu hình `scan.near_conf` 0,1 (0 = tắt) + một ô trong tab Quét (`scan_near_conf`).
**B2.3 vòng rê** [XONG]: `features/ring_probe.py` (`ring_points` 8 hướng x 45/90 px = 16 điểm; quét 1 lần đọc
con trỏ/điểm rồi xác nhận lại điểm đầu bằng `targeting.probe`; `COOLDOWN` 2 s; nhả chuột trái trước;
`poll_escape` trong vòng). Kích hoạt: `session._defend` khi HP tụt mà không có box <= `RING_DEFEND_PX` 100,
và `RING_IDLE_SEC` 5 s không có mục tiêu (kể cả đứng gốc). Trận sinh từ vòng rê: `combat.engage(..., ring=True)`
/ `engage_ranged(..., ring=True)` **không tắt theo `BOX_GONE_SEC` / `NO_SWORD_SEC`**; cứ `RING_CHECK_SEC` 0,5 s
đọc lại con trỏ (lớp cận chiến đọc con trỏ đang giữ chuột, lớp bắn xa `rehover_last`), hết kiếm
`RING_CHECK_STRIKES` 2 lần liên tiếp hoặc chạm cap thì kết thúc, outcome mới `ring_gone`.
**Mục 5 hard cases** [XONG]: `runtime/hard_cases.py` (`HardCases`, `stats()`, `export_zip()`) ghi vào
`records/hard_cases/`, tạo trong `BotContext.__init__` nên **độc lập hoàn toàn với tuỳ chọn ghi hình**.
`ctx.hard_case(rect, point, kind, src)` bỏ qua điểm nào có box thật trong 48 px (`mobs_seen`), chống trùng
2 s / 48 px, không bao giờ raise vào vòng săn. Mỗi ca: `.jpg` + `.txt` YOLO (box ước lượng `HC_BOX` 57x95,
kẹp biên) + `hard_cases.jsonl` + `labels.json` (`todo: true`) cho `tests/label_tool.py`. Hạn mức
`MAX_N` 500 / `MAX_MB` 200, cũ nhất xoá trước, xoá ảnh thì xoá cả `.txt` và dòng nhãn. Gọi từ 3 chỗ:
`targeting.probe` (ra kiếm), `combat` (dòng chat kill khi không có box sống), `ring_probe` (vòng rê tìm được).
**Mục 6 đường dữ liệu** [XONG]: nút "Xuất dữ liệu học" trong tab Dữ liệu (`record_panel._export_hard` →
`hard_cases.export_zip`, kèm `stats.json` và dòng tóm tắt số ảnh / MB / theo bãi / ngày-đêm / chưa duyệt;
chuỗi `hard_export`, `hard_none`, `hard_stats` đủ ko/en/vi). `tests/label_tool.py <file.zip>` mở thẳng zip
(giải nén như `analyze_records.py`) và lưu nhãn **cạnh zip** (`<zip>.labels.json`) để thư mục tạm bị xoá không
mất công duyệt; box ước lượng đã nằm trong `labels.json` nên hiện sẵn để chỉnh. `train/compare_models.py`
so model cũ/mới trên bộ test cố định (`monster_labels.json` + `docs/game_reference` + frame nhãn tay của
092741) và chỉ in "ĐỀ XUẤT THAY" khi recall gần TĂNG, box sai KHÔNG tăng và ms không tăng quá
`MS_TOLERANCE` 1,2 lần. Tab Thống kê: `hard_case` (kèm `/h`), `ring_probe`, `ring_hit` trong `stats.KEYS`.
**B2.2** [BỎ phần chuyển động như B1 đã kết luận; phần tracker dự đoán CHƯA làm, để sau].
VIỆC TRÊN MÁY GAME (không cần code): đổi `scan.max_probe_points` 2 -> 5 (B1(e): cứu 7/307 ca quái gần có box
nhưng bị cắt khỏi danh sách rê).
TEST: `python tests/test_near_blind.py` (55 kiểm tra: hình học vòng rê + cooldown + xác nhận lại + hard case
của vòng rê; luật trận vòng rê; nhãn YOLO/labels.json/hạn mức/xoá cũ nhất/thống kê/zip; `ctx.hard_case` bỏ
điểm model đã thấy; hình học crop + thứ tự xoá HUD; box gần không vào luật danger; `near_conf`; `detect_stats`
có ms crop; luật "ĐỀ XUẤT THAY" của compare_models). Hồi quy đã chạy lại: `tests/smoke_test.py` PASS,
`tests/test_in_place_101929.py` PASS (41 trận / 55 spell_cast như trước), `tests/test_ui.py` PASS.

SỐ REPLAY SAU B2.1/B2.3 (27/11, `tests/test_hunt_records.py`, so với mốc 0.43 ghi ở trên):
092741: 87 trận (87), **kill 8 (8)**, gone 27 (28), lost 14 (15), unreachable 17 (17), blacklist 17 (17),
dòng chat kill 21 (21), cap 0, trận dài nhất 9,8 s;
101941: 75 trận (75), **kill 2 (2)**, gone 12 (13), unreachable 9% (9%), wall 2 (2), phép 23 (23),
"đứng im" 70 phép (70), idle sau 166,9 s (166,9). => lượt crop vùng gần + conf 0,1 KHÔNG làm giảm kill và
không làm tăng unreachable/wall; `max_probe_points` 2 không bị box conf thấp chiếm chỗ trong các bản ghi này.
(Replay chạy đường `targeting._detect` nội tuyến nên nó CÓ gọi `detect_near`.)

#### B3 (0.46) — INPUT 416 HAY 640 CHO LỚP BẮN XA: PHẢI THỬ TRÊN MÁY GAME
Số B1 cho thấy một việc chưa ai tính: ở input **416** recall quái **> 200 px chỉ 69-75%** (nhãn tay 69%,
hover kiếm 75%), còn ở **640** là **~86%**. Mà **pháp sư / tiên đứng gốc bắn chủ yếu ở 200-350 px**
(`targeting.IN_PLACE_SHOT_PX` 350), tức đúng dải mà 416 nhìn kém nhất - crop vùng gần (<= 150 px) KHÔNG cứu
được dải này.
VIỆC SAU KHI BUILD (trên máy game, cùng bãi, cùng giờ, mỗi lượt >= 20 phút):
1. lượt A: `scan.input_size` 416 (hiện tại) + crop gần 320;
2. lượt B: `scan.input_size` 640 + crop gần 320;
so **kill/giờ**, **lag của client** (cảm nhận của người dùng + `detect_stats.cpu_pct`), `detect_ms` và
`boxes_per_frame` của cả hai (log một dòng/phút đã có sẵn: `[detect] ... | process cpu ...`).
Chọn mặc định theo class: nếu 640 cho kill cao hơn mà không lag thì lớp bắn xa nên mặc định 640 (cận chiến
vẫn 416 vì nó chỉ cần quái trong ~70 px). Nhớ: 640 nặng ~2,4 lần 416 (27 ms -> 65-70 ms đo trên laptop), và
guard `CPU_SHARE` 30% có thể tự hạ fps - đọc `detect_stats.duty` để biết nó có hạ hay không.
**Bổ sung 27/11 (1.9, tiên bắn cung 10–25 bước):** tiên giờ đánh thường bằng cung tới `attack_range` 15 bước (mặc
định), tức phần lớn quái nó đánh nằm ở **> 200 px** (191624: quái 300–550 px = 13–23 bước). Tiên vì vậy phụ thuộc
hẳn vào recall > 200 px: 416 thấy 69–75%, 640 thấy ~86%. ĐỀ XUẤT: mặc định `scan.input_size` 640 cho ELF nếu CPU
máy game cho phép. Quyết định nằm trong chính phép thử A/B ở trên, chạy bằng nhân vật tiên: lượt 416 và lượt 640,
cùng `attack_range`, so kill/giờ + `ms_total` + cpu_pct. Chưa đổi mặc định trong code.
RỦI RO: PLAN 0.32/0.39 đã chốt "full frame 640" rồi lại bị máy game đổi về 416 bằng tay; đừng đổi mặc định
trong code trước khi có số của hai lượt này.

#### TEST / NGHIỆM THU
- `python tests/eval_near_recall.py` (bảng B1, trước/sau B2.1 và B2.2; cổng: 150 px >= 97%).
- `python tests/eval_detect_modes.py` (+ chế độ `near400@416`): ms/lượt, box/frame, % một core.
- `python tests/test_near_blind.py`: vòng rê bị chặn đúng 2 s, không chạy khi đang có mục tiêu, mỗi
  "ra kiếm mà không có box" sinh 1 hard case đúng định dạng nhãn; trận vòng rê sống qua `BOX_GONE_SEC` và
  tắt sau 2 lần đọc con trỏ không kiếm; tracker dự đoán không được tính là tiến triển.
- `python tests/test_hard_cases.py` (mục 5/6): lưu khi recorder = None (ghi hình tắt); hạn mức 500 ảnh /
  200 MB xoá cũ nhất trước và xoá cả dòng nhãn; `.txt` YOLO đúng toạ độ chuẩn hoá với box 57x95 kẹp biên;
  chống trùng 2 s; `labels.json` mở được bằng `label_tool` (gọi `load_labels`); zip xuất ra có `stats.json`
  đúng số ảnh/bãi/ngày-đêm; `label_tool.py <zip>` mở được và lưu nhãn cạnh zip;
  `train/compare_models.py` chỉ in "ĐỀ XUẤT THAY" ở đúng điều kiện (test với số giả: recall gần tăng +
  precision giảm -> GIỮ).
- Chạy lại `tests/test_hunt_records.py`, `tests/test_in_place_101929.py`, `tests/eval_detection.py`:
  kill / gone / unreachable không xấu đi, `mobs_near` không tăng (luật danger), CPU <= +30%.
- CHƯA BUILD (bản phát hành phải dựng trên máy 3.12).

#### RỦI RO PHẢI BIẾT
1. **`scan.max_probe_points` = 2 trên máy game**: B2.1/B2.2 sinh thêm ứng viên; với hạn mức 2, một box conf
   thấp / điểm chuyển động sai chiếm chỗ quái thật → thứ tự conf-thường-trước là bắt buộc, và nên nâng hạn
   mức riêng cho vùng <= 150 px (rê gần rất rẻ: ~0,2 s).
2. **Ngân sách CPU**: B2.1 một mình ước ~25% một core ở 2 lượt/s (416); ms của nó phải vào guard `CPU_SHARE`,
   nếu không guard sẽ hạ fps lượt full và làm giảm kill (vết xe 0.33/0.34).
3. **Conf 0,1 sinh box sai**: chi phí một lần rê (~0,2 s) mỗi box; tuyệt đối không cho vào luật danger/tường.
4. **Nhãn ngày/đêm chưa đo được trên laptop này** (xem B1(a)) — đừng kết luận "đêm sót nhiều hơn" trước khi có
   ảnh các bản ghi observe.
5. **Trận vòng rê sống bằng con trỏ**: nếu quái thật đã chết mà con trỏ còn kiếm (xác/người khác), trận có thể
   kéo tới 1 s nữa; chấp nhận, nhưng đừng nới điều kiện tắt quá 2 lần đọc.
6. **Hard case ăn đĩa và CPU nhỏ nhưng không bằng 0**: mỗi lần lưu là 1 JPEG ~150 KB + 2 lần ghi file; hạn
   mức 500 ảnh/200 MB là tối đa ~75 MB-200 MB. Nếu model sót nhiều, hard case sẽ đầy trong một buổi -> cũ nhất
   bị xoá, tức bộ dữ liệu luôn là "những ca mới nhất" chứ không phải mẫu đại diện. Chấp nhận, nhưng khi train
   phải xuất zip TRƯỚC khi hạn mức xoá (nút ở tab Dữ liệu).
7. **Box ước lượng 57x95 là ước lượng**: không được train trực tiếp từ nó mà chưa duyệt tay, nếu không model
   sẽ học lệch cỡ box. `todo: true` và `compare_models.py` trên bộ test cố định là hai cái chốt.

### 0.47 v21rc6 TRÊN MÁY GAME (20261127_191624_hunt, wizard, 오크의 땅, hunt_range 10, pull_mode) — NGUYÊN NHÂN  [SỬA 27/11]
Số liệu 95 s: 30 spell_cast (ok), 0 kill, 25 fight_end = 11 danger + 7 cap + 6 gone + 1 stopped.

**A. near_ms "None"**: KHÔNG phải không ghi. detect_stats ghi near_ms / near_boxes_per_frame BÊN TRONG khối
`search` / `fight` (search 87 ms 4,4 box, fight 78 ms 3,4 box), ở cấp ngoài cùng thì không có. `tests/analyze_records.py`
không in hai trường này -> trông như None. Sửa: analyze_records in near_ms / near_boxes / "full ms = ms - near_ms".

**B. Lượt full "chậm gấp đôi"**: `ms` trong detect_stats = full + near (detector.py:204 cộng near_ms vào để guard
CPU thấy). Trừ near ra: search 195-87 = 108 (rc5 101929: 76-112, TB 87), fight 183-78 = 105 (rc5: 97-98). Tức lượt
full KHÔNG chậm lên; toàn bộ phần thêm là crop gần.
- Crop chạy MỌI lượt, cả search lẫn fight (`self.near` bật khi near_conf > 0, không giới hạn tần suất). Commit 0.46
  ước +20 ms (đo trên laptop); trên máy game là +78-87 ms/lượt.
- Guard CPU_SHARE CÓ chạy: fight duty 0,35 > 0,30 -> fight 2/s -> 1/s (max_fps 1 ở log phút 2). Search giữ sàn 2/s.
  Guard chỉ hạ fps; không tắt hay giãn crop.
- Thread: search 2, fight 1; crop dùng cùng số thread của lượt đó. CPU tiến trình 50% (rc5) -> 67% (rc6).
- Mục tiêu <= rc5 + 20%: search <= 104 ms, fight <= 118 ms (đo ms full+near trung bình/lượt).
  "1 lần/s" KHÔNG đủ: fight 2/s -> 98 + 78/2 = 137 ms (+40%).
  ĐÃ LÀM (người dùng chốt): crop gần CHỈ trong trận, tối đa 1 lần / 2 s (`detector.NEAR_EVERY_SEC` 2,0) -> fight
  ~98 + 20 = 118 ms; search không crop (87 ms); NGOẠI LỆ: HP đang tụt (`state["hp_falling"]` = danger hoặc
  hp_falling, do survival ghi) -> crop ngay lượt kế, cả khi search. detect_stats: `ms` = full, `near_runs` /
  `near_ms` (mỗi lần crop chạy) / `ms_total` (full+near trung bình mỗi lượt); guard tính full + near.
  analyze_records in "near crop ... full ... full+near" (hiểu cả số kiểu rc6). CẦN ĐO trên máy game:
  search <= 104, fight <= 118 ms (ms_total).

**C. max_probe_points nhập 5 vẫn là 2** (SỬA: MAX_PROBE_POINTS = 6): `config/models.py:212 MAX_PROBE_POINTS = 2` (từ v14, PLAN 0.31) chặn ở
  3 chỗ: spinbox `to=` (ttk vẫn cho gõ 5), `ScanPanel.store` kẹp về [1, 2], và lúc đọc config cũng kẹp. Lưu thì CÓ lưu
  nhưng lưu số 2. Ghi chú trong commit 0.46 "nâng 2 -> 5 không cần code" là SAI. Sửa: MAX_PROBE_POINTS = 6.

**D. 30 phép, 0 kill, 11 danger**:
- Phép TRÚNG: hiệu ứng xanh trên orc (f_00012), MP giảm 1%/phát (spell_mp), thanh máu orc tụt từng ít. Một lần
  "마법 사용: 실패" lúc t=4 (spell_fail_chat).
- Kill line đọc được: chat chạy bình thường (f_00048 có "회복의 기운이 느껴집니다"), chỉ là không orc nào chết.
- NGUYÊN NHÂN 0 kill: hunt_range 10 + wizard -> `targeting.in_place()` = True (PLAN 1.7) -> `engage_ranged`: CHỈ
  bắn phép, không bao giờ đánh thường. Energy Bolt mỗi ~3 s (skipped cooldown 5-8/trận) không giết nổi orc trong
  cap 10 s; orc đứng cách 37-97 px (melee: false ở MỌI trận) mà bot không đánh. -> Phần 1.9 dưới đây.
- 11 danger = MỘT lần nguy hiểm thật: HP 194 -> 178 -> 149 -> 111 (57%) trong ~5 s, vài orc đánh cùng lúc
  (f_00043/46). Cờ danger giữ DANGER_HOLD 3 s nên mỗi lần acquire trong 3 s đó kết thúc ngay sau 0,1 s
  (combat.py:567), vậy là 1 lần bị đếm thành 11. Ở 57% bot hồi (F1, f_00046 -> 140/194 ở f_00048) và lùi một
  bước, đúng luật 0.40. Ngưỡng không quá nhạy. ĐÃ SỬA: session._run không chọn mục tiêu khi cờ còn giữ (health vẫn
  hồi/lùi), survival ghi MỘT event `danger {hp, drop, mobs}` mỗi đợt.

### 1.9 ĐÁNH THƯỜNG LÀ CHÍNH, PHÉP LÀ PHỤ (mọi class; khách yêu cầu 27/11 vì MP có hạn)  [CODE XONG 27/11, CHỜ MÁY GAME]
ĐÃ LÀM (khác kế hoạch dưới đây ở mấy điểm, ghi rõ):
- Bước trên màn hình: `vision/drift.py`. Đo trên 192615 (10 click = 20 bước): mỗi bước theo trục đi = (20, 10) px ở
  1280 -> số bước giữa hai điểm = |dx|/40 + |dy|/20 (ô isometric, ô chéo tính 1 bước). Độ trôi = phaseCorrelate trên
  vùng chơi thu nửa (~3 ms): 192615 cộng ra 20,1 bước, frame đứng < 0,1. Không thêm `screen_step_px` vào config
  (ctx.step_px 23 px đã có và khớp 22,4 đo được).
- `scan.attack_range` (0 = theo class: `CharacterClass.attack_range`, wizard/knight/prince 1, elf 9),
  `scan.spell_min_mp_pct` 70; tab Săn khối cơ bản + nút "Đo tầm đánh" (`features/range_probe.py`, huỷ bằng bấm lại).
  Tầm 1 = luật MELEE_DIST 70 px cũ; > 1 = số bước isometric + 0,5.
- "Có đánh" khi đo = điều kiện yếu (không trôi + con trỏ kiếm + box còn sau 1,5 s); thanh máu quái CHƯA đọc.
- Luật phép `combat._spell_why`: danger | crowd (>= 3 trong MELEE_DIST, mọi bãi) | out_of_reach | mp_high (MP >=
  70) | mp_unread (MP không đọc được thì không chặn); không thoả -> skipped `hand_first`. Áp cho engage (lớp đi) lẫn
  engage_ranged (đứng gốc). Ô phép vẫn giữ min_mp / range / cooldown / dự trữ hồi máu.
- engage_ranged (wizard/elf có hunt_range): quái trong tầm tay -> hold+drag tại chỗ, theo box; mỗi 0,8 s so độ trôi,
  > 1 bước -> nhả, blacklist, event `range_walk`, outcome `range_walk`. Ngoài tầm tay: chỉ phép, không click.
  out_of_range cho lớp đứng gốc = ngoài tầm phép VÀ ngoài tầm tay.
- Event `melee_attack {dist, target, steps}` mỗi trận một lần (kết quả nằm ở fight_end), `spell_cast.why`.
- Test: tests/test_attack_range.py. test_hunt_records.check_in_place_101941 đổi theo 1.9: trước "không bao giờ giữ
  chuột", giờ "chỉ giữ chuột trên quái trong tầm tay" (101941: 29 lần đánh tay, tất cả <= MELEE_DIST; 0 click không elip).
- TEST CHẬM (27/11): test_hunt_records 50+ phút trên PC là do Windows dồn tiến trình test chạy nền sang 4 NHÂN E của
  i5-14400F sau 2–3 s (một detect 640: 48 -> 125 ms; 1 luồng 140 -> 370 ms), không phải do code 1.9 (A/B code cũ chậm
  y hệt). `test_hunt_records.pin_fast_cores()` (GetSystemCpuSetInformation, chỉ khi CPU lai) khoá test vào nhân P:
  183803 519 -> 192 s, cả bài ~24 phút khi chạy song song với test_near_miss (~15 phút). Hai bài dài in "-- <bản ghi>
  ... / done in N s" để biết còn sống. GỢI Ý cho bot trên máy game: nếu CPU máy game cũng là loại lai, luồng detect có
  thể bị đẩy sang nhân E như vậy (fight 98 ms) - nên kiểm tra trước khi tối ưu thêm.
- analyze_records in "hand attacks N : spells M (why ...), range_walk K".
- BỔ SUNG (khách 27/11): tiên cầm cung bắn ~80% màn hình = 10–25 bước. `scan.attack_range` UI 1–25 ("Tầm đánh (bước)");
  config lưu 0 khi người dùng để nguyên mặc định class (knight 1, wizard 1, ELF 15), ô hiển thị giá trị bot dùng; nút
  "Đo tầm đánh" điền vào ô. Bước -> px: ô isometric đo trên 192615 (một bước theo trục đi = (20,10) px, 10 click =
  20,1 bước đo được). 25 bước so với vùng chơi (không minimap / HUD / cột icon, nhân vật ở (640,380) trên 1280x960):
  10 bước phủ 30%, 15 bước 62%, 25 bước 98%; góc xa nhất 29,6 bước. Quái thật 300–550 px của 191624: tầm 15 với
  tới 27/61, tầm 25 với tới 59/61 (2 con sát góc màn hình, 26,3–26,6 bước). Ngoài tầm: không click (lớp đứng gốc).
  Test: test_attack_range.test_elf_far_boxes (tầm 15 và 25: trong tầm = giữ chuột tại chỗ, không click; ngoài tầm
  = không click gì).
- RỦI RO còn để nguyên (có từ 0.44): lớp đứng gốc KHÔNG có phép thì quái < 350 px nhưng ngoài tầm tay vẫn là ứng viên,
  mỗi nhịp kết thúc `no_spell` ngay (không click, chỉ tốn nhịp + log).
- CHƯA LÀM: cảnh báo "attack_range quá lớn" sau 2 range_walk liên tiếp.
Thay luật 1.7 "caster/cung có hunt_range thì chỉ bắn phép".

**Cấu hình mới** (`ScanSettings`, config v-next, đọc config cũ bằng mặc định):
- `attack_range` (ô = bước, int >= 1). Mặc định theo class: cận chiến (Prince/Knight/Wizard cầm gậy) 1, Elf cung 9.
  Đổi ra px trên màn hình bằng `screen_step_px` (xem phần đo). Hiện ở tab Săn, khối cơ bản, cạnh hunt_range.
- `spell_min_mp_pct` (mặc định 70): ngưỡng MP để phép được dùng tự do.

**Nút "Đo tầm đánh"** (tab Săn, cạnh "Đo bước"; chỉ khi chưa săn và đã gắn cửa sổ; ESC dừng):
1. Detect một lần, sắp các box theo khoảng cách tăng dần, bỏ box trong SELF_R.
2. Với từng box (gần -> xa, tối đa 8 con, mỗi con một lần): hover, có con trỏ "attack" thì click 1 lần, rồi theo dõi
   1,5 s:
   - màn hình trôi = độ lệch pha (cv2.phaseCorrelate trên vùng chơi đã thu nhỏ, bỏ HUD) > `DRIFT_PX`: nhân vật ĐI ->
     box này ngoài tầm. Bấm ESC/một click tại chỗ nhân vật để đứng lại, rồi DỪNG đo ở đây.
   - không trôi + có hành động đánh (thanh máu dưới tên con đó tụt, HOẶC chat có dòng sát thương/kill) -> trong tầm,
     ghi khoảng cách (px).
3. Kết quả = khoảng cách xa nhất "không trôi + có đánh". Đổi px -> ô bằng `screen_step_px`, ghi
   `scan.attack_range` và `scan.attack_range_px`, rồi lưu config. Không đo được (không có quái, hoặc con gần nhất đã
   trôi) thì giữ giá trị cũ và báo lý do.
- `screen_step_px`: mặc định đo trên bản ghi 20261126_192615_observe (2 lần đi 5 click = 10 bước, có cả frame lẫn
  minimap) -> hằng số. Nút "Đo bước" hiện có thì ghi thêm số px màn hình của 10 bước đó.
- CẦN XÁC MINH trước khi code: thanh máu dưới tên quái có đọc được ổn không (vision/nameplates đọc tên, chưa đọc
  thanh); nếu không thì "có đánh" = không trôi + con trỏ vẫn là attack + box còn đó sau 1,5 s.

**Luật đánh** (combat.engage, thay `_shoot_only`; dùng cho mọi class):
1. Quái trong `attack_range_px` -> ĐÁNH THƯỜNG TẠI CHỖ (click/hold như engage cận chiến, không đi).
2. Phép chỉ dùng khi MỘT trong các điều kiện sau đúng:
   a. MP >= `spell_min_mp_pct`;
   b. danger, hoặc >= DANGER_MOBS (3) quái trong MELEE_DIST (không phụ thuộc mp_hungry);
   c. quái ngoài attack_range nhưng trong tầm phép (`range_px` của ô, hoặc shot_reach) -> bắn thay vì đi tới.
   Vẫn giữ các luật cũ: min_mp/cooldown/range_px của từng ô, ellipse bắt buộc, HEAL_MP_RESERVE.
3. Quái ngoài cả hai tầm:
   - hunt_range N > 0 thì đứng chờ ở gốc, KHÔNG click (go_home nếu lệch quá IN_PLACE_DRIFT như cũ);
   - hunt_range 0 (không giới hạn) thì đi tới như trước.
4. **Bảo vệ "click mà đi"**: sau mỗi click đánh, so độ trôi màn hình (cùng hàm của nút đo) trong 0,8 s; trôi >
   1 bước (`screen_step_px`) thì ngừng click con đó (ngoài tầm thật), blacklist điểm 10 s, ghi event
   `range_walk {dist, drift_px, attack_range}`. Hai lần range_walk liên tiếp ở khoảng cách < attack_range_px thì log
   cảnh báo "attack_range quá lớn, đo lại".
5. **Event để so tỉ lệ**: `melee_attack {dist, target, outcome}` mỗi lần click/hold đánh thường (1 event/lần bắt đầu
   đánh một con, không phải mỗi click); `spell_cast` giữ nguyên + thêm `why` = mp_high | danger | crowd |
   out_of_melee. analyze_records in tỉ lệ melee_attack : spell_cast và kill theo từng nguồn.

**Test** (trước khi build):
- Bản ghi 191624: replay wizard hunt_range 10, attack_range 1: orc trong MELEE_DIST -> engage cận chiến (không phải
  engage_ranged); MP 82% >= 70 -> có phép; MP < 70 và không danger -> 0 phép với quái kề bên.
- Đơn vị: chọn luật (bảng điều kiện a/b/c/3), range_walk khi drift giả > 1 bước, cấu hình cũ đọc ra mặc định theo
  class, UI có 2 trường mới + nút đo (test_ui).
- Drift: phaseCorrelate trên 2 frame liên tiếp của 192615_observe (đang đi) > DRIFT_PX, và của 191624 (đứng
  đánh) < DRIFT_PX.

**Rủi ro**:
- Wizard đánh thường rất yếu. Kill/phút có thể giảm so với chỉ bắn phép khi MP còn cao; điều kiện (a) bù lại.
- Cung (Elf) attack_range 9 thì click quái xa: nếu đo sai, nhân vật sẽ đi; luật 4 chặn sau 0,8 s.
- Phép ở (c) vẫn có thể kéo quái từ xa về khi MP thấp -> chỉ dùng (c) khi MP >= ô min_mp như cũ.
