# Provider Invocation Contract

[README](../README.md) · [Registry API](api_contract.md) · [Agent Integration](agent_integration.md)

## 1. Phạm vi và convention

Đây là common invocation convention v1 của demo và SDK helper, **không phải chuẩn universal hoặc yêu cầu của Registry backend**. Provider dùng protocol khác vẫn đăng ký/discovery được, nhưng consumer phải có adapter phù hợp.

Agent Card chỉ công bố capability và một full endpoint. Nó chưa mô tả HTTP method, request/response schema, business authentication hoặc protocol version; `version` hiện là phiên bản service. Các nhóm phải thống nhất convention ngoài Registry.

Consumer POST vào **đúng endpoint trong card**, không tự nối `/invoke` hoặc `/forecast`. Registry credential không được gửi tới business endpoint. Các demo chưa có business authentication.

## 2. Request / response envelope

Request:

```json
{"capability": "search_news", "input": {"keyword": "Hanoi"}}
```

Response HTTP 200, ví dụ rút gọn:

```json
{
  "agent_id": "news-agent-01",
  "capability": "search_news",
  "output": {
    "articles": [
      {"title": "Hanoi travel update", "summary": "Hanoi museums welcome visitors this weekend."}
    ]
  }
}
```

Envelope request gồm capability (chuỗi strip, 1–100 ký tự) và input (object); không nhận trường thừa. Output là object; response identity/capability phải trùng provider/request. Capability trong invocation cần đúng tên đã thỏa thuận; không áp dụng normalization của Registry để tự đổi tên request.

Helper `invoke_first` validate envelope, Agent ID, capability và output theo Pydantic model do consumer cung cấp. Helper không tự biết schema của mọi capability.

## 3. Demo capabilities

| Provider / endpoint mặc định | Capability | Input | Output |
|---|---|---|---|
| Weather: POST `http://127.0.0.1:8001/forecast` | weather_forecast | city: chuỗi 1–100, mặc định Hanoi | city, temperature_c, condition, source |
| News: POST `http://127.0.0.1:8002/invoke` | search_news | keyword: chuỗi 1–100 | articles: array các object title/summary |
| News: cùng endpoint | summarize_news | text: chuỗi 1–10000 | summary: chuỗi không rỗng |

POST business input dùng strict validation, strip chuỗi, không nhận field thừa hoặc chuỗi chỉ whitespace. Weather trả nhiệt độ 26, condition partly_cloudy, source demo_static_data. Schema consumer yêu cầu temperature_c là số hữu hạn và các chuỗi output Weather không rỗng.

News tìm substring không phân biệt hoa thường trong title/summary của ba bài mẫu; không có kết quả trả articles rỗng và vẫn thành công. Tóm tắt lấy câu đầu (tách theo dấu chấm/chấm hỏi/chấm than theo sau bởi whitespace), cắt tối đa 240 ký tự. Không gọi nguồn tin trực tiếp hoặc LLM.

## 4. Errors và failover

| Tình huống | Response provider |
|---|---|
| Capability không hỗ trợ | 400, detail.code = unsupported_capability |
| Business input không hợp lệ | 422, detail.code = invalid_input, kèm errors |
| Envelope sai | 422, detail array của FastAPI |
| Lỗi HTTP/service khác | Consumer xử lý theo HTTP response thực tế |

`invoke_first` thử provider theo thứ tự danh sách. Lỗi mạng, HTTP, JSON, envelope, identity/capability hoặc business schema khiến helper thử provider tiếp theo; hết provider thì ném InvocationError. Discovery lỗi có DiscoveryError riêng. Timeout do caller thiết lập; Planner dùng 5s/request, không follow redirect, không đọc cấu hình proxy từ môi trường.

Failover không cung cấp exactly-once hoặc idempotency key. Không dùng mặc định này cho operation có side effect nếu chưa thống nhất cách chống thực thi lặp.

## 5. Planner output

Planner discovery `weather_forecast`/domain weather rồi `search_news`/domain news, gọi từng capability trực tiếp. Hai phần được xử lý lỗi độc lập, không phải workflow chạy song song.

Output gồm:

| Field | Ý nghĩa |
|---|---|
| city | Thành phố đầu vào |
| status | complete nếu không có lỗi; partial nếu có bất kỳ lỗi nào, kể cả cả hai phần lỗi |
| weather | Forecast đã validate hoặc null |
| news | Danh sách bài tìm được, hoặc [] nếu lỗi/không có kết quả |
| providers_used | Các object agent_id/capability đã thành công |
| errors | Theo phần weather/news, có stage discovery hoặc invocation và message |

CLI vẫn in JSON khi partial, exit code 1; complete exit 0. articles rỗng không tự tạo lỗi. Planner không cache binding, không hard-code địa chỉ provider, không phải multi-agent orchestrator.

## 6. Legacy Weather / Travel

Weather giữ `GET /forecast?city=Hanoi` với city mặc định Hanoi, length 1–100. Response GET là forecast trực tiếp, không envelope:

```json
{"city":"Hanoi","temperature_c":26,"condition":"partly_cloudy","source":"demo_static_data"}
```

Travel discovery domain weather/capability weather_forecast, GET đúng endpoint được trả về, thêm city query. Nó có timeout/failover HTTP/JSON nhưng **chưa validate business schema forecast**. POST Weather là phần bổ sung; không bắt Travel chuyển sang convention mới.

## 7. Provider health

Weather và News có `GET /health`, trả live=true, ready=true và registration state. State SDK có thể starting, registered, reconnecting, operator_required, unregistered; disabled khi lifecycle không chạy.

Ready hiện là giá trị cố định trong demo, không phải kiểm tra dependency thật. State registration không đồng nhất với ONLINE của Registry. Registry không gọi endpoint này. Phạm vi test xem [Verification](verification.md).
