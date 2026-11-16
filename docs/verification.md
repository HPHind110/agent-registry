# Verification

[README / ch?y demo](../README.md) � [Architecture](architecture.md) � [Agent Integration](agent_integration.md)

T�i li?u n�y ghi ph?m vi test v� k?t qu? th?c thi, kh�ng thay th? h�?ng d?n s? d?ng ho?c ch?ng nh?n tri?n khai production.

## 1. Test Strategy

| L?p ki?m tra | Source | C�ch th?c hi?n |
|---|---|---|
| API, persistence, validation | tests/test_registry.py | FastAPI TestClient, SQLite t?m, clock �i?u khi?n ��?c |
| Lifecycle / failure detection | tests/test_lifecycle.py | Clock gi? cho boundary; httpx MockTransport cho retry/recovery |
| Provider contract / consumer integration | tests/test_generic.py | News/Weather API, discovery, validate output v� failover |
| Dashboard controller | tests/dashboard.test.cjs | Node test runner v?i DOM/fetch gi? |
| Legacy process smoke | scripts/smoke_test.py | Registry + Weather + Travel qua process ri�ng v� HTTP loopback |
| Multi-provider process smoke | scripts/generic_smoke_test.py | Registry + Weather + News + Planner qua process ri�ng |

Fake clock tr�nh ch? TTL th?c trong API tests. Smoke d�ng TTL ng?n, port/DB/credential t?m; kh�ng s? d?ng database v� credential demo c?a ng�?i d�ng. Runner test-only �i?u khi?n process qua file ri�ng: crash d�ng os._exit b? qua cleanup, graceful d�ng Uvicorn shutdown; kh�ng th�m public route �i?u khi?n server.

## 2. Commands

Sau khi c�i dependencies theo README, t? root repository:

```powershell
.\.venv\Scripts\python -m pytest -q
node --test tests/dashboard.test.cjs
.\.venv\Scripts\python scripts/smoke_test.py
.\.venv\Scripts\python -m scripts.generic_smoke_test
```

Node ch? c?n cho dashboard tests. Generic smoke ph?i ch?y d?ng module nh� tr�n �? import helpers t? scripts. Server log ��?c in khi smoke th?t b?i; cleanup ki?m tra k?t th�c process v� x�a DB t?m.

## 3. Current Verification Results

Th?c thi ng�y **16/11/2026**, Windows, Python **3.13.15**, Node.js **v24.20.0**, virtualenv hi?n c�.

| L?nh | K?t qu? th?c t? |
|---|---|
| pytest -q | 67 passed, 1 warning, 4.06s; exit 0 |
| node --test tests/dashboard.test.cjs | 6 passed, 0 failed; exit 0 |
| python scripts/smoke_test.py | 6 nh�m PASS, g?m shutdown v� temporary database cleanup; exit 0 |
| python -m scripts.generic_smoke_test | 5 nh�m PASS, g?m cleanup; exit 0 |

Warning pytest l� StarletteDeprecationWarning v? TestClient d�ng httpx. Kh�ng thay dependency/code �? x? l? warning trong task t�i li?u n�y.

�Nh�m PASS� l� c�c checkpoint do smoke script in ra, kh�ng ph?i s? test case pytest. K?t qu? tr�n ch? m� t? m�i tr�?ng/l?n ch?y n�y; kh�ng suy ra m?i t?nh hu?ng m?ng �?u �? ��?c x? l?.

## 4. Scenarios Covered

| Scenario | B?ng ch?ng trong suite |
|---|---|
| Registration, lookup, normalization, response schemas | test_registry |
| Ownership, duplicate/concurrent ID, unauthorized mutation | test_registry |
| Heartbeat renew, nhi?u chu k? lease, ng�?ng SUSPECT/UNREACHABLE | test_registry + test_lifecycle |
| Exclude non-ONLINE kh?i discovery, nhi?u provider/filter | test_registry + test_generic |
| Re-registration, endpoint update, persistence qua restart | API tests + c? hai smoke |
| Unregister gi? ownership, DELETE x�a record | test_lifecycle / test_registry |
| Retry Registry unavailable, business API ti?p t?c | test_lifecycle + c? hai smoke |
| Weather GET/POST compatibility | test_generic + legacy smoke |
| News search/summarize v� input l?i | test_generic |
| Planner complete/partial, direct invocation | test_generic + generic smoke |
| Failover network/HTTP/JSON/schema/identity/capability | test_generic v?i MockTransport |
| Browser kh�ng heartbeat, polling ch? GET | dashboard controller tests |
| Heartbeat ho?t �?ng kh�ng c?n browser | c? hai process smoke |
| Import SDK c? c?n ho?t �?ng | test_generic |

Smoke legacy quan s�t crash ? SUSPECT ? UNREACHABLE, Registry restart kh�ng h?i sinh lease c?, recovery c�ng identity ? endpoint m?i v� graceful unregister. Generic smoke th�m Weather crash trong khi News c?n d�ng ��?c, Planner partial, c? hai provider reconnect sau Registry outage.

## 5. Not Verified

- LAN nhi?u m�y, provider c?a nh�m ngo�i, m?ng Internet production.
- Browser E2E ho?c layout/accessibility tr�n browser th?t; DOM gi? kh�ng thay th? ki?m th? n�y.
- Python 3.11/3.12 ho?c h? �i?u h�nh kh�c trong l?n ch?y hi?n t?i.
- Benchmark t?i, s? l�?ng Agent l?n, m?i ki?u packet loss/network partition ho?c clock jump.
- Build/c�i wheel SDK �?c l?p trong l?n ki?m ch?ng n�y.
- Active probe, instance fencing, credential rotation: ch�a ��?c tri?n khai, kh�ng c� test ch?ng minh c�c feature n�y.

C�c v� d? code trong t�i li?u c?n ��?c ph�n bi?t v?i c�c module demo �ang c�. K?t qu? ki?m tra c� ph�p/link t�i li?u ��?c ghi trong b�o c�o refactor, kh�ng t�nh v�o s? test c?a ?ng d?ng.

