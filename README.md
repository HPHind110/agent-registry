# Agent Registry

**Agent Registry** là danh bạ dịch vụ cho hệ thống đa Agent: Provider đăng ký `Agent Card` (ID, capability, endpoint), duy trì trạng thái bằng heartbeat; Client tìm Provider rồi gọi trực tiếp API của Provider. Dự án thuộc học phần Hệ thống phân tán, dùng FastAPI, SQLAlchemy và SQLite.

**Đang sử dụng:** [Registry Dashboard (HTTPS)](https://103-180-134-53.sslip.io/) · [API docs](https://103-180-134-53.sslip.io/docs) · [Companion v1.0](https://github.com/HPHind110/agent-registry/releases/tag/companion-v1.0.0)

## Bắt đầu nhanh

### Provider: đã có HTTP Agent

**Không cần clone Registry hay nhúng SDK.**

1. Chạy HTTP API của Agent, chuẩn bị một URL kiểm tra sức khỏe (GET trả 2xx khi Agent sẵn sàng).
2. Mở [Dashboard HTTPS](https://103-180-134-53.sslip.io/), chọn **Đăng ký Agent**, điền ID, tên, domain, capabilities, endpoint, version và mô tả. ID mới cần **Join Token** do nhóm Registry cấp.
3. Tải **JSON cấu hình** và **ownership credential**; giữ chúng cạnh nhau, ngoài Git và trong thư mục riêng tư.
4. Tải [Registry Companion Kit](https://github.com/HPHind110/agent-registry/releases/tag/companion-v1.0.0), giải nén toàn bộ. Máy Provider cần Python **3.11+**.
5. Bật Agent; trên Windows nhấp đúp `registry-companion-start.cmd` (Linux: `sh ./registry-companion-start.sh`). Chọn JSON, nhập health URL, đợi dòng **registration ONLINE**.
6. Các lần sau, mở launcher `start-<agent-id>-<mã>.cmd` được tạo riêng. Companion tự heartbeat, phát hiện Agent dừng và phục hồi sau khi Agent khởi động lại.

Xem [Hướng dẫn Provider từng bước](docs/companion_onboarding.md), gồm ví dụ Windows/Linux và xử lý lỗi.

**Lưu ý:** đăng ký trên Dashboard không tự chạy Agent hay gửi heartbeat. `ONLINE` phản ánh lease/health phía Provider, **không bảo đảm Client ở máy khác gọi được** endpoint. Địa chỉ `127.0.0.1` trên Agent Card chỉ phù hợp khi Client cũng chạy trên chính máy đó.

### Client: tìm và gọi Agent

Không cần Join Token hoặc ownership credential để discovery:

~~~http
GET https://103-180-134-53.sslip.io/v1/agents?capability=weather_forecast
~~~

Registry trả danh sách Agent `ONLINE` và endpoint đã đăng ký. Client chọn Provider rồi gọi **đúng HTTP method, payload và business authentication** do Provider công bố. Registry không chuyển tiếp business requests và không tự suy ra schema của Provider.

Đọc [API Contract](docs/api_contract.md) và [Invocation Contract](docs/invocation_contract.md).

## Hệ thống gồm những gì?

~~~mermaid
flowchart LR
    P[Provider Agent] <-->|Health check local| X[Lifecycle Companion]
    X -->|Register / Heartbeat| R[Registry HTTPS]
    U[Web Dashboard] --> R
    C[Client] -->|Discover| R
    C -->|Business invocation trực tiếp| P
    R --> D[(SQLite)]
~~~

- **Registry:** quản lý Agent Card, ownership, lease và discovery.
- **Companion:** công cụ độc lập cho Provider; dùng chung cho Agent Python, Node.js, Java, Go... nếu có HTTP health URL.
- **Python SDK / REST:** lựa chọn nâng cao, **không bắt buộc** dùng Companion.
- **Không thuộc Registry:** Message Broker, API Gateway, NAT traversal, orchestration và xác thực nghiệp vụ của Provider.

## Chạy một Registry riêng để phát triển

Đây là một **instance local với database riêng**, không kết nối hay đồng bộ với VPS:

~~~powershell
git clone https://github.com/HPHind110/agent-registry.git
cd agent-registry
py -3 -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements.txt
$env:REGISTRY_ALLOW_OPEN_REGISTRATION = "1"  # Chỉ dùng cho local demo
.\.venv\Scripts\python -m uvicorn registry.main:app --host 127.0.0.1 --port 8000
~~~

Mở `http://127.0.0.1:8000/`. Không bật open registration cho VPS công khai. Production dùng HTTPS cùng Join Token, vận hành qua `systemd` và Caddy; xem [Deployment](docs/deployment.md).

## Tài liệu

| Muốn làm gì? | Tài liệu |
|---|---|
| Đăng ký Provider không sửa code | [Companion Onboarding](docs/companion_onboarding.md) |
| Tích hợp SDK/REST nâng cao hoặc viết Consumer | [Agent Integration](docs/agent_integration.md) |
| Xem endpoint, auth, status và HTTP errors | [API Contract](docs/api_contract.md) |
| Hiểu kiến trúc, lease và giới hạn | [Architecture](docs/architecture.md) |
| Gọi API nghiệp vụ sau discovery | [Invocation Contract](docs/invocation_contract.md) |
| Vận hành, backup, cập nhật VPS HTTPS | [Deployment](docs/deployment.md) |
| Chạy test, smoke test và kiểm chứng | [Verification](docs/verification.md) |

## Giới hạn

Hiện chỉ có **một Registry instance và SQLite**, chưa có replication, instance fencing giữa nhiều máy, credential recovery/rotation đầy đủ hoặc rate limiting theo nhóm. Companion giám sát health **tại máy Provider**; Client vẫn phải tự xác minh reachability từ mạng của mình và thỏa thuận giao thức nghiệp vụ.
