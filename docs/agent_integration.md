# Agent Integration

[README / chạy demo](../README.md) · [Registry API](api_contract.md) · [Invocation Contract](invocation_contract.md)

Provider Agent cung cấp nghiệp vụ và duy trì registration. Client / Consumer chỉ tìm và gọi provider; không cần đăng ký nếu không cung cấp dịch vụ. Nhóm vận hành Registry cung cấp Registry URL; nhóm tích hợp không cần sửa source Registry.

## 1. Provider integration — chuẩn bị

Cần một HTTP service, Agent ID ổn định, Agent Card, Registry URL truy cập được, nơi lưu credential bền vững và contract nghiệp vụ đã thỏa thuận với consumer. Có thể dùng bất kỳ ngôn ngữ hỗ trợ HTTP/JSON.

Endpoint là URL operation đầy đủ, không phải chỉ base URL. Một ID/credential chỉ dùng cho một process đang chạy; chưa có instance fencing. Xem giới hạn field/normalization trong [API Contract](api_contract.md).

### Đăng ký bằng REST

Ví dụ PowerShell tạo card cho một service do nhóm tự triển khai; lệnh này **không tạo/chạy service**. Chỉ dùng lần đầu với ID mới và file credential chưa tồn tại:

```powershell
$registry = 'http://127.0.0.1:8000'
$keyPath = Join-Path $PWD 'echo-team-a.credential'
if (Test-Path -LiteralPath $keyPath) { throw 'Credential file already exists; use re-registration.' }
$card = @{
  agent_id='echo-team-a'; name='Echo Agent'; domain='text'
  description='Echo text'; capabilities=@('echo_text')
  endpoint='http://127.0.0.1:8010/invoke'; version='1.0'
}
$registration = Invoke-RestMethod "$registry/v1/agents" -Method Post -ContentType 'application/json' -Body ($card | ConvertTo-Json)
[IO.File]::WriteAllText($keyPath, $registration.credential, [Text.UTF8Encoding]::new($false))
```

Không in response chứa credential ra log. 201 trả credential một lần; authenticated re-registration trả 200 và không cấp lại khóa.

Với record đã có, đọc khóa và gửi lại card đầy đủ:

```powershell
$token = [IO.File]::ReadAllText($keyPath).Trim()
$headers = @{ Authorization = "Bearer $token" }
Invoke-RestMethod "$registry/v1/agents" -Method Post -Headers $headers -ContentType 'application/json' -Body ($card | ConvertTo-Json)
```

Provider tự triển khai REST phải gửi POST `/v1/agents/{agent_id}/heartbeat` ở background theo interval trả về; không yêu cầu operator gửi thủ công mỗi lease. Xử lý 409 bằng re-registration, lỗi tạm thời bằng retry, và unregister khi shutdown. SDK bên dưới cung cấp vòng này.

## 2. Minimal Provider Example — Python SDK

SDK yêu cầu Python 3.11+, chỉ phụ thuộc httpx/Pydantic. Từ môi trường Python của project bên ngoài:

```powershell
python -m pip install C:\agent-registry
python -m pip install fastapi uvicorn
```

Lệnh thứ hai phục vụ ví dụ FastAPI, không phải dependency bắt buộc của SDK. Package chỉ cài `agent_registry_client`, không cài Registry hoặc demo. Có thể dùng editable install khi phát triển.

Lưu ví dụ sau thành `provider.py` trong project của nhóm:

```python
import os
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from agent_registry_client import registered_agent

CARD = {
    "agent_id": "echo-team-a",
    "name": "Echo Agent",
    "domain": "text",
    "description": "Echo text",
    "capabilities": ["echo_text"],
    "endpoint": "http://127.0.0.1:8010/invoke",
    "version": "1.0",
}

class EchoInput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    text: str = Field(min_length=1)

class Invocation(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    capability: str
    input: EchoInput

@asynccontextmanager
async def lifespan(app):
    async with httpx.AsyncClient(timeout=3, trust_env=False) as http:
        async with registered_agent(
            CARD,
            os.getenv("REGISTRY_URL", "http://127.0.0.1:8000"),
            "echo-team-a.credential",
            http,
        ) as lifecycle:
            app.state.lifecycle = lifecycle
            yield

app = FastAPI(lifespan=lifespan)

@app.post("/invoke")
async def invoke(request: Invocation):
    if request.capability != "echo_text":
        raise HTTPException(400, detail={"code": "unsupported_capability"})
    return {
        "agent_id": CARD["agent_id"],
        "capability": "echo_text",
        "output": {"text": request.input.text},
    }
```

