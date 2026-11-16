# Agent Integration

[README / ch?y demo](../README.md) � [Registry API](api_contract.md) � [Invocation Contract](invocation_contract.md)

Provider Agent cung c?p nghi?p v? v� duy tr? registration. Client / Consumer ch? t?m v� g?i provider; kh�ng c?n ��ng k? n?u kh�ng cung c?p d?ch v?. Nh�m v?n h�nh Registry cung c?p Registry URL; nh�m t�ch h?p kh�ng c?n s?a source Registry.

## 1. Provider integration � chu?n b?

C?n m?t HTTP service, Agent ID ?n �?nh, Agent Card, Registry URL truy c?p ��?c, n�i l�u credential b?n v?ng v� contract nghi?p v? �? th?a thu?n v?i consumer. C� th? d�ng b?t k? ng�n ng? h? tr? HTTP/JSON.

Endpoint l� URL operation �?y �?, kh�ng ph?i ch? base URL. M?t ID/credential ch? d�ng cho m?t process �ang ch?y; ch�a c� instance fencing. Xem gi?i h?n field/normalization trong [API Contract](api_contract.md).

### ��ng k? b?ng REST

V� d? PowerShell t?o card cho m?t service do nh�m t? tri?n khai; l?nh n�y **kh�ng t?o/ch?y service**. Ch? d�ng l?n �?u v?i ID m?i v� file credential ch�a t?n t?i:

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

Kh�ng in response ch?a credential ra log. 201 tr? credential m?t l?n; authenticated re-registration tr? 200 v� kh�ng c?p l?i kh�a.

V?i record �? c�, �?c kh�a v� g?i l?i card �?y �?:

```powershell
$token = [IO.File]::ReadAllText($keyPath).Trim()
$headers = @{ Authorization = "Bearer $token" }
Invoke-RestMethod "$registry/v1/agents" -Method Post -Headers $headers -ContentType 'application/json' -Body ($card | ConvertTo-Json)
```

Provider t? tri?n khai REST ph?i g?i POST `/v1/agents/{agent_id}/heartbeat` ? background theo interval tr? v?; kh�ng y�u c?u operator g?i th? c�ng m?i lease. X? l? 409 b?ng re-registration, l?i t?m th?i b?ng retry, v� unregister khi shutdown. SDK b�n d�?i cung c?p v?ng n�y.

## 2. Minimal Provider Example � Python SDK

SDK y�u c?u Python 3.11+, ch? ph? thu?c httpx/Pydantic. T? m�i tr�?ng Python c?a project b�n ngo�i:

```powershell
python -m pip install C:\agent-registry
python -m pip install fastapi uvicorn
```

L?nh th? hai ph?c v? v� d? FastAPI, kh�ng ph?i dependency b?t bu?c c?a SDK. Package ch? c�i `agent_registry_client`, kh�ng c�i Registry ho?c demo. C� th? d�ng editable install khi ph�t tri?n.

L�u v� d? sau th�nh `provider.py` trong project c?a nh�m:

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

Ch?y trong c�ng th� m?c ch?a file credential n?u �? ��ng k? REST tr�?c:

```powershell
$env:REGISTRY_URL = 'http://127.0.0.1:8000'
python -m uvicorn provider:app --port 8010
```

N?u ch�a c� registration/file, SDK t? t?o registration v� l�u credential. N?u �? ��ng k? qua REST/web, ph?i d�ng ��ng ID/file. V� d? minh h?a m?t capability m?i, kh�ng ph?i module c� s?n trong repo; contract Echo do v� d? t? �?nh ngh?a.

## 3. Credential v� ��ng k? tr�n web

SDK �?c file UTF-8 l�c startup; khi t?o m?i, ghi credential b?ng exclusive create, kh�ng overwrite file c?. D�ng ��?ng d?n b?n v?ng/absolute n?u working directory c� th? �?i. Kh�ng commit secret; h?n ch? quy?n �?c file, ki?m tra ACL th� m?c tr�n Windows. Registry ch? gi? hash, kh�ng c� API l?y l?i kh�a.

Flow web:

