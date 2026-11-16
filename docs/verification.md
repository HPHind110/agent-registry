# Verification

[README / chạy demo](../README.md) · [Architecture](architecture.md) · [Agent Integration](agent_integration.md)

Tài liệu này ghi phạm vi test và kết quả thực thi, không thay thế hướng dẫn sử dụng hoặc chứng nhận triển khai production.

## 1. Test Strategy

| Lớp kiểm tra | Source | Cách thực hiện |
|---|---|---|
| API, persistence, validation | tests/test_registry.py | FastAPI TestClient, SQLite tạm, clock điều khiển được |
| Lifecycle / failure detection | tests/test_lifecycle.py | Clock giả cho boundary; httpx MockTransport cho retry/recovery |
| Provider contract / consumer integration | tests/test_generic.py | News/Weather API, discovery, validate output và failover |
| Dashboard controller | tests/dashboard.test.cjs | Node test runner với DOM/fetch giả |
| Legacy process smoke | scripts/smoke_test.py | Registry + Weather + Travel qua process riêng và HTTP loopback |
| Multi-provider process smoke | scripts/generic_smoke_test.py | Registry + Weather + News + Planner qua process riêng |

Fake clock tránh chờ TTL thực trong API tests. Smoke dùng TTL ngắn, port/DB/credential tạm; không sử dụng database và credential demo của người dùng. Runner test-only điều khiển process qua file riêng: crash dùng os._exit bỏ qua cleanup, graceful dùng Uvicorn shutdown; không thêm public route điều khiển server.

## 2. Commands

Sau khi cài dependencies theo README, từ root repository:

```powershell
.\.venv\Scripts\python -m pytest -q
node --test tests/dashboard.test.cjs
.\.venv\Scripts\python scripts/smoke_test.py
.\.venv\Scripts\python -m scripts.generic_smoke_test
```

Node chỉ cần cho dashboard tests. Generic smoke phải chạy dạng module như trên để import helpers từ scripts. Server log được in khi smoke thất bại; cleanup kiểm tra kết thúc process và xóa DB tạm.

## 3. Current Verification Results

Thực thi ngày **16/11/2026**, Windows, Python **3.13.15**, Node.js **v24.20.0**, virtualenv hiện có.

| Lệnh | Kết quả thực tế |
|---|---|
| pytest -q | 67 passed, 1 warning, 4.06s; exit 0 |
| node --test tests/dashboard.test.cjs | 6 passed, 0 failed; exit 0 |
| python scripts/smoke_test.py | 6 nhóm PASS, gồm shutdown và temporary database cleanup; exit 0 |
| python -m scripts.generic_smoke_test | 5 nhóm PASS, gồm cleanup; exit 0 |

Warning pytest là StarletteDeprecationWarning về TestClient dùng httpx. Không thay dependency/code để xử lý warning trong task tài liệu này.

“Nhóm PASS” là các checkpoint do smoke script in ra, không phải số test case pytest. Kết quả trên chỉ mô tả môi trường/lần chạy này; không suy ra mọi tình huống mạng đều đã được xử lý.

## 4. Scenarios Covered

| Scenario | Bằng chứng trong suite |
|---|---|
| Registration, lookup, normalization, response schemas | test_registry |
| Ownership, duplicate/concurrent ID, unauthorized mutation | test_registry |
| Heartbeat renew, nhiều chu kỳ lease, ngưỡng SUSPECT/UNREACHABLE | test_registry + test_lifecycle |
| Exclude non-ONLINE khỏi discovery, nhiều provider/filter | test_registry + test_generic |
| Re-registration, endpoint update, persistence qua restart | API tests + cả hai smoke |
| Unregister giữ ownership, DELETE xóa record | test_lifecycle / test_registry |
| Retry Registry unavailable, business API tiếp tục | test_lifecycle + cả hai smoke |
| Weather GET/POST compatibility | test_generic + legacy smoke |
| News search/summarize và input lỗi | test_generic |
| Planner complete/partial, direct invocation | test_generic + generic smoke |
| Failover network/HTTP/JSON/schema/identity/capability | test_generic với MockTransport |
| Browser không heartbeat, polling chỉ GET | dashboard controller tests |
| Heartbeat hoạt động không cần browser | cả hai process smoke |
| Import SDK cũ còn hoạt động | test_generic |

Smoke legacy quan sát crash → SUSPECT → UNREACHABLE, Registry restart không hồi sinh lease cũ, recovery cùng identity ở endpoint mới và graceful unregister. Generic smoke thêm Weather crash trong khi News còn dùng được, Planner partial, cả hai provider reconnect sau Registry outage.

## 5. Not Verified

- LAN nhiều máy, provider của nhóm ngoài, mạng Internet production.
- Browser E2E hoặc layout/accessibility trên browser thật; DOM giả không thay thế kiểm thử này.
- Python 3.11/3.12 hoặc hệ điều hành khác trong lần chạy hiện tại.
- Benchmark tải, số lượng Agent lớn, mọi kiểu packet loss/network partition hoặc clock jump.
- Build/cài wheel SDK độc lập trong lần kiểm chứng này.
- Active probe, instance fencing, credential rotation: chưa được triển khai, không có test chứng minh các feature này.

Các ví dụ code trong tài liệu cần được phân biệt với các module demo đang có. Kết quả kiểm tra cú pháp/link tài liệu được ghi trong báo cáo refactor, không tính vào số test của ứng dụng.
