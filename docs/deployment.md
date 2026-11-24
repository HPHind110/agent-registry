# Deployment & Operations — Registry HTTPS

**Dành cho người vận hành Registry, không phải Provider/Client.** Provider dùng [Companion Onboarding](companion_onboarding.md).

**Production URL:** [https://103-180-134-53.sslip.io/](https://103-180-134-53.sslip.io/) · [README](../README.md)

## 1. Trạng thái triển khai

~~~text
Internet HTTPS :443
       ↓
Caddy reverse proxy
       ↓
Uvicorn / FastAPI 127.0.0.1:8000 (systemd: agent-registry)
       ↓
SQLite /var/lib/agent-registry/registry.db
~~~

| Hạng mục | Vị trí trên VPS |
|---|---|
| Code + virtualenv | `/home/registryadmin/agent-registry`, `.venv` |
| SQLite bền vững | `/var/lib/agent-registry/registry.db` (ngoài Git) |
| Service | `agent-registry.service` |
| Admission config | `/etc/agent-registry/admission.env` (root-only, 0600) |
| Reverse proxy | Caddy, HTTPS tới port 443; upstream loopback 8000 |

Đã xác minh `systemd active (running)`, health loopback và HTTPS trả `status: ok` trên VPS trong đợt triển khai 24/11/2026. **Không cần SSH tunnel để dùng Dashboard/API**. Không mở trực tiếp port 8000 ra Internet.

Lưu ý: Source trên GitHub và process VPS không tự đồng bộ. **Companion Kit và launcher chỉ là công cụ Provider; cập nhật Companion không yêu cầu deploy/restart Registry server**, nếu REST contract không đổi.

## 2. Kiểm tra trạng thái production

Kết nối từ Windows PowerShell (khóa SSH đã được cấu hình sẵn):

~~~powershell
ssh -i "$env:USERPROFILE\.ssh\agent_registry_vps" registryadmin@103.180.134.53
~~~

Sau khi vào **Ubuntu VPS**:

~~~bash
cd /home/registryadmin/agent-registry
git status --short --branch
git log -1 --oneline
sudo systemctl status agent-registry --no-pager
sudo systemctl status caddy --no-pager
curl -fsS http://127.0.0.1:8000/v1/health
curl -fsS https://103-180-134-53.sslip.io/v1/health
~~~

Xem lỗi: `sudo journalctl -u agent-registry -n 100 --no-pager`. Không in `REGISTRY_JOIN_TOKEN` hoặc Bearer credentials ra terminal chia sẻ.

## 3. Admission: tạo ID mới

Production yêu cầu Join Token trong `X-Registry-Join-Token`. ID đã có dùng Bearer credential riêng; việc đổi Join Token **không** làm mất ownership hiện hữu.

File `/etc/agent-registry/admission.env` có các biến:

~~~ini
REGISTRY_ALLOW_OPEN_REGISTRATION=0
REGISTRY_JOIN_TOKEN=<secret-generated-and-managed-privately>
~~~

Service load qua systemd drop-in `/etc/systemd/system/agent-registry.service.d/override.conf`:

~~~ini
[Service]
EnvironmentFile=-/etc/agent-registry/admission.env
~~~

**Đây là cấu hình đang có; không tạo mới/ghi đè admission.env trên VPS hiện tại.** Với VPS mới, tạo token ngẫu nhiên qua secure secret provisioning, file root-only, quyền 0600; cài drop-in rồi `daemon-reload` và restart có kiểm soát. Không đưa Join Token vào Git, tài liệu demo hay URL. Khi thiếu token, creation bị khóa (`503`), nhưng ID đã tồn tại vẫn có thể hoạt động.

## 4. Backup trước khi cập nhật code

Chạy trên VPS, yêu cầu `sqlite3` và quyền đọc SQLite đang dùng. Dùng Online Backup API để có snapshot nhất quán:

~~~bash
umask 077
db=/var/lib/agent-registry/registry.db
test -f "$db" || exit 1
mkdir -p "$HOME/registry-backups"
snapshot=$(mktemp "$HOME/registry-backups/registry-XXXXXXXX.db")
sqlite3 -readonly "$db" ".backup '$snapshot'"
test "$(sqlite3 -readonly "$snapshot" 'PRAGMA integrity_check;')" = ok || exit 1
echo "Backup saved: $snapshot"
~~~

Giữ ít nhất một snapshot đã kiểm tra `integrity_check=ok`. Backup chứa metadata và hash credential, cần được bảo vệ. **Không xóa/ghi đè database production để sửa lỗi tài liệu hoặc Companion.**

## 5. Cập nhật backend có kiểm soát

Chỉ áp dụng **khi code backend hoặc cấu hình server thực sự đổi**. Trước hết kiểm tra release/PR đã review, có kế hoạch rollback và chấp nhận downtime ngắn.

~~~bash
cd /home/registryadmin/agent-registry
git status --short --branch
git branch --show-current
git rev-parse HEAD
git fetch origin main
git log --oneline HEAD..origin/main
~~~

Nếu working tree không sạch, dừng lại kiểm tra; **không** dùng `git reset --hard` tùy tiện. Khi đã backup và xác nhận muốn triển khai:

~~~bash
cd /home/registryadmin/agent-registry
git pull --ff-only origin main
./.venv/bin/python -m pip install -r requirements.txt
REGISTRY_DATABASE_URL=sqlite:///:memory: ./.venv/bin/python -m pytest -q
sudo systemctl daemon-reload
sudo systemctl restart agent-registry
sudo systemctl status agent-registry --no-pager
curl --retry 8 --retry-connrefused --retry-delay 1 -fsS http://127.0.0.1:8000/v1/health
curl -fsS https://103-180-134-53.sslip.io/v1/health
~~~

`git pull` chỉ thay file; `systemctl restart` mới nạp code backend. Nếu có thay đổi schema hoặc authentication, cần đánh giá migration/khả năng rollback riêng trước khi restart. Caddy không cần reload nếu không đổi Caddyfile.

**Sau deploy:** kiểm tra một Agent đã đăng ký có thể authenticated re-register/heartbeat, discovery từ Client và Dashboard, không chỉ health 200.

## 6. Giám sát và xử lý sự cố

| Hiện tượng | Kiểm tra |
|---|---|
| HTTPS lỗi, loopback OK | DNS, chứng chỉ, service Caddy, upstream, firewall 443. |
| Cả HTTPS và loopback lỗi | `systemctl status agent-registry`, `journalctl`, port 8000, DB. |
| `403` khi tạo ID | Join Token thiếu/sai; xin token hiện hành qua kênh riêng. |
| `503` chỉ khi tạo ID | Admission file thiếu/không đọc được hoặc creation đã bị khóa. |
| `401` với ID cũ | Ownership credential không hợp lệ; Join Token không giúp sửa ID cũ. |
| `409` heartbeat | Authenticated re-register bằng card và credential cũ. |
| `ONLINE` nhưng Consumer không gọi được | Kiểm tra endpoint và business auth **từ máy Consumer**. |

Bảo đảm Caddy/monitoring **không log** headers `Authorization` và `X-Registry-Join-Token`. Backend không có account/quota/rate limiting theo nhóm.

### Rollback / khôi phục SQLite

- **Chỉ lỗi code:** xem xét revert commit/deploy phiên bản tương thích; thông thường **không cần restore database**.
- **Lỗi dữ liệu:** chỉ restore từ snapshot đã kiểm tra khi được phê duyệt. Phải dừng mọi writer, giữ nguyên bản DB hiện hành và tất cả file `-wal`/`-shm` để có đường quay lại, không trộn WAL cũ với snapshot mới.
- Restore snapshot cũ có thể **mất Agent registration/ownership phát sinh sau thời điểm backup**; ghi nhận tác động và thông báo các Provider trước khi thao tác.
- Không quay lại phiên bản cho open registration trên HTTPS production.

## 7. Chạy một instance local riêng

Chỉ dùng để phát triển hoặc test độc lập, không phải Registry production:

~~~powershell
git clone https://github.com/HPHind110/agent-registry.git
cd agent-registry
py -3 -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements.txt
$env:REGISTRY_ALLOW_OPEN_REGISTRATION = "1"
.\.venv\Scripts\python -m uvicorn registry.main:app --host 127.0.0.1 --port 8000
~~~

Local mặc định dùng `./registry.db`, tách biệt SQLite VPS. Tuyệt đối không dùng open registration cho môi trường Internet. [Verification](verification.md)