1. M? dashboard, ch?n **��ng k? Agent**, �i?n card ��ng v?i c?u h?nh service.
2. L�u credential ��?c hi?n th? m?t l?n v�o file UTF-8 kh�ng BOM, ch? ch?a kh�a.
3. C?p ��ng file v� Agent ID cho ch��ng tr?nh provider.
4. Start provider; SDK re-register r?i t? heartbeat.
5. ��ng browser v?n kh�ng ?nh h�?ng lifecycle.

Refresh trang kh�ng renew lease. N�t **��ng k? l?i** l� mutation ch? �?ng t?o lease m?i, kh�ng ph?i heartbeat t? �?ng. N�t **H?y ��ng k?** hi?n g?i DELETE v� x�a ownership; kh�ng t��ng ���ng soft unregister.

M?t file kh�a ho?c m?t response c?p kh�a l?n �?u ch�a c� recovery API. Kh�ng th? suy ra secret t? hash. C?n operator x? l? ho?c d�ng ID m?i; kh�ng reset to�n b? DB �? ch?a ri�ng m?t registration.

## 4. Automatic heartbeat, recovery v� shutdown

`registered_agent` b?t �?u task n?n; business API kh�ng ph?i �?i Registry ��ng k? xong. SDK register l�c startup, l?y heartbeat interval t? response v� g?i heartbeat �?nh k?. Th�nh c�ng renew lease; Agent c� th? ch?y qua nhi?u chu k? TTL.

| T?nh hu?ng | SDK hi?n x? l? |
|---|---|
| Heartbeat c?n lease | Renew; SUSPECT c� th? tr? l?i ONLINE |
| Heartbeat tr? 409 | G?i l?i card c�ng credential �? re-register |
| L?i m?ng, 408/429/5xx | Retry exponential backoff c� jitter, ti?p t?c ph?c v? business API |
| 401/403/404/422 v� 4xx kh�ng retry kh�c | D?ng lifecycle v?i operator_required, kh�ng t? chi?m ID |
| File credential kh�ng �?c/l�u ��?c | operator_required |
| Tho�t context / Ctrl+C | H?y task, c? g?ng POST unregister trong t?i �a 4s |

Retry timing kh�ng thay TTL c?a Registry. Kh�ng d�ng `--lifespan off`; kh�ng ch?y nhi?u worker d�ng chung ID. Registry restart v?i DB c? gi? ownership/timestamp. N?u DB b? x�a, token c? kh�ng t? ��?c ch?p nh?n cho ID m?i.

## 5. C?u h?nh c�c ch��ng tr?nh c� s?n

C�c ch��ng tr?nh �?c bi?n m�i tr�?ng process; `.env.example` kh�ng t? ��?c n?p. Trong PowerShell d�ng `$env:TEN_BIEN = 'gia_tri'`.

| Bi?n | Ch��ng tr?nh | M?c �?nh |
|---|---|---|
| REGISTRY_DATABASE_URL | Registry | sqlite:///./registry.db |
| REGISTRY_HEARTBEAT_SECONDS | Registry | 10 |
| REGISTRY_TTL_SECONDS | Registry | 30 |
| REGISTRY_SUSPECT_SECONDS | Registry | (heartbeat + TTL) / 2 n?u kh�ng �?t |
| REGISTRY_URL | Providers, Travel, Planner | http://127.0.0.1:8000 |
| WEATHER_AGENT_ID | Weather | weather-local |
| WEATHER_ENDPOINT | Weather | http://127.0.0.1:8001/forecast |
| WEATHER_CREDENTIAL_FILE | Weather | weather.credential |
| NEWS_AGENT_ID | News | news-agent-01 |
| NEWS_ENDPOINT | News | http://127.0.0.1:8002/invoke |
| NEWS_CREDENTIAL_FILE | News | news.credential |
| AGENT_RETRY_MAX_SECONDS | Weather, News | 10 |

Registry y�u c?u `0 < heartbeat < suspect < TTL`; heartbeat/TTL l� s? nguy�n gi�y. Retry max l� s? d��ng, gi?i h?n kho?ng backoff ch? kh�ng gi?i h?n s? l?n th?. C�c bi?n demo kh�ng t? ��?c SDK �?c; ch��ng tr?nh truy?n gi� tr? v�o `registered_agent`.

## 6. Consumer integration � discovery r?i invocation

Lookup theo ID tr? c? record kh�ng ONLINE; normal discovery ch? tr? ONLINE, k?t h?p domain/capability b?ng AND. K?t qu? r?ng l� h?p l?:

