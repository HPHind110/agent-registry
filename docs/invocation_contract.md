# Provider Invocation Contract

[README](../README.md) � [Registry API](api_contract.md) � [Agent Integration](agent_integration.md)

## 1. Ph?m vi v� convention

��y l� common invocation convention v1 c?a demo v� SDK helper, **kh�ng ph?i chu?n universal ho?c y�u c?u c?a Registry backend**. Provider d�ng protocol kh�c v?n ��ng k?/discovery ��?c, nh�ng consumer ph?i c� adapter ph� h?p.

Agent Card ch? c�ng b? capability v� m?t full endpoint. N� ch�a m� t? HTTP method, request/response schema, business authentication ho?c protocol version; `version` hi?n l� phi�n b?n service. C�c nh�m ph?i th?ng nh?t convention ngo�i Registry.

Consumer POST v�o **��ng endpoint trong card**, kh�ng t? n?i `/invoke` ho?c `/forecast`. Registry credential kh�ng ��?c g?i t?i business endpoint. C�c demo ch�a c� business authentication.

## 2. Request / response envelope

Request:

```json
{"capability": "search_news", "input": {"keyword": "Hanoi"}}
```

Response HTTP 200, v� d? r�t g?n:

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

Envelope request g?m capability (chu?i strip, 1�100 k? t?) v� input (object); kh�ng nh?n tr�?ng th?a. Output l� object; response identity/capability ph?i tr�ng provider/request. Capability trong invocation c?n ��ng t�n �? th?a thu?n; kh�ng �p d?ng normalization c?a Registry �? t? �?i t�n request.

Helper `invoke_first` validate envelope, Agent ID, capability v� output theo Pydantic model do consumer cung c?p. Helper kh�ng t? bi?t schema c?a m?i capability.

## 3. Demo capabilities

| Provider / endpoint m?c �?nh | Capability | Input | Output |
|---|---|---|---|
| Weather: POST `http://127.0.0.1:8001/forecast` | weather_forecast | city: chu?i 1�100, m?c �?nh Hanoi | city, temperature_c, condition, source |
| News: POST `http://127.0.0.1:8002/invoke` | search_news | keyword: chu?i 1�100 | articles: array c�c object title/summary |
| News: c�ng endpoint | summarize_news | text: chu?i 1�10000 | summary: chu?i kh�ng r?ng |

POST business input d�ng strict validation, strip chu?i, kh�ng nh?n field th?a ho?c chu?i ch? whitespace. Weather tr? nhi?t �? 26, condition partly_cloudy, source demo_static_data. Schema consumer y�u c?u temperature_c l� s? h?u h?n v� c�c chu?i output Weather kh�ng r?ng.

News t?m substring kh�ng ph�n bi?t hoa th�?ng trong title/summary c?a ba b�i m?u; kh�ng c� k?t qu? tr? articles r?ng v� v?n th�nh c�ng. T�m t?t l?y c�u �?u (t�ch theo d?u ch?m/ch?m h?i/ch?m than theo sau b?i whitespace), c?t t?i �a 240 k? t?. Kh�ng g?i ngu?n tin tr?c ti?p ho?c LLM.

## 4. Errors v� failover

| T?nh hu?ng | Response provider |
|---|---|
| Capability kh�ng h? tr? | 400, detail.code = unsupported_capability |
| Business input kh�ng h?p l? | 422, detail.code = invalid_input, k�m errors |
| Envelope sai | 422, detail array c?a FastAPI |
| L?i HTTP/service kh�c | Consumer x? l? theo HTTP response th?c t? |

`invoke_first` th? provider theo th? t? danh s�ch. L?i m?ng, HTTP, JSON, envelope, identity/capability ho?c business schema khi?n helper th? provider ti?p theo; h?t provider th? n�m InvocationError. Discovery l?i c� DiscoveryError ri�ng. Timeout do caller thi?t l?p; Planner d�ng 5s/request, kh�ng follow redirect, kh�ng �?c c?u h?nh proxy t? m�i tr�?ng.

Failover kh�ng cung c?p exactly-once ho?c idempotency key. Kh�ng d�ng m?c �?nh n�y cho operation c� side effect n?u ch�a th?ng nh?t c�ch ch?ng th?c thi l?p.

## 5. Planner output

Planner discovery `weather_forecast`/domain weather r?i `search_news`/domain news, g?i t?ng capability tr?c ti?p. Hai ph?n ��?c x? l? l?i �?c l?p, kh�ng ph?i workflow ch?y song song.

Output g?m:

| Field | ? ngh?a |
|---|---|
| city | Th�nh ph? �?u v�o |
| status | complete n?u kh�ng c� l?i; partial n?u c� b?t k? l?i n�o, k? c? c? hai ph?n l?i |
| weather | Forecast �? validate ho?c null |
| news | Danh s�ch b�i t?m ��?c, ho?c [] n?u l?i/kh�ng c� k?t qu? |
| providers_used | C�c object agent_id/capability �? th�nh c�ng |
| errors | Theo ph?n weather/news, c� stage discovery ho?c invocation v� message |

CLI v?n in JSON khi partial, exit code 1; complete exit 0. articles r?ng kh�ng t? t?o l?i. Planner kh�ng cache binding, kh�ng hard-code �?a ch? provider, kh�ng ph?i multi-agent orchestrator.

## 6. Legacy Weather / Travel

Weather gi? `GET /forecast?city=Hanoi` v?i city m?c �?nh Hanoi, length 1�100. Response GET l� forecast tr?c ti?p, kh�ng envelope:

```json
{"city":"Hanoi","temperature_c":26,"condition":"partly_cloudy","source":"demo_static_data"}
```

Travel discovery domain weather/capability weather_forecast, GET ��ng endpoint ��?c tr? v?, th�m city query. N� c� timeout/failover HTTP/JSON nh�ng **ch�a validate business schema forecast**. POST Weather l� ph?n b? sung; kh�ng b?t Travel chuy?n sang convention m?i.

## 7. Provider health

Weather v� News c� `GET /health`, tr? live=true, ready=true v� registration state. State SDK c� th? starting, registered, reconnecting, operator_required, unregistered; disabled khi lifecycle kh�ng ch?y.

Ready hi?n l� gi� tr? c? �?nh trong demo, kh�ng ph?i ki?m tra dependency th?t. State registration kh�ng �?ng nh?t v?i ONLINE c?a Registry. Registry kh�ng g?i endpoint n�y. Ph?m vi test xem [Verification](verification.md).

