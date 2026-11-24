# Kiến trúc Agent Registry

[README](../README.md) · [REST API](api_contract.md) · [Deployment](deployment.md)

## 1. Phạm vi và thành phần

~~~mermaid
flowchart LR
    P[Provider Agent] <-->|Local health| X[Lifecycle Companion]
    X -->|Register / Heartbeat| R[FastAPI Registry]
    S[Provider dùng SDK/REST] --> R
    U[Dashboard] --> R
    C[Consumer] -->|Discovery| R
    C -->|Business request| P
    R --> DB[(SQLite)]
~~~

- **Registry backend** (`registry/`): REST API, Agent Card validation, ownership và lease; không chạy business API.
- **Dashboard** (`registry/dashboard.html`): giao diện cùng origin, dùng REST, **không gửi heartbeat** thay Provider.
- **Companion** (`downloads/registry-companion-kit.zip`, `companion/`): sidecar dùng chung, đọc Dashboard JSON và credential, kiểm tra health local, tự re-register/heartbeat/recovery.
- **SDK** (`agent_registry_client/`): lựa chọn tích hợp sâu bằng Python, gồm discovery và invocation helper.
- **Consumer**: lấy danh sách endpoint từ Registry rồi gọi trực tiếp Provider; không có proxy ở Registry.

Message Broker, API Gateway, NAT traversal, điều phối nhiều Agent và business authentication **ngoài phạm vi Registry**. Demo Weather/News/Travel/Planner nằm ở `demo/`.

## 2. Record và tính bền vững

| Nhóm | Trường |
|---|---|
| Agent Card | `agent_id`, `name`, `description`, `domain`, `capabilities`, `endpoint`, `version` |
| Runtime | `registered_at`, `updated_at`, `last_heartbeat`, `lease_expires_at` |
| Nội bộ | `credential_hash` (SHA-256), `withdrawn` |

`status` **được suy ra khi đọc**, không lưu trong database. SQLite bền vững qua restart và trên VPS đặt ở `/var/lib/agent-registry/registry.db`, ngoài thư mục Git. Registry serialize SQLite writers bằng `BEGIN IMMEDIATE`. Chưa có hệ migration versioned hay replication.

## 3. Registration, lease và discovery

1. **ID mới:** Provider gửi full card kèm Join Token; Registry tạo ID, cấp ownership credential một lần.
2. **ID cũ:** Provider gửi full card kèm Bearer credential; Registry cập nhật binding và tạo lease mới.
3. **Đang chạy:** heartbeat có Bearer gia hạn lease. Nếu hết hạn hoặc đã unregister, heartbeat trả `409`, cần re-register.
4. **Dừng bình thường:** `POST /unregister` giữ record và ownership. `DELETE` xóa hẳn record và ownership.
5. **Consumer:** discovery theo domain/capability; mặc định chỉ nhận Agent `ONLINE`, sau đó invoke trực tiếp.

Với cấu hình mặc định: heartbeat **10 giây**, suspect **20 giây**, TTL **30 giây**. Thứ tự suy luận:

~~~text
withdrawn?             → UNREGISTERED
now >= lease_expires_at → UNREACHABLE
heartbeat quá ngưỡng?   → SUSPECT
ngược lại               → ONLINE
~~~

Không có active probing từ **Registry server**. Vì thế `UNREACHABLE` không chứng minh Agent chết, và `ONLINE` không chứng minh Consumer ở mạng khác gọi được. Companion chủ động thăm health API **tại máy Provider** trước khi heartbeat.

## 4. Bảo mật và vận hành

Production: **HTTPS → Caddy → Uvicorn (127.0.0.1:8000) → SQLite**; `systemd` quản lý process. Join Token được cấu hình riêng tại `/etc/agent-registry/admission.env`; owner credential nằm ở Provider, không đưa vào Git. REST GET/discovery không trả secret. Credential Registry **không phải** token gọi business API.

Có thể sử dụng SDK hoặc Companion, nhưng **chỉ một chủ thể quản lý lifecycle cho mỗi Agent ID**. Companion phát hiện trùng trong cùng tài khoản/máy bằng lock; chưa có fencing liên máy. SDK có thể ghi đè metadata khi re-register; Companion so khớp Agent Card rồi từ chối nếu config lệch.

## 5. Giới hạn và quyết định thiết kế

- Một Registry + SQLite: đơn giản để vận hành đồ án, chưa có replica, consensus hoặc benchmark tải lớn.
- Không có credential recovery/rotation hoàn chỉnh, tài khoản Provider/Client riêng hoặc hạn mức theo nhóm.
- Card chưa biểu diễn HTTP method, request/response schema, business auth và protocol version.
- Không đảm bảo reachability chéo mạng; Client cần kiểm tra endpoint và firewall.
- Retry business request có side effect cần idempotency; SDK chỉ có cơ chế rediscovery giới hạn cho tác vụ an toàn.

[Verification](verification.md) · [Invocation Contract](invocation_contract.md)