Chạy trong cùng thư mục chứa file credential nếu đã đăng ký REST trước:

```powershell
$env:REGISTRY_URL = 'http://127.0.0.1:8000'
python -m uvicorn provider:app --port 8010
```

Nếu chưa có registration/file, SDK tự tạo registration và lưu credential. Nếu đã đăng ký qua REST/web, phải dùng đúng ID/file. Ví dụ minh họa một capability mới, không phải module có sẵn trong repo; contract Echo do ví dụ tự định nghĩa.

## 3. Credential và đăng ký trên web

SDK đọc file UTF-8 lúc startup; khi tạo mới, ghi credential bằng exclusive create, không overwrite file cũ. Dùng đường dẫn bền vững/absolute nếu working directory có thể đổi. Không commit secret; hạn chế quyền đọc file, kiểm tra ACL thư mục trên Windows. Registry chỉ giữ hash, không có API lấy lại khóa.

Flow web:

1. Mở dashboard, chọn **Đăng ký Agent**, điền card đúng với cấu hình service.
2. Lưu credential được hiển thị một lần vào file UTF-8 không BOM, chỉ chứa khóa.
3. Cấp đúng file và Agent ID cho chương trình provider.
4. Start provider; SDK re-register rồi tự heartbeat.
5. Đóng browser vẫn không ảnh hưởng lifecycle.

Refresh trang không renew lease. Nút **Đăng ký lại** là mutation chủ động tạo lease mới, không phải heartbeat tự động. Nút **Hủy đăng ký** hiện gọi DELETE và xóa ownership; không tương đương soft unregister.

Mất file khóa hoặc mất response cấp khóa lần đầu chưa có recovery API. Không thể suy ra secret từ hash. Cần operator xử lý hoặc dùng ID mới; không reset toàn bộ DB để chữa riêng một registration.

## 4. Automatic heartbeat, recovery và shutdown

`registered_agent` bắt đầu task nền; business API không phải đợi Registry đăng ký xong. SDK register lúc startup, lấy heartbeat interval từ response và gửi heartbeat định kỳ. Thành công renew lease; Agent có thể chạy qua nhiều chu kỳ TTL.

| Tình huống | SDK hiện xử lý |
|---|---|
| Heartbeat còn lease | Renew; SUSPECT có thể trở lại ONLINE |
| Heartbeat trả 409 | Gửi lại card cùng credential để re-register |
| Lỗi mạng, 408/429/5xx | Retry exponential backoff có jitter, tiếp tục phục vụ business API |
| 401/403/404/422 và 4xx không retry khác | Dừng lifecycle với operator_required, không tự chiếm ID |
| File credential không đọc/lưu được | operator_required |
| Thoát context / Ctrl+C | Hủy task, cố gắng POST unregister trong tối đa 4s |

Retry timing không thay TTL của Registry. Không dùng `--lifespan off`; không chạy nhiều worker dùng chung ID. Registry restart với DB cũ giữ ownership/timestamp. Nếu DB bị xóa, token cũ không tự được chấp nhận cho ID mới.

## 5. Cấu hình các chương trình có sẵn

Các chương trình đọc biến môi trường process; `.env.example` không tự được nạp. Trong PowerShell dùng `$env:TEN_BIEN = 'gia_tri'`.

| Biến | Chương trình | Mặc định |
|---|---|---|
| REGISTRY_DATABASE_URL | Registry | sqlite:///./registry.db |
| REGISTRY_HEARTBEAT_SECONDS | Registry | 10 |
| REGISTRY_TTL_SECONDS | Registry | 30 |
| REGISTRY_SUSPECT_SECONDS | Registry | (heartbeat + TTL) / 2 nếu không đặt |
| REGISTRY_URL | Providers, Travel, Planner | http://127.0.0.1:8000 |
| WEATHER_AGENT_ID | Weather | weather-local |
| WEATHER_ENDPOINT | Weather | http://127.0.0.1:8001/forecast |
| WEATHER_CREDENTIAL_FILE | Weather | weather.credential |
| NEWS_AGENT_ID | News | news-agent-01 |
| NEWS_ENDPOINT | News | http://127.0.0.1:8002/invoke |
| NEWS_CREDENTIAL_FILE | News | news.credential |
| AGENT_RETRY_MAX_SECONDS | Weather, News | 10 |

Registry yêu cầu `0 < heartbeat < suspect < TTL`; heartbeat/TTL là số nguyên giây. Retry max là số dương, giới hạn khoảng backoff chứ không giới hạn số lần thử. Các biến demo không tự được SDK đọc; chương trình truyền giá trị vào `registered_agent`.

## 6. Consumer integration — discovery rồi invocation

