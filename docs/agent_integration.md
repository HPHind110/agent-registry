# Tích hợp Agent với Registry

[README](../README.md) · [Registry API](api_contract.md) · [Invocation Contract](invocation_contract.md)

Mục tiêu của file này là trả lời một câu hỏi:

> **Nếu nhóm khác đã có một Agent, họ cần làm gì để Agent đó xuất hiện và được tìm thấy trong Registry?**

Không cần sửa source code Registry.

## 1. Trước hết: Agent của bạn là Provider hay Consumer?

### Provider Agent

Provider là Agent **cung cấp một chức năng cho Agent khác**.

Ví dụ:

```text
Weather Agent
capability = weather_forecast
```

Provider cần:

1. có business API riêng;
2. có Agent Card;
3. register với Registry;
4. tự gửi heartbeat;
5. giữ credential để update/re-register/unregister.

### Consumer / Client

Consumer là chương trình **đi tìm và sử dụng Provider Agent**.

Consumer:

1. hỏi Registry theo capability/domain;
2. nhận Agent Card + endpoint;
3. gọi trực tiếp Provider Agent.

Consumer không bắt buộc phải đăng ký nếu bản thân nó không cung cấp dịch vụ cho Agent khác.

## 2. Agent Card cần chuẩn bị

Ví dụ một Text Agent:

```json
{
  "agent_id": "text-team-a",
  "name": "Text Agent",
  "domain": "text",
  "description": "Simple text processing provider",
  "capabilities": ["echo_text"],
  "endpoint": "http://192.168.1.20:8010/invoke",
  "version": "1.0"
}
```

Ý nghĩa:

- `agent_id`: identity ổn định của Agent;
- `domain`: lĩnh vực;
- `capabilities`: Agent làm được gì;
- `endpoint`: Client phải gọi ở đâu.

Nếu Agent restart ở địa chỉ khác, giữ nguyên `agent_id` và cập nhật `endpoint`.

## 3. Cách dễ nhất để thử: Web Dashboard

Để kiểm tra nhanh một Agent Card:

1. chạy Registry;
2. mở Web Dashboard;
3. bấm **Đăng ký Agent**;
4. nhập Agent Card;
5. lưu credential được cấp;
6. dùng bộ lọc Domain/Capability để kiểm tra Agent đã xuất hiện.

Quan trọng:

> Đăng ký trên Web chỉ tạo registration trong Registry. Nó **không khởi động Agent** và Web **không heartbeat thay Agent**.

Nếu không có Agent process thật gửi heartbeat, registration sẽ dần chuyển khỏi `ONLINE`.

## 4. Provider bằng Python SDK

Với Python, cách khuyến nghị là dùng package `agent_registry_client`.

### Cài SDK

Cài trực tiếp từ repository:

```powershell
python -m pip install "git+https://github.com/HPHind110/agent-registry.git"
```

Nếu đang phát triển ngay trong repository đã clone:

```powershell
python -m pip install -e .
```

SDK chỉ hỗ trợ tích hợp Registry; Agent của nhóm vẫn tự chọn framework business API của mình.

### Lifecycle tối thiểu

Ví dụ Provider dùng FastAPI:

```python
import os
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI
from agent_registry_client import registered_agent

CARD = {
    "agent_id": "text-team-a",
    "name": "Text Agent",
    "domain": "text",
    "description": "Simple text processing provider",
    "capabilities": ["echo_text"],
    "endpoint": "http://127.0.0.1:8010/invoke",
    "version": "1.0",
}

@asynccontextmanager
async def lifespan(app):
    async with httpx.AsyncClient(timeout=3, trust_env=False) as http:
        async with registered_agent(
            CARD,
            os.getenv("REGISTRY_URL", "http://127.0.0.1:8000"),
            "text-team-a.credential",
            http,
        ):
            yield

app = FastAPI(lifespan=lifespan)

@app.post("/invoke")
async def invoke(body: dict):
    return {
        "agent_id": CARD["agent_id"],
        "capability": "echo_text",
        "output": body.get("input", {}),
    }
```

Khi process start, SDK tự:

```text
register
   ↓
heartbeat định kỳ
   ↓
renew lease
   ↓
retry khi Registry tạm lỗi
   ↓
re-register nếu lease đã hết
```

Khi shutdown bình thường, SDK cố gắng unregister.

## 5. Credential

Khi Agent ID được tạo lần đầu, Registry trả một credential.

Credential dùng để chứng minh:

> “Tôi là owner của Agent ID này.”

Nó cần cho:

- re-registration;
- heartbeat;
- update;
- unregister;
- DELETE.

Không commit credential lên Git.

Nếu đăng ký bằng Web trước, hãy lưu credential vào file rồi cấu hình Provider sử dụng đúng file đó.

Registry hiện không có API lấy lại credential đã mất.

## 6. Provider không dùng Python

Python SDK chỉ là tiện ích.

Agent viết bằng Java, JavaScript, Go hoặc ngôn ngữ khác vẫn tích hợp được bằng REST:

```text
POST /v1/agents
POST /v1/agents/{id}/heartbeat
POST /v1/agents/{id}/unregister
```

Provider cần tự triển khai vòng:

