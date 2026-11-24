# Deployment & Operations — Local và HTTPS VPS

[README](../README.md) · [Architecture](architecture.md) · [Agent Integration](agent_integration.md) · [Verification](verification.md)

Tài liệu này phân biệt **chạy Registry** (process/backend/database) với **truy cập Registry** (browser, CLI, HTTPS và REST API). Ví dụ dùng Ubuntu 24.04 và Windows PowerShell. Đường dẫn, username, IP và port phải được điều chỉnh theo môi trường thực tế.

## Rollout HTTPS và join token

Địa chỉ Dashboard do nhóm cung cấp là [https://103-180-134-53.sslip.io](https://103-180-134-53.sslip.io). Browser, Provider và Consumer dùng cùng HTTPS origin cho API Registry. Trên Ubuntu, Caddy nhận HTTPS, chuyển tiếp tới Uvicorn trên loopback. systemd quản lý ứng dụng; SQLite nằm ngoài checkout. Phần này là quy trình cho người vận hành. Registry đã được xác minh thủ công bằng HTTPS và loopback health check trên VPS ngày 24/11/2026; điều đó không thay thế kiểm thử tất cả API hoặc tải production.

### 1. Kiểm tra trước khi cập nhật

Chạy trên VPS. Đối chiếu đường dẫn thật nếu cách cài khác ví dụ. Kiểm tra thông tin agent trước/sau bằng cùng một ID hiện có. GET không gia hạn lease.

~~~bash
cd /home/registryadmin/agent-registry
git status --short --branch
git rev-parse HEAD
systemctl is-active caddy agent-registry
systemctl show agent-registry -p User -p WorkingDirectory -p FragmentPath
sudo ss -lntp
sudo caddy validate --config /etc/caddy/Caddyfile
curl -fsS http://127.0.0.1:8000/v1/health
curl -fsS https://103-180-134-53.sslip.io/v1/health
~~~

Caddyfile cho site đang phục vụ cần có upstream tương đương đoạn dưới. Giữ các tùy chỉnh hiện hữu. Caddy tự xin và gia hạn chứng chỉ khi DNS trỏ đúng VPS, ACME có thể xác minh hostname và thư mục dữ liệu Caddy ghi được. Giữ cổng Uvicorn trên loopback. Không bật log header/body, trace hoặc access log ghi custom request headers cho site này. Nếu hệ thống đã có access logging, kiểm tra redaction của cả `X-Registry-Join-Token` và `Authorization` ở mọi proxy/APM trước rollout. [Caddy Automatic HTTPS](https://caddyserver.com/docs/automatic-https).

~~~caddyfile
103-180-134-53.sslip.io {
    reverse_proxy 127.0.0.1:8000
}
~~~

### 2. Sao lưu SQLite và kiểm tra khả năng đọc

Trên Ubuntu có CLI `sqlite3`. Chạy với tài khoản service có quyền đọc DB (ví dụ registryadmin). Xác nhận DB nguồn là file đang dùng. Online Backup API chụp snapshot nhất quán kể cả khi có WAL. Bảo vệ bản sao vì nó giữ metadata và hash ownership. [SQLite Backup](https://sqlite.org/backup.html).

~~~bash
set -e
umask 077
db=/var/lib/agent-registry/registry.db
test -f "$db"
mkdir -p "$HOME/registry-backups"
snapshot=$(mktemp "$HOME/registry-backups/registry-XXXXXXXX.db")
sqlite3 -readonly "$db" ".backup '$snapshot'"
test "$(sqlite3 -readonly "$snapshot" 'PRAGMA integrity_check;')" = ok
printf 'SQLite backup saved: %s\n' "$snapshot"
~~~

### 3. Cấu hình admission trước khi đổi code

Chuẩn bị token riêng qua trình quản lý bí mật nếu có. Ví dụ sau **chỉ khởi tạo lần đầu**, tạo file root-only riêng cho admission; token ngẫu nhiên không đi vào history, console hoặc repo. Trao token cho người được phép tạo ID qua kênh riêng. Không chia cho Consumer hoặc Provider đã có ownership credential.

~~~bash
sudo install -d -m 0700 /etc/agent-registry
sudo python3 - <<'PY'
import os, secrets
path = "/etc/agent-registry/admission.env"
fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
with os.fdopen(fd, "w") as out:
    out.write("REGISTRY_ALLOW_OPEN_REGISTRATION=0\n")
    out.write("REGISTRY_JOIN_TOKEN=" + secrets.token_urlsafe(32) + "\n")
PY
sudo systemctl edit agent-registry
~~~

Thêm vào **drop-in**. Dấu trừ cho phép systemd chạy khi file biến môi trường bị thiếu: ứng dụng vẫn phục vụ ID cũ, tự khóa tạo ID mới. Kiểm tra các drop-in khác để bảo đảm không bật chế độ mở ở production. Không in toàn bộ biến môi trường ra log.

~~~ini
[Service]
EnvironmentFile=-/etc/agent-registry/admission.env
~~~

### 4. Cập nhật có kiểm soát

Chờ phiên bản đã review có trên nhánh triển khai. Chạy khi có thể chấp nhận một lần restart Registry. Dùng cùng venv, database và tài khoản hiện tại. Thông báo người dùng giữ nguyên file ownership; lease có thể hết khi downtime dài, SDK sẽ re-register với khóa cũ.

~~~bash
set -e
cd /home/registryadmin/agent-registry
test "$(git branch --show-current)" = main
test -z "$(git status --porcelain)"
git fetch origin main
git log --oneline HEAD..origin/main
git pull --ff-only origin main
grep -q REGISTRY_JOIN_TOKEN registry/config.py
REGISTRY_DATABASE_URL=sqlite:///:memory: ./.venv/bin/python -m pytest -q
sudo systemctl daemon-reload
sudo systemctl restart agent-registry
systemctl is-active agent-registry
curl --retry 8 --retry-connrefused --retry-delay 1 -fsS http://127.0.0.1:8000/v1/health
curl -fsS https://103-180-134-53.sslip.io/v1/health
~~~

Kiểm tra Dashboard hiển thị ô join token khi tạo ID. Dùng môi trường staging cho phép thử POST âm/dương; trên production quan sát một Provider hiện có renew lease thành công. Health 200 chỉ chứng minh endpoint health trả lời. Tính năng này không yêu cầu đổi schema hay restart Caddy. Chỉ khi thực sự đổi Caddyfile mới cần validate rồi `sudo systemctl reload caddy`.

**Đổi token.** Trước khi đổi, chuẩn bị phân phối giá trị mới cho nhóm sắp tạo ID. Chạy đoạn dưới trên VPS khi được phép xoay khóa. Nó thay nguyên tử file *chỉ dành cho admission* và restart Registry để đọc lại môi trường. Chủ sở hữu ID hiện hữu không cần thay file credential. Token cũ hết tác dụng cho ID mới sau restart. Nếu cần tạm khóa tạo ID, để trống token và giữ open registration bằng 0, rồi restart Registry.

~~~bash
sudo python3 - <<'PY'
import os, secrets, tempfile
directory = "/etc/agent-registry"
with tempfile.NamedTemporaryFile(mode="w", dir=directory, delete=False) as out:
    out.write("REGISTRY_ALLOW_OPEN_REGISTRATION=0\nREGISTRY_JOIN_TOKEN=" + secrets.token_urlsafe(32) + "\n")
os.replace(out.name, directory + "/admission.env")
PY
sudo systemctl restart agent-registry
~~~

### 5. Khôi phục dữ liệu khi được phê duyệt

Chỉ dùng sau khi xác định cần phục hồi DB. Rollback code thông thường không cần restore SQLite. Snapshot cũ cũng hoàn nguyên ownership theo thời điểm backup, có thể mất các registration phát sinh sau đó. Giữ bản DB hiện hành và sidecar để có đường quay lại. Thực hiện trong một phiên SSH với đúng service user/đường dẫn.

~~~bash
set -e
db=/var/lib/agent-registry/registry.db
read -r -p 'Absolute path to verified SQLite snapshot: ' snapshot
test -f "$snapshot"
test "$(sqlite3 -readonly "$snapshot" 'PRAGMA integrity_check;')" = ok
sudo systemctl stop agent-registry
# Sau khi đã dừng tất cả writer, giữ cả DB và sidecar nếu có.
hold=$(sudo mktemp -d /var/lib/agent-registry/pre-restore-XXXXXXXX)
for f in "$db" "$db-wal" "$db-shm" "$db-journal"; do
    if sudo test -f "$f"; then sudo mv -- "$f" "$hold/"; fi
done
sudo install -o registryadmin -g registryadmin -m 0600 "$snapshot" "$db"
sudo systemctl start agent-registry
curl --retry 8 --retry-connrefused --retry-delay 1 -fsS http://127.0.0.1:8000/v1/health
~~~

Nếu restore lỗi, giữ service dừng, bảo tồn cả thư mục `pre-restore-*` và file vừa cài trước khi điều tra. Không trộn WAL của DB cũ vào DB đã restore. Với sự cố rollout code, không quay lại bản cho đăng ký công khai khi proxy vẫn mở admission ra Internet.

| Triệu chứng | Cách kiểm tra |
|---|---|
| 403 khi tạo ID | Header join token thiếu/sai hoặc vừa rotate. Dùng token hiện hành qua HTTPS. |
| 503 chỉ khi tạo ID | Kiểm tra owner/mode của admission.env, đường dẫn drop-in và lần restart. Health có thể vẫn OK. |
| 401 với ID đã có | Dùng Bearer credential đúng ID. Join token không khôi phục ownership. |
| 409 khi heartbeat | Re-register cùng card và ownership credential, sau đó tiếp tục heartbeat. |
| Public health lỗi, loopback OK | Kiểm tra DNS, chứng chỉ, Caddy upstream và firewall. Tránh bật log các header bí mật. |

## 1. Chọn mô hình phù hợp

| Mục đích | Registry chạy ở đâu? | URL sử dụng |
|---|---|---|
| Phát triển/kiểm thử độc lập | Uvicorn trên laptop, SQLite local | `http://127.0.0.1:8000` |
| Provider/Consumer sử dụng Registry chung | VPS, systemd + Caddy | `https://103-180-134-53.sslip.io` |
| Vận hành hệ thống | SSH vào VPS để kiểm tra service, backup, triển khai | HTTPS vẫn là URL công khai |

Dashboard (`/`), Swagger (`/docs`) và REST API (`/v1/...`) thuộc **cùng FastAPI app**. Không cần SSH tunnel để các nhóm Provider/Client truy cập Registry chung. Clone repo rồi chạy local tạo **instance riêng**, không kết nối vào database production.

## 2. Chạy Registry local (Windows)

Yêu cầu Python 3.11+ và Git:

```powershell
git clone https://github.com/HPHind110/agent-registry.git
cd agent-registry
python -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements.txt
.\.venv\Scripts\python -m uvicorn registry.main:app --host 127.0.0.1 --port 8000
```

Dùng browser trên **cùng laptop**: `http://127.0.0.1:8000/` (Dashboard), `/docs` (Swagger), `/v1/health` (health). Database mặc định là `./registry.db` trong thư mục làm việc. Kết thúc Uvicorn bằng Ctrl+C.

Nếu repo đã được clone, **không clone lại**: vào đúng thư mục, kiểm tra `git status` trước khi pull/update.

## 3. VPS Ubuntu — bố trí đã kiểm thử thủ công

Ví dụ bố trí triển khai của nhóm:

```text
/home/registryadmin/agent-registry/       # Git checkout + .venv
/var/lib/agent-registry/registry.db        # SQLite durable, ở ngoài source
/etc/systemd/system/agent-registry.service # systemd unit
```

VPS đã được kiểm tra thủ công với Uvicorn lắng nghe tại `127.0.0.1:8000`, service `active (running)`, và `GET /v1/health` trả `status: ok`. Đây **không phải** bằng chứng Registry có thể truy cập trực tiếp từ Internet hoặc đã tích hợp nhóm ngoài.

### 3.1. Kết nối bằng SSH key (Windows)

```powershell
ssh -i "$env:USERPROFILE\.ssh\agent_registry_vps" registryadmin@<VPS_IP>
```

Ví dụ tên user và khóa mang tính môi trường; thay `<VPS_IP>` bằng IP được cấp. **Không đưa mật khẩu, private key, credential, IP cá nhân không cần thiết hoặc các nội dung `.env` có secret vào Git.** SSH key passphrase không phải mật khẩu sudo.

### 3.2. Kiểm tra service (lệnh trên VPS, không phải Windows)

```bash
sudo systemctl status agent-registry --no-pager
curl -fsS http://127.0.0.1:8000/v1/health
sudo ss -lntp | grep ':8000'
sudo journalctl -u agent-registry -n 50 --no-pager
```

Nếu Uvicorn bind `127.0.0.1:8000`, chỉ tiến trình/SSH tunnel trên VPS mới kết nối qua loopback. Không mở port 8000 ra Internet để kiểm thử nhanh khi chưa có TLS/admission control.

### 3.3. Tạo systemd service trên Ubuntu (dành cho VPS mới, không chạy lại nếu đã cài)

Sau khi cài Git, Python 3.11+, `python3-venv`, `python3-pip`; clone source vào `/home/registryadmin/agent-registry`, tạo `.venv` và cài `requirements.txt`:

```bash
sudo install -d -o registryadmin -g registryadmin -m 750 /var/lib/agent-registry
sudo nano /etc/systemd/system/agent-registry.service
```

Ví dụ nội dung unit:

```ini
[Unit]
Description=Agent Registry Service
Wants=network-online.target
After=network-online.target

[Service]
Type=simple
User=registryadmin
Group=registryadmin
WorkingDirectory=/home/registryadmin/agent-registry
Environment="REGISTRY_DATABASE_URL=sqlite:////var/lib/agent-registry/registry.db"
ExecStart=/home/registryadmin/agent-registry/.venv/bin/python -m uvicorn registry.main:app --host 127.0.0.1 --port 8000
Restart=on-failure
RestartSec=5
UMask=0077
NoNewPrivileges=true

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now agent-registry
sudo systemctl status agent-registry --no-pager
curl -fsS http://127.0.0.1:8000/v1/health
```

**Không chạy đồng thời Uvicorn thủ công và systemd ở cùng port 8000.** `enable` cấu hình tự khởi động khi boot; muốn xác minh sau reboot cần thực hiện một bài thử có kiểm soát riêng. Chưa có Docker; không cần Docker chỉ để chạy một Registry instance.

## 4. Truy cập Registry qua HTTPS

**Dashboard:** https://103-180-134-53.sslip.io/  
**Swagger:** https://103-180-134-53.sslip.io/docs  
**Health:** https://103-180-134-53.sslip.io/v1/health

Caddy nhận kết nối HTTPS và reverse-proxy đến Uvicorn `127.0.0.1:8000`. Không mở port 8000 ra Internet. Nếu health loopback chạy nhưng HTTPS lỗi, kiểm tra Caddy, DNS, chứng chỉ và firewall cổng 443.

Provider/Consumer dùng cùng base URL HTTPS. Health của Registry **không phải** health của Provider; Consumer vẫn phải thử business endpoint từ máy của họ.

## 5. Cập nhật code VPS từ GitHub

### 5.1. Laptop / Codex

Kiểm thử trên máy phát triển, review thay đổi, commit và push/merge lên `main`. Nếu Codex đã merge thì không cần push lại. Không commit database/credential/private key/`.env`.

### 5.2. VPS — dưới tài khoản registryadmin

```bash
cd ~/agent-registry
sudo systemctl status agent-registry --no-pager
git status
git branch --show-current
git rev-parse HEAD       # lưu mã commit trước khi cập nhật
git fetch origin main
git log --oneline HEAD..origin/main
git pull --ff-only origin main
./.venv/bin/python -m pip install -r requirements.txt
./.venv/bin/python -m pytest -q
```

**Chỉ khi test đạt và không có migration/DB compatibility issue chưa được giải quyết**, áp dụng code mới:

```bash
sudo systemctl restart agent-registry
sudo systemctl status agent-registry --no-pager
curl -fsS http://127.0.0.1:8000/v1/health
sudo journalctl -u agent-registry -n 50 --no-pager
```

Với `Type=simple`, `systemctl restart` không đảm bảo Uvicorn đã sẵn sàng nhận HTTP request ngay lập tức. Nếu `curl` bị `Connection refused` trong khoảnh khắc đầu, thử lại và xem log. Luôn kiểm thử thêm chức năng vừa thay đổi, vì health 200 chưa chứng minh mọi API đúng.

`git pull` chỉ cập nhật file, `systemctl restart` mới khởi chạy lại code; chúng là **hai bước khác nhau**. Git checkout không tự xóa database nằm ngoài repository. Dẫu vậy, nếu sửa schema/database/credential, phải sao lưu nhất quán (SQLite backup API) và lên kế hoạch migration trước khi deploy. Không chạy `git reset --hard` nếu VPS có thay đổi local chưa được đối chiếu.

### 5.3. Một số lệnh vận hành

```bash
sudo systemctl restart agent-registry      # áp dụng code/config khi cần
sudo systemctl status agent-registry --no-pager
sudo journalctl -u agent-registry -f       # Ctrl+C chỉ ngừng xem log
```

Khi SSH `exit`, service vẫn chạy trên VPS. Provider/Client dùng HTTPS nên không cần giữ SSH tunnel. Phiên SSH dành cho người vận hành có thể thoát bằng `exit` mà không dừng service.

## 6. Đưa Registry cho nhiều máy / nhóm ngoài

Registry đã được kiểm tra truy cập qua HTTPS, nhưng điều đó **chưa** đồng nghĩa Client có thể gọi mọi business endpoint của Provider từ máy riêng.

Cần kiểm chứng độc lập:

1. Provider và Consumer có thể kết nối tới **base URL Registry chung** (HTTPS hoặc mạng riêng/overlay được cho phép).
2. Provider đăng ký bằng REST/SDK, giữ credential riêng, tự heartbeat và re-register khi cần.
3. Consumer discovery qua Registry rồi gọi **trực tiếp Provider endpoint** đã công bố; endpoint đó phải reachable từ mạng của Consumer.

Nếu Provider chỉ công bố `http://192.168.x.x:8001/...` trong mạng nhà riêng, Consumer ở mạng khác thường không gọi được, dù discovery thành công. Registry **không** làm NAT traversal hoặc chuyển tiếp business requests.

Bản cập nhật yêu cầu join token cho ID mới. TLS kết thúc ở Caddy. Registry chưa có tài khoản quản trị, quota theo nhóm hoặc rate limiting. **Không đưa thẳng HTTP/port 8000 và Dashboard ra Internet**. Cần quyết định mạng riêng hoặc reverse proxy HTTPS, giới hạn quyền truy cập và firewall trước khi dùng chung.

Với LAN thử nghiệm có kiểm soát, có thể chạy **một Registry khác trên laptop** bind `0.0.0.0`, giới hạn firewall và dùng IP LAN để các máy gọi tới. Đây là môi trường kiểm thử **tách biệt database** với VPS.

## 7. Troubleshooting nhanh

| Hiện tượng | Kiểm tra |
|---|---|
| `curl 127.0.0.1:8000` trên VPS thất bại | `systemctl status`, `journalctl`, `ss -lntp`; thử lại sau startup |
| URL HTTPS không mở được nhưng loopback OK | Kiểm tra Caddy, DNS, TLS và cổng 443. |
| Localhost 8000 có dữ liệu khác production | Đây là hai Registry/database độc lập. |
| Agent đăng ký được nhưng Client không gọi được | Kiểm tra endpoint Provider reachable từ **Client**, firewall, method và business schema |
| `git pull --ff-only` từ chối | Xem `git status`, branch, commit; không reset mù |
| `401` khi re-register | Credential của Agent ID sai/mất, không tự tạo ID khác để chiếm |
| Dashboard bấm “Hủy đăng ký” | Hiện triển khai gọi **DELETE**: xóa record và ownership, không giống graceful unregister |

## 8. Giới hạn kết quả đã kiểm tra

Ngày 24/11/2026 đã kiểm tra thủ công Ubuntu VPS với systemd active, SQLite bền vững và `/v1/health` trả OK qua cả loopback lẫn HTTPS. Còn thiếu kiểm thử độc lập liên nhóm, nhiều laptop/mạng, tải production và reboot recovery đầy đủ. Xem [Verification](verification.md).
