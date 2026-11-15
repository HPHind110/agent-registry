# Kiểm chứng lifecycle — 15/11/2026

- Python 3.13 trên Windows, virtualenv hiện có.
- `python -m pytest -q`: 44 passed, 1 warning, 3.03s sau khi thêm observer. Warning Starlette TestClient/httpx deprecated, không phải test failure.
- HTTP smoke thật: startup, automatic heartbeat qua nhiều TTL, Travel discovery và gọi provider, crash/SUSPECT/UNREACHABLE, loại khỏi discovery, Registry restart giữ expiry, recovery cùng ID ở endpoint mới, Registry outage nhưng forecast vẫn phục vụ, automatic reconnect, graceful unregister, process shutdown và temporary DB cleanup: tất cả PASS, exit 0.
- Runner test dùng file điều khiển riêng, os._exit mô phỏng crash bỏ qua cleanup; server.should_exit mô phỏng shutdown tử tế. Không có route quản trị process trong app.
- Lần smoke đầu dùng taskkill bị môi trường từ chối; không dùng kết quả đó để tuyên bố thành công. Lần kế tiếp sửa module import cho runner, rồi chạy trọn vẹn thành công.
- Test UI dùng DOM/HTTP giả; không tuyên bố browser E2E, LAN hoặc tích hợp liên nhóm. `node --test tests/dashboard.test.cjs`: 6 passed, 0 failed, exit 0; kiểm tra cả polling chỉ GET và cập nhật dialog đang mở.
- Active probe và instance_id không triển khai; không có test giả nhận rằng đã kiểm tra chúng. Thay probe bằng lease-based failure detector như boundary của repo ban đầu.
