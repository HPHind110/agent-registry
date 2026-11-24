# Kiểm thử và xác minh

[README](../README.md) · [Companion](companion_onboarding.md) · [Deployment](deployment.md)

Tách ba mức bằng chứng: **unit/integration tests**, **smoke tests loopback**, và **kiểm thử thực tế trên Registry HTTPS**. Một mức đạt không tự chứng minh mức còn lại.

## 1. Chạy test từ root repository

Tạo Python 3.11+ environment và cài `requirements.txt`, sau đó:

~~~powershell
.\.venv\Scripts\python -m pytest -q
node --test tests/dashboard.test.cjs
.\.venv\Scripts\python scripts/smoke_test.py
.\.venv\Scripts\python -m scripts.generic_smoke_test
~~~

Lệnh trên cho Windows; Linux dùng `.venv/bin/python`. Node.js **chỉ cần cho dashboard tests**, không cần để chạy Registry.

| Thành phần | Tests |
|---|---|
| REST API, admission/ownership, lease | `tests/test_registry.py`, `tests/test_admission.py` |
| SDK lifecycle, discovery, invocation | `tests/test_lifecycle.py`, `tests/test_generic.py`, `tests/test_rediscovery.py` |
| Companion và launcher | `tests/test_companion.py`, `tests/test_companion_launchers.py` |
| Dashboard | `tests/dashboard.test.cjs` |
| Process HTTP loopback | `scripts/smoke_test.py`, `scripts/generic_smoke_test.py` |

Để build lại kit từ source: `python scripts/build_companion.py`. Chỉ phát hành artifact khi build/test và review thành công.

## 2. Kết quả đã ghi nhận

Tại PR #5 (24/11/2026), Codex báo **115 Python tests pass**, **7 Dashboard tests pass**, hai smoke scripts pass trên Windows. GitHub Actions chạy **24/24 Companion/launcher tests** trên Ubuntu Python 3.11 và **24/24** trên Windows Python 3.11; cả hai jobs kết thúc `success`.

Kiểm thử thủ công thực tế trên laptop Windows với **File Organizer (8101)** và **Study Planner (8102)** đã xác nhận: `check`, authenticated re-register, heartbeat mỗi 10 giây, health failure → unregister, Agent restart → recovery, Companion `Ctrl+C` → giữ ownership và restart lại `ONLINE`. Launcher tạo profile riêng cho mỗi ID và chạy lifecycle.

Những kết quả này **không** chứng minh Consumer ở một máy/mạng khác gọi được business endpoint, cũng không chứng minh Linux desktop double-click hoặc khả năng chịu tải production.

## 3. Checklist trước khi demo liên nhóm

- [ ] Registry HTTPS `GET /v1/health` trả `status=ok`.
- [ ] Provider đăng ký đúng card, giữ credential ngoài Git, dùng **một** Companion/SDK.
- [ ] Health URL local trả 2xx khi khỏe; Companion gửi heartbeat và duy trì `ONLINE`.
- [ ] Khi dừng Provider, Companion ngừng heartbeat; khi bật lại, re-register thành công.
- [ ] Consumer discovery được đúng capability; **endpoint reachable từ máy Consumer**.
- [ ] Consumer gọi đúng method/payload/auth và xác minh response.
- [ ] Thử tình huống Provider lỗi, Registry tạm mất kết nối và restart.
- [ ] Không đưa Join Token, credential hay secret vào log/ảnh/demo.

## 4. Chưa được đảm bảo

Chưa có benchmark lớn, Registry replication, instance fencing liên máy, rate limiting theo nhóm, credential recovery, hoặc thử nghiệm end-to-end độc lập giữa tất cả nhóm infra. Kiểm thử của Companion không thay thế bài kiểm tra kết nối Broker hay giao thức invocation.

[Architecture](architecture.md) · [API Contract](api_contract.md)
