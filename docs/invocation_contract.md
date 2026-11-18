# Provider Invocation Contract

[README](../README.md) · [Agent Integration](agent_integration.md) · [Registry API](api_contract.md)

File này trả lời câu hỏi:

> **Sau khi Client đã tìm thấy một Provider trong Registry, Client phải gọi Provider đó như thế nào?**

Đây là **quy ước dùng trong demo của repository**, không phải protocol bắt buộc của Agent Registry.

Registry vẫn có thể đăng ký và discovery một Agent dùng protocol khác.

## 1. Discovery không phải Invocation

Registry chỉ cho Client biết:

```text
Agent nào?
Capability gì?
Endpoint ở đâu?
```

Ví dụ:

```json
{
  "agent_id": "news-agent-01",
  "capabilities": ["search_news"],
  "endpoint": "http://127.0.0.1:8002/invoke"
}
```

Nhưng chỉ từ thông tin đó, Client chưa tự biết đầy đủ:

- dùng GET hay POST;
- request body có field gì;
- response có schema gì;
- lỗi business được biểu diễn thế nào.

Vì vậy Provider và Consumer cần một **invocation contract** riêng.

## 2. Common convention của demo

Demo hiện tại dùng:

```http
POST <endpoint lấy từ Registry>
Content-Type: application/json
```

Request:

```json
{
  "capability": "search_news",
  "input": {
    "keyword": "Hanoi"
  }
}
```

Response thành công:

```json
{
  "agent_id": "news-agent-01",
  "capability": "search_news",
  "output": {
    "articles": [
      {
        "title": "Hanoi travel update",
        "summary": "Hanoi museums welcome visitors this weekend."
      }
    ]
  }
}
```

Ba phần quan trọng của response:

- `agent_id`: Provider nào đã xử lý request;
- `capability`: chức năng vừa được gọi;
- `output`: kết quả business.

Client nên kiểm tra cả ba thay vì tin mọi JSON trả về.

## 3. Client gọi đúng endpoint được discovery

Nếu Registry trả:

```text
http://127.0.0.1:8002/invoke
```

Client gọi đúng URL đó.

Không tự nối thêm:

```text
/invoke
/forecast
/api
```

vì Agent Card hiện lưu **full endpoint**.

Registry credential cũng không được gửi sang Provider business API. Credential Registry chỉ dùng để quản lý registration.

## 4. Các capability demo hiện có

| Provider | Capability | Input | Output |
|---|---|---|---|
| Weather | `weather_forecast` | `city` | city, temperature_c, condition, source |
| News | `search_news` | `keyword` | danh sách article |
| News | `summarize_news` | `text` | summary |

### Weather

Request:

```json
{
  "capability": "weather_forecast",
  "input": {
    "city": "Hanoi"
  }
}
```

Response:

```json
{
  "agent_id": "weather-local",
  "capability": "weather_forecast",
  "output": {
    "city": "Hanoi",
    "temperature_c": 26,
    "condition": "partly_cloudy",
    "source": "demo_static_data"
  }
}
```

### News search

Request:

```json
{
  "capability": "search_news",
  "input": {
    "keyword": "Hanoi"
  }
}
```

Không tìm thấy bài phù hợp vẫn là request thành công:

```json
{
  "articles": []
}
```

### News summary

Request:

```json
{
  "capability": "summarize_news",
  "input": {
    "text": "First sentence. Second sentence."
  }
}
```

Demo hiện chỉ lấy câu đầu để tạo summary. Nó không gọi LLM hoặc nguồn tin ngoài.

## 5. Errors

| Tình huống | Behavior |
|---|---|
| Capability không hỗ trợ | HTTP `400` |
| Business input sai | HTTP `422` |
| Provider lỗi | HTTP `5xx` hoặc lỗi kết nối |
| Response sai JSON/schema | Consumer coi invocation thất bại |

Lỗi đọc Registry ở lần discovery đầu phát sinh `DiscoveryError`. Nếu Registry trả
danh sách rỗng, lần đọc đã thành công và Consumer báo `InvocationError` với
thông điệp `No ONLINE provider`. Cả hai trường hợp đều dừng ngay.

## 6. Nhiều Provider và failover

Một capability có thể có nhiều Provider:

```text
weather-a
weather-b
weather-c
```

Helper `invoke_first` thử lần lượt:

```text
Provider A
   ↓ fail
Provider B
   ↓ success
return result
```

Các lỗi như network, HTTP, JSON hoặc response schema không hợp lệ có thể khiến helper chuyển sang Provider tiếp theo.

