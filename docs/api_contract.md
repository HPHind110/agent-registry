# Registry API Contract

[README](../README.md) � [Architecture](architecture.md) � [Agent Integration](agent_integration.md)

## 1. Ph?m vi

Base URL local: `http://127.0.0.1:8000`. Request/response d�ng JSON UTF-8; timestamp ISO-8601 UTC c� `Z` ho?c `+00:00`. Schema sinh t? app t?i [OpenAPI](http://127.0.0.1:8000/openapi.json), giao di?n th? t?i [Swagger UI](http://127.0.0.1:8000/docs).

T�i li?u n�y m� t? **Registry REST API**. [Provider invocation contract](invocation_contract.md) l� th?a thu?n ri�ng c?a provider/consumer, kh�ng ph?i schema Registry �p �?t l�n business API.

## 2. Agent Card v� normalization

V� d? request t?o registration:

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

T?t c? tr�?ng b?t bu?c khi POST; kh�ng nh?n tr�?ng th?a ho?c metadata do client t? �?t.

| Tr�?ng | Quy t?c |
|---|---|
| agent_id | 1�128 k? t?, regex `[A-Za-z0-9][A-Za-z0-9_.-]{0,127}`; ph�n bi?t hoa th�?ng |
| name | Chu?i 1�200 k? t? sau strip |
| domain | Chu?i 1�100 k? t? sau strip, sau �� normalization |
| description | Chu?i t?i �a 1000 k? t? sau strip; ��?c r?ng |
| capabilities | 1�100 chu?i �?u v�o; normalization, lo?i tr�ng v� s?p x?p |
| endpoint | HTTP(S) URL t?i �a 2048 k? t?; kh�ng username/password/fragment |
| version | Chu?i 1�64 k? t? sau strip; ch�a c� compatibility negotiation |

Domain/capability ��?c strip, lowercase, gom chu?i whitespace ho?c d?u `-` th�nh `_`. K?t qu? ph?i kh?p `[a-z0-9][a-z0-9_.:]{0,99}`. V� d? ` Weather-Forecast ` th�nh `weather_forecast`. Filter �p d?ng c�ng normalization, so kh?p ch�nh x�c; query domain/capability t?i �a 100 k? t? tr�?c normalization. URL ��?c Pydantic chu?n h�a; Registry kh�ng ki?m tra kh? n�ng truy c?p endpoint.

## 3. Authentication v� ownership

D�ng header `Authorization: Bearer <credential>` c?a ��ng Agent ID. Kh�ng ��a secret v�o URL.

- ID m?i: ��ng k? kh�ng k�m credential, nh?n secret m?t l?n. G?i credential cho ID ch�a t?n t?i tr? 401.
- ID �? t?n t?i: c?n credential ��ng �? re-register ho?c mutation; sai/thi?u tr? 401, kh�ng ghi �� record.
- GET kh�ng y�u c?u credential; kh�ng tr? secret/hash.
- L?i 401 c� header `WWW-Authenticate: Bearer`.

Ownership kh�ng t��ng ���ng x�c minh danh t�nh t? ch?c. ��ng k? ID m?i v� �?c danh b? hi?n ch�a c� admission policy/t�i kho?n.

## 4. Routes v� response models

| Method | Route | Input | Th�nh c�ng | Bearer |
|---|---|---|---|---|
| POST | `/v1/agents` | Card �?y �? | 201 t?o m?i / 200 re-register; Registration | Khi ID �? t?n t?i |
| GET | `/v1/agents` | capability, domain, active_only | 200, array AgentView | Kh�ng |
| GET | `/v1/agents/{agent_id}` | ID | 200, AgentView | Kh�ng |
| PATCH | `/v1/agents/{agent_id}` | C�c tr�?ng card tr? ID | 200, AgentView | C� |
| POST | `/v1/agents/{agent_id}/heartbeat` | Kh�ng c?n body | 200, AgentView | C� |
| GET | `/v1/agents/{agent_id}/status` | ID | 200, AgentStatus | Kh�ng |
| POST | `/v1/agents/{agent_id}/unregister` | Kh�ng c?n body | 200, AgentView | C� |
| DELETE | `/v1/agents/{agent_id}` | ID | 204, body r?ng | C� |
| GET | `/v1/health` | Kh�ng | 200, Health | Kh�ng |

**AgentView:** to�n b? Agent Card c?ng `registered_at`, `updated_at`, `last_heartbeat`, `lease_expires_at`, `status`.

**Registration:** AgentView c?ng `heartbeat_interval_seconds`, `ttl_seconds`; ch? response 201 c� th�m `credential`. Response 200 re-register **b? tr�?ng credential**, kh�ng tr? null. C? hai c� `Cache-Control: no-store`.

**AgentStatus:** ch? `agent_id`, `status`, `last_heartbeat`, `lease_expires_at`.

V� d? status sau ��ng k? (timestamp minh h?a):

```json
{
  "agent_id": "weather-team-a",
  "status": "ONLINE",
  "last_heartbeat": "2026-11-16T09:00:00Z",
  "lease_expires_at": "2026-11-16T09:00:30Z"
}
```

**Health:** `status: "ok"`, `server_time`, `heartbeat_interval_seconds`, `ttl_seconds`, sau ki?m tra DB b?ng SELECT 1. ��y kh�ng ph?i health c?a provider.

## 5. Discovery v� lookup

```http
GET /v1/agents?domain=weather&capability=weather_forecast
GET /v1/agents?active_only=false
GET /v1/agents/weather-team-a
```

- `active_only=true` l� m?c �?nh, ch? tr? **ONLINE**.
- `active_only=false` g?m ONLINE/SUSPECT/UNREACHABLE/UNREGISTERED �? quan s�t, v?n �p d?ng c�c filter kh�c.
- Domain v� capability k?t h?p AND. M?t capability c� th? c� nhi?u provider.
- Array s?p theo Agent ID t�ng d?n theo th? t? SQLite; kh�ng ph�n trang.
- Kh�ng c� k?t qu? tr? `200 []`. Lookup ID kh�ng t?n t?i tr? 404.
- Lookup/status theo ID v?n tr? record kh�ng ONLINE; kh�ng t? ch?n n� l�m provider.
- GET kh�ng renew lease; expiry ��?c ��nh gi� khi query, kh�ng c?n maintenance ch?y tr�?c.

## 6. Registration, mutation v� lease

M?c �?nh heartbeat interval 10s, suspect threshold 20s, TTL 30s. N?u kh�ng c?u h?nh suspect ri�ng, d�ng trung b?nh interval v� TTL. �i?u ki?n c?u h?nh: `0 < interval < suspect < TTL`.

| Operation | Card / ownership | Timestamp / tr?ng th�i |
|---|---|---|
| Register m?i | T?o card v� hash credential | C�c timestamp = now, expiry = now + TTL, ONLINE |
| Re-register | Card �?y �? thay th? card c?; gi? hash v� registered_at | updated_at/last_heartbeat = now, expiry = now + TTL, b? withdrawn |
| Heartbeat | Kh�ng thay card/endpoint | updated_at/last_heartbeat = now, expiry = now + TTL |
| PATCH | S?a c�c tr�?ng cung c?p; kh�ng �?i ID | Ch? updated_at �?i, kh�ng renew |
| Unregister | Gi? card/hash/registered_at | withdrawn = true, updated_at/expiry = now |
| DELETE | X�a record v� hash | ID ��?c gi?i ph�ng |

PATCH ph?i c� �t nh?t m?t tr�?ng, kh�ng nh?n null, ID ho?c runtime metadata. V� d?:

```json
{"endpoint": "http://192.168.1.20:9005/forecast"}
```

PATCH c� th? s?a record UNREACHABLE/UNREGISTERED nh�ng kh�ng k�ch ho?t l?i. Re-registration c� credential h?p l? ��?c ph�p ? m?i tr?ng th�i v� renew lease.

Status �u ti�n UNREGISTERED khi withdrawn; sau �� UNREACHABLE khi `now >= lease_expires_at`; SUSPECT khi tu?i heartbeat �?t suspect threshold nh�ng lease c?n h?n; c?n l?i ONLINE. Heartbeat khi SUSPECT ��?c nh?n; sau expiry ho?c unregister tr? 409, c?n re-register.

Unregister l?p l?i ��?c, gi? ownership �? restart. DELETE x�a v?nh vi?n, c�c lookup/mutation theo ID sau �� tr? 404; m?t ��ng k? m?i kh�ng token c� th? l?y ID n�y. SDK kh�ng t? chi?m l?i ID khi g?p 404.

## 7. HTTP errors

| HTTP | ? ngh?a |
|---|---|
| 401 | Thi?u/sai ownership credential; ho?c g?i token cho ID m?i |
| 404 | Record kh�ng t?n t?i |
| 409 | Heartbeat khi lease h?t ho?c �? unregister |
| 422 | Card/query sai, tr�?ng th?a, PATCH r?ng/null |
| 503 | DB t?m kh�ng truy c?p ��?c ho?c l?i operational, g?m SQLite b?n qu� timeout |

L?i service d�ng `{"detail":"..."}`. Validation Pydantic/FastAPI d�ng detail array; normalization query c� th? d�ng detail string. Client n�n d?a v�o HTTP code, kh�ng parse th�ng �i?p ti?ng Anh.

Server kh�ng tr? l?i credential sau l?n t?o m?i. N?u response �?u ti�n th?t l?c nh�ng record �? t?o, retry kh�ng c� kh�a c� th? nh?n 401; ch�a c� idempotency key ho?c recovery API.

## 8. Backward compatibility

Agent Card v� DELETE gi? semantics hi?n t?i; `POST /unregister` l� thao t�c gi? ownership ri�ng. Literal status hi?n l� ONLINE/SUSPECT/UNREACHABLE/UNREGISTERED, **kh�ng c?n ACTIVE/EXPIRED**. Client d?a tr�n literal c? ph?i c?p nh?t; `active_only=true` hi?n lo?i c? SUSPECT.

Weather GET v� import `demo.registry_client.RegistryClient` v?n ��?c gi?; ch�ng thu?c demo/SDK, kh�ng m? r?ng schema Registry. Xem [Invocation Contract](invocation_contract.md) v� [Verification](verification.md).

