# Tích hợp Agent bên ngoài — REST trước, SDK tùy chọn

## 1. Các vai trò

Registry là dịch vụ danh bạ. Provider Agent là chương trình HTTP thực hiện nghiệp vụ. Client/consumer là chương trình cần dùng nghiệp vụ đó; client chỉ tiêu thụ không bắt buộc đăng ký. Agent Card là bản mô tả provider. `agent_id` là identity ổn định; `endpoint` là URL operation đầy đủ có thể thay đổi. `domain` là lĩnh vực; `capability` là tên chức năng dùng để tìm kiếm (semantic discovery identifier), không phải đặc tả API. Credential chứng minh quyền quản lý record. Heartbeat là request nền do Agent gửi. Lease là thời hạn Registry chấp nhận tín hiệu gần nhất; không giới hạn tuổi thọ process.

Nhóm cung cấp Registry chạy một server và gửi Registry URL cùng tài liệu này cho các nhóm. Nhóm làm provider không cần sửa code Registry. Nhóm làm consumer dùng URL để discovery, rồi gọi trực tiếp provider. Web chỉ là công cụ quản lý; không phải nơi chạy Agent.

## 2. Chuẩn bị

Một service HTTP đang chạy, Agent Card, Registry URL truy cập được, chỗ lưu credential, vòng heartbeat/recovery và hợp đồng nghiệp vụ. Có thể viết bằng bất kỳ ngôn ngữ hỗ trợ HTTP/JSON. Chạy một process cho mỗi ID/credential. Chuẩn hóa capability/domain: lowercase, whitespace/hyphen thành underscore. Endpoint không chứa username/password/fragment.

## 3. Đăng ký REST bằng PowerShell

```powershell
$registry = 'http://127.0.0.1:8000'
$card = @{
  agent_id='finance-team-a'; name='Finance Agent'; domain='finance'
  description='Demo calculation provider'; capabilities=@('calculate_tax')
  endpoint='http://127.0.0.1:8010/invoke'; version='1.0'
}
$registration = Invoke-RestMethod "$registry/v1/agents" -Method Post -ContentType 'application/json' -Body ($card | ConvertTo-Json)
# Lưu secret, không in response chứa secret vào log.
[IO.File]::WriteAllText((Join-Path $PWD 'finance-team-a.credential'), $registration.credential, [Text.UTF8Encoding]::new($false))
$headers = @{ Authorization = "Bearer $($registration.credential)" }
Invoke-RestMethod "$registry/v1/agents/finance-team-a/heartbeat" -Method Post -Headers $headers
```

POST mới trả 201 gồm card, timestamps UTC, status ONLINE, heartbeat_interval_seconds, ttl_seconds và credential một lần. POST có credential đúng cho ID cũ trả 200, không trả lại credential. Các GET không bao giờ trả khóa/hash. Ví dụ trên minh họa protocol một request; developer phải chạy heartbeat tự động, không yêu cầu người dùng gõ lặp lại.

Nếu chỉ đăng ký card Finance mà không chạy service/heartbeat, sau 20s SUSPECT, 30s UNREACHABLE theo mặc định. Registration không chứng minh business API đã hoạt động.

## 4. SDK Python dùng ở project khác

SDK chỉ phụ thuộc httpx/Pydantic, không import FastAPI hay backend Registry. Từ project bên ngoài dùng Python 3.11+:

```powershell
python -m pip install 'C:\agent-registry'
```

Có thể cài editable khi phát triển: `python -m pip install -e C:\agent-registry`. Không cần publish PyPI. Packaging chỉ gồm `agent_registry_client`, không cài demo/backend. Mã generic tối thiểu (card lấy từ cấu hình của service):

```python
import asyncio
import httpx
from agent_registry_client import registered_agent

async def run_service(card, registry_url, credential_path, serve_business_api):
    async with httpx.AsyncClient(timeout=3, trust_env=False, follow_redirects=False) as http:
        async with registered_agent(card, registry_url, credential_path, http) as lifecycle:
            await serve_business_api()  # Server/framework của nhóm; không cần FastAPI.
```

