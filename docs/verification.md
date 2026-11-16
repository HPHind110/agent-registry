# Kiểm chứng lifecycle — 15/11/2026

- Python 3.13 trên Windows, virtualenv hiện có.
- `python -m pytest -q`: 44 passed, 1 warning, 3.03s sau khi thêm observer. Warning Starlette TestClient/httpx deprecated, không phải test failure.
- HTTP smoke thật: startup, automatic heartbeat qua nhiều TTL, Travel discovery và gọi provider, crash/SUSPECT/UNREACHABLE, loại khỏi discovery, Registry restart giữ expiry, recovery cùng ID ở endpoint mới, Registry outage nhưng forecast vẫn phục vụ, automatic reconnect, graceful unregister, process shutdown và temporary DB cleanup: tất cả PASS, exit 0.
- Runner test dùng file điều khiển riêng, os._exit mô phỏng crash bỏ qua cleanup; server.should_exit mô phỏng shutdown tử tế. Không có route quản trị process trong app.
- Lần smoke đầu dùng taskkill bị môi trường từ chối; không dùng kết quả đó để tuyên bố thành công. Lần kế tiếp sửa module import cho runner, rồi chạy trọn vẹn thành công.
- Test UI dùng DOM/HTTP giả; không tuyên bố browser E2E, LAN hoặc tích hợp liên nhóm. `node --test tests/dashboard.test.cjs`: 6 passed, 0 failed, exit 0; kiểm tra cả polling chỉ GET và cập nhật dialog đang mở.
- Active probe và instance_id không triển khai; không có test giả nhận rằng đã kiểm tra chúng. Thay probe bằng lease-based failure detector như boundary của repo ban đầu.


## Generic external integration — 16/11/2026

- `python -m pytest -q`: **67 passed**, 1 Starlette/httpx deprecation warning, 4.72s. Gồm 44 regression tests và 23 cases mới: arbitrary domains, News inputs/errors, Weather GET/POST compatibility, consumer failover network/HTTP/JSON/schema/identity/capability, Planner complete/partial, malformed discovery và SDK import compatibility.
- `node --test tests/dashboard.test.cjs`: **6 passed**, 0 failed.
- `python scripts/smoke_test.py`: tất cả 6 nhóm PASS, exit 0; Weather/Travel legacy, crash/expiry, persistence, endpoint recovery, Registry outage, graceful unregister và cleanup.
- `python -m scripts.generic_smoke_test`: tất cả 5 nhóm PASS, exit 0. Registry/Weather/News/Planner là process riêng qua HTTP loopback; hai provider heartbeat qua nhiều TTL không browser; Weather crash để lại News usable; Planner partial; đổi endpoint; Registry outage và cả hai reconnect; graceful unregister; cleanup.
- Build SDK wheel: ban đầu thiếu setuptools, đã cài setuptools 84.2.1 trong venv rồi `python -m pip wheel . --no-deps --no-build-isolation --wheel-dir dist` thành công. Wheel chỉ đóng gói SDK. Đã cài wheel vào thư mục tạm và import trong Python isolated mode từ thư mục ngoài repo: PASS.
- Không reset database/credential người dùng. Smoke/tests dùng dữ liệu riêng. Sửa smoke cũ để đặt SUSPECT=2 rõ ràng, tránh kế thừa biến môi trường SUSPECT=20 khi TTL test chỉ 3s.
- Không thêm logic Weather/News vào Registry, không thay schema DB/API registration. Common POST protocol là phần bổ sung phía provider/consumer.
- Chưa kiểm chứng Python 3.11 riêng, browser E2E, LAN, nhóm ngoài hoặc Internet production. Không tuyên bố News là tin thật hay Planner là AI.
