# Registry API Contract

[README](../README.md) · [Architecture](architecture.md) · [Agent Integration](agent_integration.md)

## 1. Phạm vi

Base URL local: `http://127.0.0.1:8000`. Request/response dùng JSON UTF-8; timestamp ISO-8601 UTC có `Z` hoặc `+00:00`. Schema sinh từ app tại [OpenAPI](http://127.0.0.1:8000/openapi.json), giao diện thử tại [Swagger UI](http://127.0.0.1:8000/docs).

Tài liệu này mô tả **Registry REST API**. [Provider invocation contract](invocation_contract.md) là thỏa thuận riêng của provider/consumer, không phải schema Registry áp đặt lên business API.

## 2. Agent Card và normalization

Ví dụ request tạo registration:

```json
{
  "agent_id": "weather-team-a",
  "name": "Weather Agent",
  "domain": "weather",
  "description": "Forecast provider",
  "capabilities": ["weather_forecast"],
  "endpoint": "http://192.168.1.20:8001/forecast",
  "version": "1.0"
}
```

Tất cả trường bắt buộc khi POST; không nhận trường thừa hoặc metadata do client tự đặt.

| Trường | Quy tắc |
|---|---|
| agent_id | 1–128 ký tự, regex `[A-Za-z0-9][A-Za-z0-9_.-]{0,127}`; phân biệt hoa thường |
| name | Chuỗi 1–200 ký tự sau strip |
| domain | Chuỗi 1–100 ký tự sau strip, sau đó normalization |
| description | Chuỗi tối đa 1000 ký tự sau strip; được rỗng |
| capabilities | 1–100 chuỗi đầu vào; normalization, loại trùng và sắp xếp |
| endpoint | HTTP(S) URL tối đa 2048 ký tự; không username/password/fragment |
| version | Chuỗi 1–64 ký tự sau strip; chưa có compatibility negotiation |

Domain/capability được strip, lowercase, gom chuỗi whitespace hoặc dấu `-` thành `_`. Kết quả phải khớp `[a-z0-9][a-z0-9_.:]{0,99}`. Ví dụ ` Weather-Forecast ` thành `weather_forecast`. Filter áp dụng cùng normalization, so khớp chính xác; query domain/capability tối đa 100 ký tự trước normalization. URL được Pydantic chuẩn hóa; Registry không kiểm tra khả năng truy cập endpoint.

## 3. Authentication và ownership

Dùng header `Authorization: Bearer <credential>` của đúng Agent ID. Không đưa secret vào URL.

- ID mới: đăng ký không kèm credential, nhận secret một lần. Gửi credential cho ID chưa tồn tại trả 401.
- ID đã tồn tại: cần credential đúng để re-register hoặc mutation; sai/thiếu trả 401, không ghi đè record.
- GET không yêu cầu credential; không trả secret/hash.
- Lỗi 401 có header `WWW-Authenticate: Bearer`.

Ownership không tương đương xác minh danh tính tổ chức. Đăng ký ID mới và đọc danh bạ hiện chưa có admission policy/tài khoản.

## 4. Routes và response models

| Method | Route | Input | Thành công | Bearer |
|---|---|---|---|---|
| POST | `/v1/agents` | Card đầy đủ | 201 tạo mới / 200 re-register; Registration | Khi ID đã tồn tại |
| GET | `/v1/agents` | capability, domain, active_only | 200, array AgentView | Không |
| GET | `/v1/agents/{agent_id}` | ID | 200, AgentView | Không |
| PATCH | `/v1/agents/{agent_id}` | Các trường card trừ ID | 200, AgentView | Có |
| POST | `/v1/agents/{agent_id}/heartbeat` | Không cần body | 200, AgentView | Có |
| GET | `/v1/agents/{agent_id}/status` | ID | 200, AgentStatus | Không |
| POST | `/v1/agents/{agent_id}/unregister` | Không cần body | 200, AgentView | Có |
| DELETE | `/v1/agents/{agent_id}` | ID | 204, body rỗng | Có |
| GET | `/v1/health` | Không | 200, Health | Không |

**AgentView:** toàn bộ Agent Card cộng `registered_at`, `updated_at`, `last_heartbeat`, `lease_expires_at`, `status`.

**Registration:** AgentView cộng `heartbeat_interval_seconds`, `ttl_seconds`; chỉ response 201 có thêm `credential`. Response 200 re-register **bỏ trường credential**, không trả null. Cả hai có `Cache-Control: no-store`.

**AgentStatus:** chỉ `agent_id`, `status`, `last_heartbeat`, `lease_expires_at`.

Ví dụ status sau đăng ký (timestamp minh họa):

```json
{
  "agent_id": "weather-team-a",
  "status": "ONLINE",
  "last_heartbeat": "2026-11-16T09:00:00Z",
  "lease_expires_at": "2026-11-16T09:00:30Z"
}
```

**Health:** `status: "ok"`, `server_time`, `heartbeat_interval_seconds`, `ttl_seconds`, sau kiểm tra DB bằng SELECT 1. Đây không phải health của provider.

## 5. Discovery và lookup

```http
GET /v1/agents?domain=weather&capability=weather_forecast
GET /v1/agents?active_only=false
GET /v1/agents/weather-team-a
```

- `active_only=true` là mặc định, chỉ trả **ONLINE**.
- `active_only=false` gồm ONLINE/SUSPECT/UNREACHABLE/UNREGISTERED để quan sát, vẫn áp dụng các filter khác.
- Domain và capability kết hợp AND. Một capability có thể có nhiều provider.
- Array sắp theo Agent ID tăng dần theo thứ tự SQLite; không phân trang.
- Không có kết quả trả `200 []`. Lookup ID không tồn tại trả 404.
- Lookup/status theo ID vẫn trả record không ONLINE; không tự chọn nó làm provider.
- GET không renew lease; expiry được đánh giá khi query, không cần maintenance chạy trước.

## 6. Registration, mutation và lease

Mặc định heartbeat interval 10s, suspect threshold 20s, TTL 30s. Nếu không cấu hình suspect riêng, dùng trung bình interval và TTL. Điều kiện cấu hình: `0 < interval < suspect < TTL`.

| Operation | Card / ownership | Timestamp / trạng thái |
|---|---|---|
| Register mới | Tạo card và hash credential | Các timestamp = now, expiry = now + TTL, ONLINE |
| Re-register | Card đầy đủ thay thế card cũ; giữ hash và registered_at | updated_at/last_heartbeat = now, expiry = now + TTL, bỏ withdrawn |
| Heartbeat | Không thay card/endpoint | updated_at/last_heartbeat = now, expiry = now + TTL |
| PATCH | Sửa các trường cung cấp; không đổi ID | Chỉ updated_at đổi, không renew |
| Unregister | Giữ card/hash/registered_at | withdrawn = true, updated_at/expiry = now |
| DELETE | Xóa record và hash | ID được giải phóng |

PATCH phải có ít nhất một trường, không nhận null, ID hoặc runtime metadata. Ví dụ:

```json
{"endpoint": "http://192.168.1.20:9005/forecast"}
```

PATCH có thể sửa record UNREACHABLE/UNREGISTERED nhưng không kích hoạt lại. Re-registration có credential hợp lệ được phép ở mọi trạng thái và renew lease.

Status ưu tiên UNREGISTERED khi withdrawn; sau đó UNREACHABLE khi `now >= lease_expires_at`; SUSPECT khi tuổi heartbeat đạt suspect threshold nhưng lease còn hạn; còn lại ONLINE. Heartbeat khi SUSPECT được nhận; sau expiry hoặc unregister trả 409, cần re-register.

Unregister lặp lại được, giữ ownership để restart. DELETE xóa vĩnh viễn, các lookup/mutation theo ID sau đó trả 404; một đăng ký mới không token có thể lấy ID này. SDK không tự chiếm lại ID khi gặp 404.

## 7. HTTP errors

| HTTP | Ý nghĩa |
|---|---|
| 401 | Thiếu/sai ownership credential; hoặc gửi token cho ID mới |
| 404 | Record không tồn tại |
| 409 | Heartbeat khi lease hết hoặc đã unregister |
| 422 | Card/query sai, trường thừa, PATCH rỗng/null |
| 503 | DB tạm không truy cập được hoặc lỗi operational, gồm SQLite bận quá timeout |

Lỗi service dùng `{"detail":"..."}`. Validation Pydantic/FastAPI dùng detail array; normalization query có thể dùng detail string. Client nên dựa vào HTTP code, không parse thông điệp tiếng Anh.

Server không trả lại credential sau lần tạo mới. Nếu response đầu tiên thất lạc nhưng record đã tạo, retry không có khóa có thể nhận 401; chưa có idempotency key hoặc recovery API.

## 8. Backward compatibility

Agent Card và DELETE giữ semantics hiện tại; `POST /unregister` là thao tác giữ ownership riêng. Literal status hiện là ONLINE/SUSPECT/UNREACHABLE/UNREGISTERED, **không còn ACTIVE/EXPIRED**. Client dựa trên literal cũ phải cập nhật; `active_only=true` hiện loại cả SUSPECT.

Weather GET và import `demo.registry_client.RegistryClient` vẫn được giữ; chúng thuộc demo/SDK, không mở rộng schema Registry. Xem [Invocation Contract](invocation_contract.md) và [Verification](verification.md).
