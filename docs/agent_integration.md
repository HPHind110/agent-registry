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
4. nhập Agent Card và join token cho ID mới;
5. lưu credential được cấp;
6. dùng bộ lọc Domain/Capability để kiểm tra Agent đã xuất hiện.

Quan trọng:

> Đăng ký trên Web chỉ tạo registration trong Registry. Nó **không khởi động Agent** và Web **không heartbeat thay Agent**.

Nếu không có Agent process thật gửi heartbeat, registration sẽ dần chuyển khỏi `ONLINE`.

### News Agent: Manual Mode vs SDK Auto Mode

Dùng Registry đang chạy. Các lệnh dưới đây giả sử PowerShell mở ở thư mục project. Mỗi lần chỉ chạy một process News trên cổng 8002. Chọn URL của **cùng một Registry** cho Dashboard, heartbeat và discovery.

**AUTO (mặc định).** Trong terminal Provider:

```powershell
$env:NEWS_REGISTRY_MODE = 'auto'
$env:REGISTRY_URL = 'http://127.0.0.1:8000'
$env:NEWS_ENDPOINT = 'http://127.0.0.1:8002/invoke'
.\.venv\Scripts\python -m uvicorn demo.news_agent:app --host 0.0.0.0 --port 8002
```

SDK đọc `NEWS_CREDENTIAL_FILE` (mặc định `news.credential`), đăng ký hoặc re-register và lưu khóa khi được cấp lần đầu. Sau đó SDK gửi heartbeat, retry khi Registry tạm mất kết nối và re-register nếu lease đã hết. Ctrl+C khiến SDK cố gắng graceful unregister, giữ lại identity và ownership. Khi demo qua nhiều máy, đặt `NEWS_ENDPOINT` thành địa chỉ Consumer truy cập được.

**MANUAL.** Trong terminal Provider:

```powershell
$env:NEWS_REGISTRY_MODE = 'manual'
$env:NEWS_AGENT_ID = 'news-agent-01'
.\.venv\Scripts\python -m uvicorn demo.news_agent:app --host 0.0.0.0 --port 8002
```

1. News phục vụ `POST /invoke` và `GET /health` ngay cả khi Registry chưa chạy. Giá trị `registration: disabled` ở `/health` cho biết lifecycle SDK đã tắt. News không cần `REGISTRY_URL`, `NEWS_ENDPOINT` hay file credential.
2. Mở Dashboard, chọn **Đăng ký Agent**. Điền ID `news-agent-01`, tên `News Agent`, domain `news`, mô tả `Manual REST integration demo`, capabilities `search_news, summarize_news`, version `1.0`. Endpoint là `http://<PROVIDER_IP>:8002/invoke`, thay placeholder bằng IP/DNS mà Consumer truy cập được. Khi tất cả cùng máy có thể dùng `http://127.0.0.1:8002/invoke`.
3. Lưu riêng credential Dashboard cấp một lần. News trả Agent ID trong response, nên ID trên card phải trùng `NEWS_AGENT_ID`. Nếu ID đã có từ demo AUTO, chọn card cũ và **Đăng ký lại** bằng credential cũ, hoặc dùng ID mới cho cả process và card.
4. Từ PowerShell thứ hai trên máy Provider, gửi **một** heartbeat. Nhập credential vào dấu nhắc PowerShell, không nhập vào process News:

```powershell
$registry = 'http://127.0.0.1:8000'  # Dùng URL tunnel nếu Dashboard mở qua tunnel.
$id = 'news-agent-01'
$secret = Read-Host 'Registry credential' -AsSecureString
$headers = @{ Authorization = 'Bearer ' + ([pscredential]::new($id, $secret)).GetNetworkCredential().Password }
Invoke-RestMethod -Method Post -Uri "$registry/v1/agents/$id/heartbeat" -Headers $headers |
    Select-Object status, last_heartbeat, lease_expires_at
```

Một heartbeat chỉ gia hạn lease một lần. Gửi lại theo interval của Registry nếu muốn duy trì discovery. Khi heartbeat trả 409, dùng **Đăng ký lại** với credential cũ rồi tiếp tục. Trong Dashboard, **Sửa card** cập nhật metadata, **Hủy đăng ký** gọi DELETE và xóa cả record lẫn ownership. Dừng News ở MANUAL không thay đổi card; lease sẽ hết nếu bên vận hành ngừng gửi heartbeat.