```powershell
Invoke-RestMethod 'http://127.0.0.1:8000/v1/agents?domain=text&capability=echo_text'
Invoke-RestMethod 'http://127.0.0.1:8000/v1/agents/echo-team-a'
Invoke-RestMethod 'http://127.0.0.1:8000/v1/agents?active_only=false'
```

L?nh cu?i ph?c v? quan s�t, kh�ng d�ng �? m?c �?nh ch?n provider. Consumer g?i endpoint tr?c ti?p; Registry kh�ng proxy. N?u provider kh�ng d�ng common convention, thay ph?n invocation b?ng adapter �? th?ng nh?t.

### Minimal Consumer Example

L�u `consumer.py` b�n c?nh v� d? provider. Schema output do consumer khai b�o theo contract, kh�ng import source Registry:

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

Ch?y `python consumer.py` khi provider �? ��ng k?. Consumer ch? bi?t Registry URL v� capability contract, kh�ng hard-code �?a ch? provider. Kh�ng g?n Bearer credential Registry v�o HTTP client d�ng g?i business endpoint.

## 7. Endpoint change v� LAN

D?ng provider c?, gi? Agent ID/credential, s?a endpoint qu?ng b� v� host/port server r?i restart. Re-registration c?p nh?t binding. V?i Weather, �?i c? WEATHER_ENDPOINT v� Uvicorn `--port`; v?i News t��ng t?. PATCH c?ng s?a binding nh�ng kh�ng renew lease; s?a tr�n web c� th? b? c?u h?nh service ghi �� ? l?n re-registration sau.

Tr�n nhi?u m�y, `127.0.0.1` l� ch�nh m�y �ang g?i. V� d? Registry ? m�y A, provider ? B, consumer ? C:

- Registry/provider bind `--host 0.0.0.0` n?u c?n nh?n k?t n?i LAN.
- REGISTRY_URL d�ng IP/DNS c?a A; endpoint qu?ng b� d�ng IP/DNS c?a B, **kh�ng d�ng 0.0.0.0**.
- M? ��ng port theo ch�nh s�ch firewall; ki?m tra t? C b?ng `Test-NetConnection <IP-provider> -Port <port>`.
- Provider v� consumer ph?i c�ng th?ng nh?t contract; ONLINE kh�ng b?o �?m route m?ng t? C t?i B.

��y l� h�?ng d?n c?u h?nh, ch�a ph?i k?t qu? ki?m th? cross-machine. HTTP demo d�nh cho m?ng tin c?y; tri?n khai Internet c?n HTTPS v� ki?m so�t truy c?p ph� h?p.

## 8. Troubleshooting

| Tri?u ch?ng | Ki?m tra / x? l? |
|---|---|
| 401 | ID v� credential c� kh?p? File c� BOM, kh�a c? sau reset DB? Kh�ng x�a kh�a �? th? chi?m l?i ID |
| 404 khi heartbeat | Record sai ID ho?c b? DELETE; lifecycle d?ng, c?n operator |
| 409 | Lease h?t/unregistered; authenticated re-registration, SDK t? x? l? |
| 422 | Ki?m tra card/query theo API contract; business input theo invocation contract |
| 503 / reconnecting | Registry/DB/network t?m l?i; xem log v� ch? retry |
| Discovery [] | Filter sai ho?c kh�ng c� ONLINE provider; xem active_only=false |
| Provider ch?y nh�ng kh�ng ��?c t?m th?y | Ki?m tra /health.registration, Registry URL v� file credential |
| Endpoint v?n c? | Ki?m tra c?u h?nh provider, kh�ng ch? card tr�n web; m?t process/ID |
| L?i ghi file kh�a | Th� m?c t?n t?i, c� quy?n ghi, file m?i ch�a c�; xem operator_required |
| Planner partial | Xem errors v� stage discovery/invocation; ph?n c?n l?i c� th? v?n th�nh c�ng |
| /forecast ho?t �?ng nh�ng lease h?t | Business API v� lifecycle �?c l?p; ki?m tra task ��ng k?, kh�ng heartbeat t? browser |

Gi?i h?n thi?t k? xem [Architecture](architecture.md); ph?m vi ki?m ch?ng xem [Verification](verification.md).

