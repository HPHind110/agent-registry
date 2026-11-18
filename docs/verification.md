# Verification

[README](../README.md) · [Architecture](architecture.md) · [Agent Integration](agent_integration.md)

File này mô tả **hệ thống đang được kiểm tra ở những mức nào** và cách chạy các bài test.

Nó không phải hướng dẫn sử dụng Registry. Nếu chỉ muốn chạy project, xem [README](../README.md).

## 1. Có những loại test nào?

Project hiện có bốn mức kiểm tra chính.

### API tests

Kiểm tra Registry REST API:

- register;
- discovery;
- lookup;
- credential;
- heartbeat;
- lease;
- update;
- unregister;
- persistence;
- validation.

Source chính:

```text
tests/test_registry.py
```

### Lifecycle tests

Kiểm tra các tình huống theo thời gian và lỗi mạng:

- heartbeat qua nhiều lease;
- `ONLINE → SUSPECT → UNREACHABLE`;
- recovery;
- re-registration;
- Registry tạm unavailable;
- graceful shutdown.

Source:

```text
tests/test_lifecycle.py
```

### Generic integration tests

Kiểm tra Registry không phụ thuộc Weather:

- nhiều domain/capability;
- News Agent;
- Weather backward compatibility;
- Planner;
- multiple providers;
- failover;
- response validation.

Source:

```text
tests/test_generic.py
```

### Process smoke tests

Các script này khởi động những process thật và giao tiếp qua HTTP loopback.

```text
scripts/smoke_test.py
scripts/generic_smoke_test.py
```

Chúng gần với demo end-to-end hơn unit test.

## 2. Chạy test

Sau khi cài dependencies:

```powershell
python -m pytest -q
```

Dashboard controller tests cần Node.js:

```powershell
node --test tests/dashboard.test.cjs
```

Legacy Weather/Travel smoke:

```powershell
python scripts/smoke_test.py
```

Generic Registry/Weather/News/Planner smoke:

```powershell
python -m scripts.generic_smoke_test
```

Node.js không cần để chạy Registry; chỉ cần cho dashboard test.

## 3. Những scenario chính được kiểm tra

| Scenario | Được kiểm tra ở |
|---|---|
| Register và lookup Agent | API tests |
| Duplicate ID và ownership | API tests |
| Discovery theo domain/capability | API + generic tests |
| Nhiều Provider cùng capability | API + generic tests |
| Heartbeat renew lease | API + lifecycle tests |
| SUSPECT / UNREACHABLE | lifecycle tests |
| Re-register sau khi lease hết | lifecycle tests |
| Endpoint thay đổi | lifecycle + smoke |
| Registry restart giữ dữ liệu | API + smoke |
| Registry tạm unavailable | lifecycle + smoke |
| Weather business API vẫn chạy khi Registry lỗi | lifecycle + smoke |
| Graceful unregister | lifecycle + smoke |
| Weather GET cũ vẫn dùng được | generic + legacy smoke |
| News search/summarize | generic tests |
| Planner complete/partial | generic + generic smoke |
| Provider failover | generic tests |
| Browser không heartbeat thay Agent | dashboard tests |
| Weather + News chạy như process riêng | generic smoke |

## 4. Generic smoke test đang chứng minh điều gì?

Flow chính:

```text
Start Registry
   ↓
Start Weather + News
   ↓
hai Provider tự register + heartbeat
   ↓
Planner discovery và gọi cả hai
```

Sau đó script tiếp tục kiểm tra:

```text
Weather crash
   ↓
Weather bị loại khỏi discovery
   ↓
News vẫn dùng được
   ↓
Planner trả partial
```

và:

```text
Weather restart ở endpoint mới
   ↓
re-register
   ↓
Planner discovery binding mới
```

Ngoài ra còn kiểm tra Registry outage và graceful shutdown.

## 5. Tại sao unit test dùng fake clock / MockTransport?

Một số hành vi phụ thuộc thời gian.

Nếu test thật sự phải chờ TTL 30 giây cho từng case thì test sẽ rất chậm.

Vì vậy lifecycle tests dùng clock điều khiển được để mô phỏng:

```text
now
↓
advance 20s
↓
SUSPECT
↓
advance tiếp
↓
UNREACHABLE
```

`httpx.MockTransport` được dùng để giả lập:

- mất kết nối;
- HTTP 503;
- JSON sai;
- schema sai;
- Provider đầu tiên fail.

Smoke test vẫn dùng process và HTTP thật để bổ sung cho các test giả lập này.

## 6. Những gì chưa được kiểm chứng đầy đủ

### VPS service: kiểm tra thủ công, không phải cross-machine test

Nhóm đã kiểm tra thủ công **một Agent Registry instance** trên VPS Ubuntu 24.04: process do `systemd` quản lý báo `active (running)`, `ss` hiển thị bind `127.0.0.1:8000`, SQLite file tồn tại và `/v1/health` trả `status: ok`. Sau khi restart, một request ngay lập tức đã gặp `Connection refused` nhưng request sau thành công; hiện chưa xác định được nguyên nhân chắc chắn, có thể do startup chưa sẵn sàng.

Phạm vi **chưa** kiểm tra xong: reboot recovery thực tế, preservation của registration thật sau restart, SSH/HTTPS exposure và các máy khác dùng chung Registry VPS, Agent-to-Agent invocation giữa các mạng, cross-team integration. Xem [Deployment & Operations](deployment.md) để phân biệt CLI local với SSH tunnel.


Hiện test chủ yếu chạy trong local/loopback.

Chưa coi là đã kiểm chứng đầy đủ:

- nhiều laptop trên LAN thực tế;
- Agent của nhóm khác;
- firewall/network policy thực tế;
- Internet production;
- browser E2E đầy đủ;
- benchmark số lượng Agent lớn;
- Registry replication/consensus;
- instance fencing;
- credential rotation/recovery.

Nói cách khác:

> Local tests chứng minh implementation hiện tại hoạt động trong phạm vi đã mô phỏng và smoke test, không chứng minh mọi tình huống mạng phân tán ngoài thực tế.

## 7. Khi nào nên chạy bộ test nào?

Khi sửa Registry backend:

```powershell
python -m pytest -q
```

Khi sửa Dashboard:

```powershell
node --test tests/dashboard.test.cjs
```

Trước khi demo Weather/Travel:

```powershell
python scripts/smoke_test.py
```

Trước khi demo generic integration:

```powershell
python -m scripts.generic_smoke_test
```

Trước khi tích hợp liên nhóm, nên chạy toàn bộ bốn nhóm test trên rồi mới chuyển sang kiểm thử LAN/cross-team.
