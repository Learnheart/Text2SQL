# CLAUDE.md — Development Rules & Constraints

## Project Overview

Text-to-SQL Agent Platform cho domain Banking/POS. Hệ thống cho phép người dùng nghiệp vụ đặt câu hỏi bằng ngôn ngữ tự nhiên (tiếng Việt/Anh) và nhận câu trả lời từ PostgreSQL database.

### Architecture Documentation Reference

Tài liệu kiến trúc nằm tại `docs/03_Technical_Assessment/`. Có 3 patterns, mỗi pattern ứng với 1 phase:

| Phase | Pattern | Folder |
|-------|---------|--------|
| Phase 1 (R&D) | RAG-Enhanced Single Agent | `pattern_2_rag_single_agent/` |
| Phase 2 (POC) | LLM-in-the-middle Pipeline | `pattern_1_llm_in_the_middle/` |
| Phase 3 (Production) | Adaptive Router + Tiered Agents | `pattern_3_adaptive_router/` |

Mỗi folder chứa 5 tài liệu:
- `01_design_pattern.md` — Design patterns
- `02_components.md` — Components chi tiết
- `03_architecture_flow.md` — Luồng architecture
- `04_sequence_diagrams.md` — Sequence diagrams
- `05_tech_stack.md` — Tech stack

---

## RULES BẮT BUỘC

### Rule 1: Architecture-First — Kiểm tra tài liệu kiến trúc TRƯỚC KHI code

**TRƯỚC KHI viết bất kỳ dòng code nào**, bắt buộc phải:

1. Xác định code này thuộc **pattern nào** (Phase 1/2/3) và **component nào** (Router, Schema Linker, SQL Generator, Validator, Executor, etc.)
2. Đọc file tài liệu kiến trúc tương ứng trong `docs/03_Technical_Assessment/pattern_*/` để hiểu:
   - Component đó được thiết kế như thế nào (`02_components.md`)
   - Nó tương tác với các component khác ra sao (`03_architecture_flow.md`)
   - Luồng dữ liệu đi qua nó thế nào (`04_sequence_diagrams.md`)
   - Tech stack nào được chỉ định (`05_tech_stack.md`)
3. Đảm bảo implementation **khớp chính xác** với tài liệu — đúng input/output interface, đúng tech stack, đúng luồng xử lý

**Nếu phát hiện mâu thuẫn** giữa yêu cầu và tài liệu → dừng lại, báo cho người dùng, KHÔNG tự ý code khác tài liệu.

---

### Rule 2: Declare Before Act — Khai báo hành động trước khi thực hiện

**TRƯỚC KHI bắt tay vào implement**, bắt buộc phải trình bày rõ ràng cho người dùng:

1. **Sẽ thêm mới những gì?** — File nào, function nào, class nào
2. **Sẽ sửa/update những gì?** — File nào bị ảnh hưởng, thay đổi gì cụ thể
3. **Sẽ xoá những gì?** — File/code nào bị loại bỏ và lý do
4. **Thuộc module/component nào?** — Map rõ vào component trong tài liệu kiến trúc
5. **Ảnh hưởng đến component nào khác?** — Side effects, dependencies

Format khai báo:

```
## Kế hoạch thực hiện

**Pattern:** [Pattern X — tên]
**Component:** [tên component]
**Reference:** [đường dẫn file tài liệu kiến trúc]

### Thêm mới:
- `path/to/new_file.py` — [mô tả ngắn]

### Sửa đổi:
- `path/to/existing_file.py` — [thay đổi gì, tại sao]

### Xoá:
- `path/to/old_file.py` — [lý do xoá]

### Ảnh hưởng:
- [Component X] — [ảnh hưởng gì]
```

**CHỈ bắt đầu code SAU KHI người dùng xác nhận kế hoạch.**

---

### Rule 3: Architecture Boundary — Không vượt phạm vi kiến trúc

Khi nhận yêu cầu mà **không khớp** với tài liệu kiến trúc hiện tại:

1. **Dừng lại** — KHÔNG tự ý implement
2. **Báo rõ cho người dùng:**
   - Yêu cầu này vượt ngoài phạm vi kiến trúc hiện tại
   - Nó ảnh hưởng đến component/layer nào
   - Cần update tài liệu kiến trúc nào trước
3. **Yêu cầu người dùng update tài liệu kiến trúc TRƯỚC**, sau đó mới code

Các trường hợp cần flag:
- Thêm component mới không có trong `02_components.md`
- Thay đổi luồng xử lý khác với `03_architecture_flow.md`
- Dùng tech stack khác với `05_tech_stack.md`
- Thêm LLM call vào step được thiết kế là deterministic code
- Thay đổi interface giữa các components

---

### Rule 4: Test After Implement — Unit test bắt buộc sau khi code

Sau khi implement xong bất kỳ code nào, bắt buộc phải:

1. **Viết unit test** cho code vừa implement
2. **Test phải verify** theo đúng behavior mô tả trong tài liệu kiến trúc:
   - Input/output đúng format
   - Edge cases được handle
   - Error cases trả về đúng expected behavior
   - Integration với components liên quan hoạt động đúng
3. **Chạy test** và đảm bảo PASS trước khi báo hoàn thành
4. **Test file convention:** đặt trong thư mục `tests/` với tên `test_<module_name>.py`

**KHÔNG được báo hoàn thành nếu test chưa PASS.**

---

### Rule 5: Report Changes — Báo cáo thay đổi sau khi hoàn thành

Sau khi hoàn thành code (bao gồm cả test), bắt buộc phải khai báo:

```
## Báo cáo thay đổi

### Files đã thêm mới:
- `path/to/file.py` — [mô tả]

### Files đã sửa đổi:
- `path/to/file.py` — [thay đổi gì]

### Files đã xoá:
- `path/to/file.py` — [lý do]

### Tests:
- `tests/test_xxx.py` — [X passed, Y failed]

### Verification:
- [ ] Code khớp với tài liệu kiến trúc
- [ ] Unit tests PASS
- [ ] Không có side effects ngoài dự kiến
```

---

## WORKFLOW TÓM TẮT

```
Nhận yêu cầu
    │
    ▼
[1] Đọc tài liệu kiến trúc tương ứng (Rule 1)
    │
    ├── Vượt phạm vi? → Báo người dùng, yêu cầu update tài liệu (Rule 3)
    │
    ▼
[2] Khai báo kế hoạch cho người dùng (Rule 2)
    │
    ├── Người dùng chưa confirm? → Chờ xác nhận
    │
    ▼
[3] Implement code
    │
    ▼
[4] Viết và chạy unit test (Rule 4)
    │
    ├── Test FAIL? → Fix code, chạy lại test
    │
    ▼
[5] Báo cáo thay đổi (Rule 5)
```