Trong FastAPI lifespan, đặt `app.state.lifecycle = lifecycle` rồi `yield` thay `await serve_business_api()`. Xem `demo/news_agent.py` cho ví dụ hoàn chỉnh. Context khởi động task register/heartbeat; khi thoát hủy task rồi unregister với deadline 4s. Nó không chặn business API khi Registry tạm unavailable. Có thể dùng RegistryClient.run trực tiếp nếu tự quản lý task/cancel/unregister. Import cũ `demo.registry_client.RegistryClient` vẫn hoạt động trong repo.

## 5. Đăng ký bằng web trước

Mở `/`, đăng ký card, lưu credential vào file UTF-8 không BOM, đặt đúng ID/file credential trong service rồi start service. Web không khởi động process và không chuyển file sang máy provider. Service startup sẽ authenticated re-register và tự heartbeat. Web không heartbeat dù mở hay đóng browser. Cấu hình service là nguồn card chính, có thể ghi đè chỉnh sửa trên web khi re-register.

## 6. Credential và lease

Server sinh secret ngẫu nhiên 256 bit, chỉ lưu hash SHA-256. Không commit/log/đưa token vào URL. Bảo vệ ACL file trên Windows. Credential Registry chỉ dùng quản lý record, không gửi cho business endpoint. Business auth là contract riêng; demo không có.

Mặc định interval=10s, suspect=20s, TTL=30s. Agent heartbeat liên tục có thể chạy vô hạn. Heartbeat còn lease renew; hết lease trả 409 và SDK tự register lại bằng khóa. 408/429/5xx/network retry với backoff/jitter; 401/403/404/422 cần operator. Business API vẫn phục vụ nếu khỏe.

Mất khóa hoặc mất response đầu tiên: không có API lấy lại khóa; operator phải xử lý ownership hoặc chọn ID mới. Xóa DB mất cả ownership; đừng xóa credential rồi tự chiếm ID. Restart Registry với DB cũ giữ timestamps/khóa và không hồi sinh lease hết hạn. `/unregister` giữ identity, DELETE xóa vĩnh viễn. Không tự reset DB khi gặp lỗi.

## 7. Discovery và invocation

```powershell
Invoke-RestMethod "$registry/v1/agents/finance-team-a"
Invoke-RestMethod "$registry/v1/agents?domain=news&capability=search_news"
Invoke-RestMethod "$registry/v1/agents?active_only=false"
```

ID lookup trả cả record không ONLINE. Discovery mặc định chỉ ONLINE; các filter kết hợp AND. Danh sách rỗng là kết quả hợp lệ. Danh sách admin/quan sát tất cả không dùng để chọn provider tự động.

Consumer lấy endpoint từ kết quả; không ghép host/port cài cứng. Xác định contract đã thỏa thuận, gọi trực tiếp, validate response và timeout/failover. `agent_registry_client.discovery.discover` trả danh sách Provider; `invocation.invoke_first` thực hiện convention dưới đây và nhận schema output do caller cung cấp. Hai helper không biết nghiệp vụ Weather/News.

### Common demo invocation v1

Đây là quy ước nội bộ demo, không phải chuẩn quốc tế. Agent Card không quảng bá version protocol riêng: nhóm phải thỏa thuận v1 ngoài Registry, không suy luận từ capability/version service. Agent không hỗ trợ convention cần adapter riêng.

POST đúng full endpoint quảng bá, JSON:

```json
{"capability":"search_news","input":{"keyword":"Hanoi"}}
```

200:

```json
{"agent_id":"news-agent-01","capability":"search_news","output":{"articles":[{"title":"Hanoi travel update","summary":"Hanoi museums welcome visitors this weekend."}]}}
```

| Capability | Input | Output |
|---|---|---|
| weather_forecast | city: string 1–100, mặc định Hanoi | city, temperature_c: finite number, condition, source |
| search_news | keyword: string 1–100 | articles: array của {title, summary}; không tìm thấy trả [] |
| summarize_news | text: string 1–10000 | summary: câu đầu tiên tối đa 240 ký tự |