```text
startup
  ↓
register
  ↓
heartbeat định kỳ
  ↓
nếu 409 → authenticated re-register
  ↓
shutdown → unregister
```

Chi tiết request/response xem [Registry API](api_contract.md).

## 7. Consumer: tìm Provider

Consumer không cần biết trước IP/port của Provider.

Ví dụ tìm Agent có capability `echo_text`:

```http
GET /v1/agents?domain=text&capability=echo_text
```

Registry trả một danh sách Provider `ONLINE`.

Consumer lấy endpoint trong kết quả rồi gọi trực tiếp:

```text
Consumer
   │
   │ discovery
   ▼
Registry
   │
   │ endpoint
   ▼
Consumer ─────────────► Provider
        business call
```

Đây là điểm quan trọng:

> **Discovery và Invocation là hai bước khác nhau.**

Registry không proxy business request.

## 8. Consumer bằng Python helper

Nếu Provider dùng common invocation convention của repository:

```python
import httpx
from agent_registry_client.invocation import invoke_with_rediscovery

with httpx.Client(timeout=5, trust_env=False) as http:
    output, provider_id = invoke_with_rediscovery(
        http,
        "http://127.0.0.1:8000",
        "echo_text",
        {"text": "Hello"},
        output_schema=YourOutputModel,
        domain="text",
        safe_to_retry=True,  # echo_text chỉ trả lại dữ liệu đầu vào.
    )
```

`YourOutputModel` là schema business do Provider và Consumer tự thống nhất.

Mặc định `safe_to_retry=False` chỉ thử danh sách đầu. Với phép đọc an toàn,
bật tùy chọn này cho phép một lượt discovery bổ sung nếu các Provider đều lỗi.
SDK chỉ gọi các cặp Agent ID và endpoint chưa thử. HTTP 400/422 ngăn lượt bổ
sung khi failover ban đầu thất bại. Consumer có thể tiếp tục dùng `discover()`
và `invoke_first()` để tự quản lý hai bước. Dùng HTTP client riêng cho Consumer,
giữ credential quản lý registration trong chương trình Provider.

Nếu Provider không dùng convention này, Consumer có thể discovery bằng Registry rồi gọi endpoint theo protocol riêng.

Xem [Invocation Contract](invocation_contract.md).

## 9. Khi endpoint thay đổi

Ví dụ Agent ban đầu:

```text
text-team-a
→ http://192.168.1.20:8010/invoke
```

sau restart chuyển sang:

```text
text-team-a
→ http://192.168.1.20:9010/invoke
```

Giữ:

- cùng Agent ID;
- cùng credential;

và re-register với endpoint mới.

Consumer discovery lần tiếp theo sẽ nhận binding mới, không cần sửa hard-code URL.

## 10. Chạy trên nhiều máy

Khi tất cả chạy trên cùng máy, `127.0.0.1` là đủ.

Khi chạy trên nhiều máy:

```text
Máy A: Registry
Máy B: Provider
Máy C: Consumer
```

thì:

- Provider phải quảng bá IP/DNS mà máy C truy cập được;
- `REGISTRY_URL` phải trỏ tới máy A;
- server cần bind `0.0.0.0` nếu nhận kết nối LAN;
- **không quảng bá `0.0.0.0` làm endpoint**;
- firewall phải cho phép đúng port cần thiết.

Ví dụ:

```text
Registry: http://192.168.1.10:8000
Provider endpoint: http://192.168.1.20:8010/invoke
```

`127.0.0.1` trên máy C luôn là **máy C**, không phải máy B.

## 11. Troubleshooting nhanh

| Hiện tượng | Ý nghĩa / kiểm tra |
|---|---|
| `401` | Credential thiếu hoặc sai |
| `404` | Agent ID không còn tồn tại |
| `409` heartbeat | Lease đã hết hoặc Agent đã unregister; cần re-register |
| `422` | Agent Card hoặc request không đúng schema |
| Discovery trả `[]` | Không có Provider `ONLINE` phù hợp hoặc filter sai |
| Agent chạy nhưng không xuất hiện | Kiểm tra Registry URL, credential và lifecycle task |
| Endpoint cũ | Kiểm tra Agent đã re-register với endpoint mới chưa |
| Web đăng ký xong nhưng Agent thành UNREACHABLE | Chưa có Agent process thật gửi heartbeat |

## 12. Checklist tích hợp cho nhóm khác

Provider:

- [ ] Business API chạy được độc lập.
- [ ] Có Agent ID ổn định.
- [ ] Có domain và capability rõ ràng.
- [ ] Endpoint truy cập được từ Consumer.
- [ ] Register được với Registry.
- [ ] Credential được lưu an toàn.
- [ ] Heartbeat chạy tự động.
- [ ] Restart cùng ID có thể re-register.
- [ ] Endpoint thay đổi được cập nhật vào Registry.

Consumer:

- [ ] Chỉ biết Registry URL và capability cần dùng.
- [ ] Không hard-code Provider endpoint.
- [ ] Discovery trước khi invocation.
- [ ] Có timeout và xử lý provider unavailable.
- [ ] Validate response theo contract đã thống nhất.

Chi tiết kiến trúc xem [Architecture](architecture.md). Phạm vi kiểm thử xem [Verification](verification.md).