**Discovery và invocation (dùng chung hai chế độ).** Tại Consumer, đặt URL Registry theo góc nhìn của máy đó và ID đúng với demo. Chạy khi card còn ONLINE:

```powershell
$registry = 'http://127.0.0.1:8000'
$providers = Invoke-RestMethod "$registry/v1/agents?domain=news&capability=search_news"
$news = $providers | Where-Object agent_id -eq 'news-agent-01' | Select-Object -First 1
if (-not $news) { throw 'News Agent is not ONLINE' }
$body = @{ capability = 'search_news'; input = @{ keyword = 'Hanoi' } } | ConvertTo-Json
Invoke-RestMethod -Method Post -Uri $news.endpoint -ContentType 'application/json' -Body $body |
    ConvertTo-Json -Depth 6
```

Consumer nhận hai bài mẫu về Hanoi từ News. Request nghiệp vụ gửi thẳng tới endpoint trong card, không mang credential của Registry. Registry quản lý card, ownership và lease trong cả hai chế độ.

### Onboarding Provider trên Windows

1. Khởi chạy dịch vụ nghiệp vụ của bạn. Chọn endpoint mà máy Consumer có thể gọi. Nếu URL chứa token hoặc thông tin bí mật, hãy tách thông tin đó khỏi URL trước khi công bố card.
2. Mở [Dashboard HTTPS](https://103-180-134-53.sslip.io/), chọn **Đăng ký Agent**, điền card và join token do người vận hành cấp. Nếu đã có ID, chọn **Đăng ký lại** với ownership credential.
3. Trong hộp thoại thành công, tải **credential** và **cấu hình JSON**. Chuyển hai file vào thư mục riêng của tài khoản chạy Provider, ví dụ `$HOME\agent-config`. Đặt cùng thư mục, giữ tên file credential khớp với JSON. Nếu trình duyệt tự thêm `(1)` vào tên file, sửa lại tên hoặc cập nhật đường dẫn. Credential là khóa bí mật duy nhất được cấp cho ID. Cấu hình chứa metadata công khai và đường dẫn khóa. Cả hai cách dưới đây đều dùng được sau khi đóng Dashboard.
4. Nạp JSON trong PowerShell. Đổi `agent-text-team-a.json` thành tên file đã tải:

```powershell
$configPath = Join-Path $HOME 'agent-config\agent-text-team-a.json'
$c = Get-Content -Raw -LiteralPath $configPath | ConvertFrom-Json
$keyPath = Join-Path (Split-Path $configPath) $c.AGENT_CREDENTIAL_FILE
$env:REGISTRY_URL = $c.REGISTRY_URL
$env:AGENT_ID = $c.AGENT_ID
$env:AGENT_ENDPOINT = $c.AGENT_ENDPOINT
$env:AGENT_NAME = $c.AGENT_NAME
$env:AGENT_DESCRIPTION = $c.AGENT_DESCRIPTION
$env:AGENT_VERSION = $c.AGENT_VERSION
$env:AGENT_DOMAIN = $c.AGENT_DOMAIN
$env:AGENT_CAPABILITIES = $c.AGENT_CAPABILITIES -join ','
$env:AGENT_CREDENTIAL_FILE = $keyPath
```

**A. Python SDK.** Trong virtualenv của Provider, cài SDK theo mục 4. Dùng card đầy đủ của dịch vụ (cùng ID, endpoint, domain và capabilities đã đăng ký). Truyền `os.environ["REGISTRY_URL"]` và `os.environ["AGENT_CREDENTIAL_FILE"]` cho `registered_agent`. SDK đọc file, re-register và chạy heartbeat, retry, phục hồi lease. Khi SDK tự tạo ID thay cho Dashboard, truyền thêm `join_token=os.getenv("REGISTRY_JOIN_TOKEN")`. Cấp token qua môi trường riêng, không đặt vào source. Sau khi có file credential, SDK chỉ dùng Bearer cho các lần đăng ký lại.

Ví dụ với News AUTO có sẵn, sau khi nạp JSON:

```powershell
$env:NEWS_AGENT_ID = $c.AGENT_ID
$env:NEWS_ENDPOINT = $c.AGENT_ENDPOINT
$env:NEWS_CREDENTIAL_FILE = $keyPath
$env:NEWS_REGISTRY_MODE = 'auto'
.\.venv\Scripts\python -m uvicorn demo.news_agent:app --host 0.0.0.0 --port 8002
```

Weather dùng `WEATHER_AGENT_ID`, `WEATHER_ENDPOINT`, `WEATHER_CREDENTIAL_FILE` và mặc định cổng 8001. Cả hai dùng `REGISTRY_URL`. Chọn card khớp domain/capabilities cố định của từng demo vì SDK gửi lại card khi startup. File JSON là mẫu tích hợp, demo không tự đọc file.

**B. REST từ bất kỳ ngôn ngữ nào.** Với ID vừa đăng ký trên Web, thử một heartbeat từ máy Provider:

```powershell
$owner = @{ Authorization = 'Bearer ' + [IO.File]::ReadAllText($keyPath).Trim() }
Invoke-RestMethod -Method Post -Uri "$($c.REGISTRY_URL)/v1/agents/$($c.AGENT_ID)/heartbeat" -Headers $owner |
    Select-Object status,last_heartbeat,lease_expires_at
```

Để duy trì qua nhiều lease, ứng dụng tự lên lịch heartbeat theo `heartbeat_interval_seconds`. Với 409, POST lại card đầy đủ kèm Bearer vào `/v1/agents`. Retry có backoff cho sự cố mạng/5xx. Với 401, kiểm tra khóa thuộc đúng ID; với 403 khi tạo ID, hỏi quản trị viên token hiện hành. Gửi POST unregister khi shutdown để giữ ownership. Consumer discovery rồi gọi endpoint trực tiếp. Chỉ gửi khóa cho Registry. Java, Go, JavaScript và Python đều dùng cùng [REST contract](api_contract.md).

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

Ví dụ Provider Echo dùng FastAPI sau khi nạp cấu hình Windows ở trên (khai báo capability `echo_text` trên card):

```python
import os
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI
from agent_registry_client import registered_agent

CARD = {
    "agent_id": os.environ["AGENT_ID"],
    "name": os.environ["AGENT_NAME"],
    "domain": os.environ["AGENT_DOMAIN"],
    "description": os.environ["AGENT_DESCRIPTION"],
    "capabilities": os.environ["AGENT_CAPABILITIES"].split(","),
    "endpoint": os.environ["AGENT_ENDPOINT"],
    "version": os.environ["AGENT_VERSION"],
}

@asynccontextmanager
async def lifespan(app):
    async with httpx.AsyncClient(timeout=3, trust_env=False) as http:
        async with registered_agent(
            CARD,
            os.getenv("REGISTRY_URL", "http://127.0.0.1:8000"),
            os.getenv("AGENT_CREDENTIAL_FILE", "text-team-a.credential"),
            http,
            join_token=os.getenv("REGISTRY_JOIN_TOKEN"),
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

**Trước khi cấu hình URL, phân biệt ba tình huống:**

| Mô hình | `REGISTRY_URL` ở máy gọi | Ý nghĩa |
|---|---|---|
| Registry và Agent/Client cùng máy | `http://127.0.0.1:8000` | Local Registry |
| Registry trên VPS qua SSH tunnel được mở **trên chính máy Agent/Client** | `http://127.0.0.1:18000` (nếu forward cổng 18000) | Chỉ riêng máy đang có tunnel dùng được |
| Registry chung qua mạng | URL HTTPS hoặc private-network URL được cấp | Chỉ áp dụng sau khi thiết lập phương án truy cập an toàn |

**Từ một laptop, tunnel chỉ tạo kết nối tới Registry trên VPS, không làm cho endpoint của Provider ở laptop khác tự truy cập được.** Các nhóm cần kiểm tra cả hai chiều: Agent/Client ↔ Registry và Client → Provider.

Hướng dẫn cụ thể cho VPS, systemd, tunnel, local CLI, cập nhật code: [Deployment & Operations](deployment.md).


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