Lookup theo ID trả cả record không ONLINE; normal discovery chỉ trả ONLINE, kết hợp domain/capability bằng AND. Kết quả rỗng là hợp lệ:

```powershell
Invoke-RestMethod 'http://127.0.0.1:8000/v1/agents?domain=text&capability=echo_text'
Invoke-RestMethod 'http://127.0.0.1:8000/v1/agents/echo-team-a'
Invoke-RestMethod 'http://127.0.0.1:8000/v1/agents?active_only=false'
```

Lệnh cuối phục vụ quan sát, không dùng để mặc định chọn provider. Consumer gọi endpoint trực tiếp; Registry không proxy. Nếu provider không dùng common convention, thay phần invocation bằng adapter đã thống nhất.

### Minimal Consumer Example

Lưu `consumer.py` bên cạnh ví dụ provider. Schema output do consumer khai báo theo contract, không import source Registry:

```python
import os
import httpx
from pydantic import BaseModel, ConfigDict
from agent_registry_client.discovery import discover, DiscoveryError
from agent_registry_client.invocation import invoke_first, InvocationError

class EchoOutput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    text: str

try:
    with httpx.Client(timeout=5, trust_env=False, follow_redirects=False) as http:
        providers = discover(
            http, os.getenv("REGISTRY_URL", "http://127.0.0.1:8000"),
            "echo_text", domain="text",
        )
        output, provider_id = invoke_first(
            http, providers, "echo_text", {"text": "Hello"}, EchoOutput,
        )
        print({"provider_id": provider_id, "output": output})
except (DiscoveryError, InvocationError) as exc:
    raise SystemExit(str(exc))
```

Chạy `python consumer.py` khi provider đã đăng ký. Consumer chỉ biết Registry URL và capability contract, không hard-code địa chỉ provider. Không gắn Bearer credential Registry vào HTTP client dùng gọi business endpoint.

## 7. Endpoint change và LAN

Dừng provider cũ, giữ Agent ID/credential, sửa endpoint quảng bá và host/port server rồi restart. Re-registration cập nhật binding. Với Weather, đổi cả WEATHER_ENDPOINT và Uvicorn `--port`; với News tương tự. PATCH cũng sửa binding nhưng không renew lease; sửa trên web có thể bị cấu hình service ghi đè ở lần re-registration sau.

Trên nhiều máy, `127.0.0.1` là chính máy đang gọi. Ví dụ Registry ở máy A, provider ở B, consumer ở C:

- Registry/provider bind `--host 0.0.0.0` nếu cần nhận kết nối LAN.
- REGISTRY_URL dùng IP/DNS của A; endpoint quảng bá dùng IP/DNS của B, **không dùng 0.0.0.0**.
- Mở đúng port theo chính sách firewall; kiểm tra từ C bằng `Test-NetConnection <IP-provider> -Port <port>`.
- Provider và consumer phải cùng thống nhất contract; ONLINE không bảo đảm route mạng từ C tới B.

Đây là hướng dẫn cấu hình, chưa phải kết quả kiểm thử cross-machine. HTTP demo dành cho mạng tin cậy; triển khai Internet cần HTTPS và kiểm soát truy cập phù hợp.

## 8. Troubleshooting

| Triệu chứng | Kiểm tra / xử lý |
|---|---|
| 401 | ID và credential có khớp? File có BOM, khóa cũ sau reset DB? Không xóa khóa để thử chiếm lại ID |
| 404 khi heartbeat | Record sai ID hoặc bị DELETE; lifecycle dừng, cần operator |
| 409 | Lease hết/unregistered; authenticated re-registration, SDK tự xử lý |
| 422 | Kiểm tra card/query theo API contract; business input theo invocation contract |
| 503 / reconnecting | Registry/DB/network tạm lỗi; xem log và chờ retry |
| Discovery [] | Filter sai hoặc không có ONLINE provider; xem active_only=false |
| Provider chạy nhưng không được tìm thấy | Kiểm tra /health.registration, Registry URL và file credential |
| Endpoint vẫn cũ | Kiểm tra cấu hình provider, không chỉ card trên web; một process/ID |
| Lỗi ghi file khóa | Thư mục tồn tại, có quyền ghi, file mới chưa có; xem operator_required |
| Planner partial | Xem errors và stage discovery/invocation; phần còn lại có thể vẫn thành công |
| /forecast hoạt động nhưng lease hết | Business API và lifecycle độc lập; kiểm tra task đăng ký, không heartbeat từ browser |

Giới hạn thiết kế xem [Architecture](architecture.md); phạm vi kiểm chứng xem [Verification](verification.md).
