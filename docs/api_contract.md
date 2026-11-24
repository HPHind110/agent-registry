# Registry REST API (v1)

**Base URL production:** `https://103-180-134-53.sslip.io` · [Swagger](https://103-180-134-53.sslip.io/docs)

API lưu Agent Card, xác thực quyền sở hữu, theo dõi lease và trả kết quả discovery. Business requests **không đi qua Registry**.

[README](../README.md) · [Provider Onboarding](companion_onboarding.md)

## 1. Agent Card

~~~json
{
  "agent_id": "weather-team-a",
  "name": "Weather Agent",
  "domain": "weather",
  "description": "Forecast provider",
  "capabilities": ["weather_forecast"],
  "endpoint": "http://192.168.1.20:8001/forecast",
  "version": "1.0"
}
~~~

`agent_id` là định danh ổn định; `endpoint` là URL nghiệp vụ đầy đủ. `domain` và `capabilities` được chuẩn hóa về chữ thường; khoảng trắng/dấu gạch ngang thành `_`. `capabilities` là danh sách không rỗng. Endpoint là HTTP(S) URL, không chứa username/password hay fragment. Registry không chủ động gọi thử URL này.

## 2. Các endpoint

| Method | Path | Mục đích / xác thực |
|---|---|---|
| `POST` | `/v1/agents` | Tạo mới: full card + header Join Token → `201` và credential một lần. Đăng ký lại: full card + Bearer → `200`. |
| `GET` | `/v1/agents` | Discovery; bộ lọc `capability`, `domain`, `active_only`. |
| `GET` | `/v1/agents/{agent_id}` | Lookup full card và runtime metadata, kể cả Agent offline. |
| `GET` | `/v1/agents/{agent_id}/status` | `status`, `last_heartbeat`, `lease_expires_at`. |
| `POST` | `/v1/agents/{agent_id}/heartbeat` | Bearer; gia hạn lease đang hợp lệ. |
| `PATCH` | `/v1/agents/{agent_id}` | Bearer; cập nhật một phần card, **không** gia hạn lease. |
| `POST` | `/v1/agents/{agent_id}/unregister` | Bearer; rút registration, **giữ ID và ownership**. |
| `DELETE` | `/v1/agents/{agent_id}` | Bearer; xóa record **và ownership**. |
| `GET` | `/v1/health` | Kiểm tra Registry và kết nối database. |

### Tạo ID mới

~~~http
POST /v1/agents
X-Registry-Join-Token: <join-token>
Content-Type: application/json
~~~

Body là Agent Card đầy đủ. Token được quản trị viên cấp riêng; thiếu/sai trả `403`. Production không có token cấu hình thì từ chối tạo ID mới (`503`). Khi tạo thành công, response chứa `credential` **chỉ một lần**; giữ file này ngoài Git.

### Re-register / heartbeat

~~~http
POST /v1/agents
Authorization: Bearer <ownership-credential>
Content-Type: application/json
~~~

Gửi full card. Re-register giữ `agent_id` và ownership, cập nhật binding và tạo lease mới, kể cả sau khi hết hạn/unregister. Join Token **không thay thế credential** của ID đã tồn tại.

~~~http
POST /v1/agents/{agent_id}/heartbeat
Authorization: Bearer <ownership-credential>
~~~

Heartbeat trả `409` khi lease đã hết hoặc Agent đã unregister; phải authenticated re-register trước khi heartbeat tiếp. GET và PATCH **không** renew lease.

### Discovery / lookup

~~~http
GET /v1/agents?capability=weather_forecast&domain=weather
GET /v1/agents?active_only=false
GET /v1/agents/weather-team-a/status
~~~

`GET /v1/agents` mặc định chỉ trả Agent `ONLINE`, danh sách rỗng là `[]`. `active_only=false` gồm cả registration ở các trạng thái khác. Nhiều Provider có thể cùng capability. `GET /v1/agents/{id}` có thể trả Agent không ONLINE.

## 3. Lease và trạng thái

Mặc định heartbeat mỗi **10 giây**, ngưỡng nghi ngờ **20 giây**, TTL **30 giây** (có thể đổi bằng cấu hình server).

| Trạng thái | Ý nghĩa |
|---|---|
| `ONLINE` | Lease còn hạn và heartbeat đủ mới. |
| `SUSPECT` | Heartbeat trễ nhưng chưa hết lease. |
| `UNREACHABLE` | Lease hết hạn; không khẳng định process đã chết. |
| `UNREGISTERED` | Provider chủ động rút đăng ký; ownership vẫn giữ. |

Response khi đăng ký có `heartbeat_interval_seconds` và `ttl_seconds`; nên dùng giá trị server trả, không hard-code. Xem [Architecture](architecture.md).

## 4. Authentication và lỗi

- **Join Token**: chỉ để được phép tạo ID mới, truyền qua `X-Registry-Join-Token` trên HTTPS.
- **Ownership credential**: Bearer chỉ để thao tác lên **ID của chính Provider**; không nằm trong discovery.
- **Business authentication**: do Provider tự quy định; không dùng hai khóa Registry ở trên.

| HTTP | Cách hiểu |
|---|---|
| `401` | Thiếu/sai ownership credential. |
| `403` | Join Token thiếu/sai khi tạo ID mới. |
| `404` | Agent ID không tồn tại. |
| `409` | Heartbeat hết hiệu lực, cần re-register. |
| `422` | Card/query không hợp lệ. |
| `408`, `429`, `5xx` | Lỗi có thể tạm thời; client cần retry có kiểm soát. |
| `503` | DB không sẵn sàng hoặc tạo ID mới đang bị khóa. |

Không gửi secret trong URL, log hay ảnh chụp. Dashboard thao tác **Hủy đăng ký** hiện dùng DELETE (khác graceful unregister).

**Quan trọng:** Registry health không phải health của Provider; registration thành công không đảm bảo HTTP business endpoint reachable.

[Invocation Contract](invocation_contract.md) · [Tích hợp nâng cao](agent_integration.md)
