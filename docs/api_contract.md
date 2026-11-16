# Registry API

[README](../README.md) · [Architecture](architecture.md) · [Agent Integration](agent_integration.md)

File này mô tả **REST API công khai của Agent Registry**: đăng ký Agent, tìm kiếm, heartbeat, cập nhật và hủy đăng ký.

Nếu chỉ muốn chạy Registry và dùng Web Dashboard, xem [README](../README.md). Nếu muốn tích hợp một Agent mới, xem [Agent Integration](agent_integration.md).

## 1. Khái niệm chính

| Khái niệm | Ý nghĩa |
|---|---|
| Agent Card | Thông tin mô tả một Provider Agent |
| Agent ID | Định danh ổn định của Agent |
| Domain | Lĩnh vực của Agent, ví dụ `weather`, `news` |
| Capability | Chức năng cụ thể, ví dụ `weather_forecast` |
| Endpoint | URL mà Client sẽ gọi sau khi discovery |
| Credential | Khóa chứng minh quyền sở hữu Agent ID |
| Heartbeat | Tín hiệu do Agent gửi để chứng minh registration còn hoạt động |
| Lease | Khoảng thời gian Registry tiếp tục coi registration là hợp lệ |

Base URL khi chạy local:

```text
http://127.0.0.1:8000
```

Swagger UI:

```text
http://127.0.0.1:8000/docs
```

## 2. Agent Card

Ví dụ:

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

Các trường:

| Field | Ý nghĩa |
|---|---|
| `agent_id` | ID duy nhất và ổn định của Agent |
| `name` | Tên hiển thị |
| `domain` | Lĩnh vực |
| `description` | Mô tả ngắn |
| `capabilities` | Danh sách chức năng dùng cho discovery |
| `endpoint` | HTTP(S) URL đầy đủ để Client gọi |
| `version` | Phiên bản service |

Registry chuẩn hóa `domain` và `capability` về chữ thường; khoảng trắng và dấu `-` được chuyển thành `_`.

Ví dụ:

```text
Weather-Forecast
→ weather_forecast
```

Registry **không kiểm tra endpoint có thực sự truy cập được hay không** khi đăng ký.

## 3. Register và re-register

### Tạo Agent ID mới

```http
POST /v1/agents
Content-Type: application/json
```

Body là Agent Card đầy đủ.

Nếu ID chưa tồn tại:

- trả HTTP `201`;
- tạo registration;
- Agent trở thành `ONLINE`;
- Registry trả một `credential` mới.

Credential chỉ được trả khi tạo mới và cần được lưu lại.

### Re-register Agent đã có

Gửi lại cùng endpoint:

```http
POST /v1/agents
Authorization: Bearer <credential>
```

với Agent Card đầy đủ.

Re-registration:

- giữ nguyên Agent ID và ownership;
- cập nhật Agent Card, kể cả endpoint;
- tạo lease mới;
- đưa Agent trở lại `ONLINE`.

Nếu ID đã tồn tại nhưng credential thiếu hoặc sai, Registry trả `401`.

## 4. Discovery

Tìm tất cả Agent đang hoạt động:

```http
GET /v1/agents
```

Tìm theo capability:

```http
GET /v1/agents?capability=weather_forecast
```

Tìm theo domain và capability:

```http
GET /v1/agents?domain=weather&capability=weather_forecast
```

Mặc định chỉ các Agent `ONLINE` được trả về.

Để xem cả các trạng thái khác:

```http
GET /v1/agents?active_only=false
```

Nếu không có Agent phù hợp:

```json
[]
```

Một capability có thể có **nhiều Provider Agent**. Registry trả danh sách; Client quyết định dùng provider nào.

## 5. Lookup và status

Lấy đầy đủ thông tin một Agent:

```http
GET /v1/agents/{agent_id}
```

Lấy trạng thái lifecycle:

```http
GET /v1/agents/{agent_id}/status
```

Ví dụ:

```json
{
  "agent_id": "weather-team-a",
  "status": "ONLINE",
  "last_heartbeat": "2026-11-16T09:00:00Z",
  "lease_expires_at": "2026-11-16T09:00:30Z"
}
```

Các trạng thái hiện tại:

- `ONLINE`
- `SUSPECT`
- `UNREACHABLE`
- `UNREGISTERED`

Ý nghĩa và state machine chi tiết nằm trong [Architecture](architecture.md).

## 6. Heartbeat

Provider Agent tự gửi:

```http
POST /v1/agents/{agent_id}/heartbeat
Authorization: Bearer <credential>
```

Heartbeat hợp lệ:

- cập nhật `last_heartbeat`;
- gia hạn lease;
- có thể đưa Agent từ `SUSPECT` về `ONLINE`.

Nếu lease đã hết hoặc Agent đã unregister, heartbeat trả `409`. Khi đó Agent cần **re-register**, không chỉ heartbeat tiếp.

Web Dashboard không heartbeat thay Agent.

## 7. Cập nhật Agent Card

```http
PATCH /v1/agents/{agent_id}
Authorization: Bearer <credential>
Content-Type: application/json
```

Ví dụ đổi endpoint:

```json
{
  "endpoint": "http://192.168.1.20:9005/forecast"
}
```

PATCH chỉ sửa metadata và **không gia hạn lease**.

Muốn cập nhật card đồng thời tạo lease mới, dùng authenticated re-registration qua `POST /v1/agents`.

## 8. Unregister và DELETE

Hai thao tác này khác nhau.

### Graceful unregister

```http
POST /v1/agents/{agent_id}/unregister
Authorization: Bearer <credential>
```

Kết quả:

- Agent chuyển sang `UNREGISTERED`;
- record và ownership vẫn được giữ;
- Agent có thể re-register lại bằng credential cũ.

### Xóa hoàn toàn registration

```http
DELETE /v1/agents/{agent_id}
Authorization: Bearer <credential>
```

Kết quả:

- record bị xóa;
- ownership bị xóa;
- Agent ID có thể được đăng ký lại như một ID mới.

Dashboard hiện dùng DELETE cho thao tác **Hủy đăng ký**.

## 9. Registry health

```http
GET /v1/health
```

Endpoint này kiểm tra Registry và kết nối database.

Nó **không phải health check của Provider Agent**.

## 10. Authentication

Các thao tác làm thay đổi một Agent đã tồn tại cần:

```http
Authorization: Bearer <credential>
```

Credential dùng để bảo vệ ownership của Agent ID.

Credential:

- không xuất hiện trong normal GET/discovery;
- không nên đặt trong URL;
- không phải credential để gọi business API của Provider Agent.

## 11. HTTP errors thường gặp

| HTTP | Ý nghĩa |
|---|---|
| `401` | Credential thiếu hoặc sai |
| `404` | Agent ID không tồn tại |
| `409` | Heartbeat không còn hợp lệ; cần re-register |
| `422` | Dữ liệu request/query không hợp lệ |
| `503` | Registry/database tạm thời không sẵn sàng |

Client nên xử lý theo HTTP status code, không phụ thuộc vào nội dung câu tiếng Anh trong error message.

## 12. Những quy tắc cần nhớ

- GET và refresh Dashboard **không renew lease**.
- PATCH **không renew lease**.
- Normal discovery mặc định chỉ trả `ONLINE`.
- Registration thành công **không chứng minh business endpoint đang reachable**.
- Registry chỉ trả endpoint; business request được Client gửi trực tiếp tới Provider.
- Provider invocation contract là vấn đề riêng, xem [Invocation Contract](invocation_contract.md).
