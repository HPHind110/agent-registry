# Discovery và Provider Invocation

Registry trả metadata và endpoint; **không tự thực thi nghiệp vụ**. Tài liệu này mô tả **quy ước của các demo Weather/News/Planner**, không phải protocol bắt buộc với mọi Provider.

[README](../README.md) · [Registry API](api_contract.md) · [Tích hợp Agent](agent_integration.md)

## 1. Discovery khác Invocation

Ví dụ Client hỏi:

~~~http
GET /v1/agents?capability=search_news
~~~

Registry trả một hoặc nhiều Agent `ONLINE` có `endpoint`. Client vẫn cần biết **HTTP method, input/output schema và business authentication** từ Provider; Agent Card hiện chưa mô tả các phần này.

**Không tự nối `/invoke` hoặc `/forecast`** vào endpoint của card. Registry lưu URL nghiệp vụ **đầy đủ**. Không gửi ownership credential của Registry sang Provider.

## 2. Quy ước POST JSON của demo

Một số Provider mẫu hỗ trợ:

~~~http
POST <endpoint-discovered>
Content-Type: application/json
~~~

~~~json
{
  "capability": "search_news",
  "input": {"keyword": "Hanoi"}
}
~~~

Response:

~~~json
{
  "agent_id": "news-agent-01",
  "capability": "search_news",
  "output": {"articles": []}
}
~~~

Consumer cần xác minh `agent_id`, `capability` và schema `output`. Trường `output` có cấu trúc khác nhau tùy capability.

| Demo | Capability | Input chính |
|---|---|---|
| Weather | `weather_forecast` | `city` |
| News | `search_news` | `keyword` |
| News | `summarize_news` | `text` |

Weather còn có legacy `GET /forecast?city=...` cho Travel Client. Hai demo Agent độc lập (File Organizer, Study Planner) sử dụng API riêng, **không** bắt buộc theo envelope trên.

## 3. Nhiều Provider, lỗi và rediscovery

`invoke_first(...)` trong `agent_registry_client/invocation.py` thử các Provider trong danh sách, xác minh response theo schema caller cung cấp. Hành vi này phục vụ tác vụ **an toàn khi gọi lặp lại**. HTTP 400/422 thường là input không hợp lệ; lỗi mạng/5xx hoặc response sai có thể dẫn đến thử Provider khác.

`invoke_with_rediscovery(..., safe_to_retry=True)` có thể discovery lại **tối đa một lần** sau khi thử hết các binding ban đầu mà không thành công, và chỉ thử các cặp `(agent_id, endpoint)` chưa gọi. Nếu lượt trước có HTTP 400/422, helper không rediscovery; lần đọc lại Registry lỗi sẽ báo `DiscoveryError`.

**Cảnh báo:** failover ngay trong lượt đầu vẫn có thể gọi tác vụ trên nhiều Provider; `safe_to_retry` chỉ bật/tắt lượt rediscovery bổ sung. Không dùng tự động cho thanh toán, ghi dữ liệu hay tác vụ có side effect nếu chưa có idempotency.

## 4. Client cần tự xử lý

- Không có Provider `ONLINE` → thông báo không có dịch vụ, không đoán URL.
- Provider không reachable → timeout và báo lỗi/đổi provider theo chính sách nghiệp vụ.
- Response sai schema → coi như invocation thất bại.
- Endpoint `127.0.0.1` chỉ dùng được khi Client và Provider chạy cùng máy.
- Invocation contract, business token và quyền truy cập mạng phải do các nhóm Provider/Consumer thống nhất.

**Registry không phải Message Broker hoặc API Gateway.** [Architecture](architecture.md)