Không chấp nhận field dư, sai kiểu, chuỗi rỗng/whitespace trong input. Unsupported capability: 400 `detail.code=unsupported_capability`. Sai input: 422, business field có `detail.code=invalid_input`; sai envelope dùng FastAPI validation detail array. Unexpected business failure: HTTP 5xx; consumer không coi là lỗi discovery. Planner validate identity/capability và schema output; provider sai thì thử provider kế tiếp. Không tự retry operation ghi dữ liệu: failover chỉ an toàn cho operation idempotent như demo đọc/tóm tắt này.

Weather giữ GET `/forecast?city=Hanoi`; POST `/forecast` bổ sung cùng endpoint. News POST `/invoke`. Không đổi endpoint thành base URL. Registry không nhận/proxy request nghiệp vụ.

Planner trả `status=complete|partial`, `city`, `weather`, `news`, `providers_used`, `errors`. Lỗi có stage discovery hoặc invocation. CLI exit 1 khi partial nhưng vẫn in kết quả hữu ích; exit 0 khi đầy đủ. Đây là tổng hợp deterministic, không có LLM lập kế hoạch.

## 8. Đổi endpoint và mạng LAN

Dừng bản cũ, giữ ID và credential, đổi WEATHER_ENDPOINT/NEWS_ENDPOINT và port bind rồi restart. SDK re-register cập nhật binding. PATCH endpoint có xác thực cũng được nhưng không renew, cấu hình service phải đổi tương ứng. Consumer discovery lại mỗi lượt, không cache endpoint.

127.0.0.1 luôn trỏ chính máy đang gọi. Provider máy B, client máy C: quảng bá IP/DNS của B, không localhost. Registry và provider dùng `--host 0.0.0.0`, nhưng không quảng bá 0.0.0.0. Registry URL phải là IP/DNS máy Registry. Ví dụ kiểm tra từ máy client:

```powershell
Test-NetConnection 192.168.1.20 -Port 8002
Invoke-RestMethod 'http://192.168.1.20:8002/health'
```

Cho phép inbound đúng port qua firewall theo chính sách nhóm, không tắt toàn bộ firewall. HTTP chỉ dành cho LAN/local tin cậy; Internet cần HTTPS, admission policy/access control. Registry không probe endpoint tùy ý; consumer chỉ gọi provider trong môi trường được tin cậy. ONLINE không bảo đảm endpoint reachable từ mọi client.

## 9. Troubleshooting

| Triệu chứng | Kiểm tra/xử lý |
|---|---|
| 401 | Đúng credential và ID? File có BOM/khóa cũ sau reset DB? Không xóa khóa để thử chiếm lại ID |
| 404 | ID sai hoặc đã DELETE; cần operator, SDK dừng lifecycle |
| 409 | Lease hết/unregistered; authenticated re-register, SDK tự làm |
| 422 | Đúng schema card/JSON, URL, capability, field bắt buộc; business input khác card |
| 503 | Registry/DB tạm lỗi; chờ retry, kiểm tra log và khóa SQLite |
| Registry trả [] | Sai filter hoặc không có ONLINE provider; xem active_only=false |
| Không kết nối endpoint | Sai IP/port, process chưa chạy, firewall hoặc địa chỉ localhost trên máy khác |
| Restart binding vẫn cũ | Kiểm tra endpoint env và file/ID đúng, đọc log re-register; chỉ một process/ID |
| Mất credential | Không lấy lại được hash thành secret; cần operator hoặc ID mới |
| Registry restart | Dùng cùng DB; chờ SDK heartbeat/re-register, không reset dữ liệu |
| Weather chạy nhưng không discovery | /health.registration có thể operator_required/reconnecting; kiểm tra 401/404 và cấu hình Registry URL |
| Planner partial | Xem errors.stage; News có thể vẫn dùng được khi Weather lỗi |

## 10. Giới hạn và bước tiếp

Chưa instance_id/fencing, key rotation, active probe, replication, pagination hoặc benchmark. News chỉ dữ liệu cố định và tóm tắt trích câu đầu; không tin tức live. Chưa kiểm chứng LAN/liên nhóm thực tế hoặc browser E2E. Ba bước sau hợp lý: kiểm thử hai máy với nhóm khác; bổ sung metadata protocol version có compatibility; bảo vệ stale process bằng instance_id/fencing.