Điều này phù hợp với các operation đọc trong demo.

Với operation có side effect như thanh toán hoặc ghi dữ liệu, không nên tự động retry/failover nếu chưa thiết kế idempotency.

### Rediscovery khi binding đã đổi

`invoke_with_rediscovery(..., domain=..., safe_to_retry=True)` discovery rồi thử
các Provider theo thứ tự như trên. Kết quả hợp lệ đầu tiên kết thúc lượt gọi.
Khi tất cả đều lỗi, helper hỏi lại Registry đúng một lần với cùng capability,
domain và bộ lọc ONLINE. Nếu bất kỳ Provider nào trả HTTP 400/422, helper vẫn
thử hết danh sách đầu nhưng bỏ qua rediscovery khi danh sách đó thất bại.

Ví dụ Weather B đổi cổng trong lúc Client đang xử lý một request:

1. Client discovery Weather B ở cổng 8001.
2. B chuyển sang 8010 và re-register thành công với cùng Agent ID.
3. Client gọi endpoint 8001 vừa nhận và gặp lỗi kết nối.
4. Client discovery lại, nhận endpoint 8010 và gọi trực tiếp B tại đó.
5. Client kiểm tra Agent ID, capability và output schema rồi trả kết quả.

Giới hạn cho mỗi capability là **hai lượt discovery và hai lượt thử danh sách
Provider**. Lượt thứ hai có thể thử nhiều binding mới. Mỗi cặp
`(agent_id, endpoint)` chỉ được gọi một lần trong toàn bộ thao tác.

| Kết quả sau lượt invocation đầu thất bại | Consumer trả về |
|---|---|
| Rediscovery tắt hoặc input bị từ chối | `InvocationError` của lượt đầu |
| Đọc lại Registry lỗi | `DiscoveryError` với thông điệp `Rediscovery failed` |
| Danh sách mới rỗng hoặc chỉ có binding đã thử | `InvocationError` với `no new provider binding` |
| Thử hết binding mới vẫn lỗi | `InvocationError` với `Invocation after rediscovery failed` và nguyên nhân tóm tắt của hai lượt |

Registry phải nhận cập nhật binding trước lần discovery thứ hai thì Client mới
nhận được endpoint mới. Consumer chỉ biết địa chỉ Registry trả về. Giao thức
hiện tại không dò IP, không push cập nhật và không chờ Provider re-register.

`safe_to_retry` mặc định là `False` và chỉ điều khiển **lượt bổ sung**. Failover
trong danh sách đầu vẫn có hiệu lực. Nếu timeout xảy ra sau khi Provider đã ghi
dữ liệu, gọi Provider khác có thể thực hiện cùng tác vụ lần nữa. Caller chỉ nên
bật rediscovery khi biết tác vụ an toàn để thực hiện lặp lại.

## 7. Planner Client dùng contract này thế nào?

Planner cần hai capability:

```text
weather_forecast
search_news
```

Flow:

```text
Planner
  ↓ discover weather_forecast
Weather endpoint
  ↓ invoke
Weather result

Planner
  ↓ discover search_news
News endpoint
  ↓ invoke
News result

Planner
  ↓
combine
```

Planner bật rediscovery cho cả hai capability đọc dữ liệu. Nếu một bên lỗi,
Planner vẫn giữ kết quả phần còn lại và trả `status: partial`.

Planner là consumer demo, không phải multi-agent orchestrator.

## 8. Legacy Weather / Travel

Weather vẫn giữ API cũ:

```http
GET /forecast?city=Hanoi
```

để `Travel Client` cũ tiếp tục hoạt động.

Weather đồng thời hỗ trợ POST theo common invocation convention để Planner sử dụng.

Điều này minh họa backward compatibility:

```text
Travel Client
→ GET Weather

Planner Client
→ POST Weather
```

Cả hai đều discovery endpoint qua Registry.

## 9. Giới hạn của convention hiện tại

Agent Card hiện chưa mô tả:

- HTTP method;
- input schema;
- output schema;
- business authentication;
- protocol version riêng.

Vì vậy capability name như `search_news` chỉ giúp **tìm Provider**, chưa đủ để một Client hoàn toàn xa lạ tự suy ra cách gọi Provider.

Trong project hiện tại, Provider và Consumer thống nhất contract ngoài Registry.

Nếu sau này cần interoperability mạnh hơn, có thể mở rộng Agent Card bằng protocol metadata hoặc schema reference.
