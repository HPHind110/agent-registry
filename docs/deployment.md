# Deployment & Operations — Local, VPS, SSH tunnel

[README](../README.md) · [Architecture](architecture.md) · [Agent Integration](agent_integration.md) · [Verification](verification.md)

Tài liệu này phân biệt **chạy Registry** (process/backend/database) với **truy cập Registry** (browser, CLI, SSH tunnel, REST API). Ví dụ dùng Ubuntu 24.04 và Windows PowerShell. Đường dẫn, username, IP và port phải được điều chỉnh theo môi trường thực tế.

## 1. Chọn mô hình phù hợp

| Mục đích | Registry process | Client/browser kết nối bằng | Lưu ý |
|---|---|---|---|
| Phát triển/kiểm thử local | Uvicorn trên Windows | `http://127.0.0.1:8000` | SQLite local, không phải dữ liệu VPS |
| Kiểm tra Registry đã deploy | systemd/Uvicorn trên Ubuntu VPS | SSH local-forward `http://127.0.0.1:18000` trên laptop | Tunnel **không** tạo Registry mới |
| Tích hợp Agent nhiều máy (LAN) | Một Registry bind IP LAN phù hợp | IP/DNS reachable từ từng Agent/Client | Cần firewall và endpoint Provider reachable |
| Tích hợp qua VPS/mạng khác nhau | VPS có điểm truy cập mạng chung | URL HTTPS hoặc overlay/private network do nhóm triển khai | **Chưa hoàn tất** chỉ nhờ SSH tunnel; cần bảo vệ API |

Web Dashboard (`/`), Swagger (`/docs`) và REST API (`/v1/...`) là các đường dẫn của **cùng ứng dụng FastAPI**. `127.0.0.1` luôn là máy **đang gọi** URL, không phải tên chung của Registry trên Internet.

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

## 4. Mở Dashboard VPS qua SSH tunnel

Trên **Windows PowerShell ngoài phiên SSH**:

```powershell
ssh -i "$env:USERPROFILE\.ssh\agent_registry_vps" -N -L 18000:127.0.0.1:8000 registryadmin@<VPS_IP>
```

Giữ cửa sổ này mở, dùng **browser trên cùng laptop**:

- `http://127.0.0.1:18000/`: Dashboard của **VPS**
- `http://127.0.0.1:18000/docs`: Swagger của **VPS**
- `http://127.0.0.1:18000/v1/health`: API health của **VPS**

Giải thích `-N`: chỉ chuyển tiếp, không mở shell. `-L 18000:127.0.0.1:8000`: cổng `18000` của laptop đi qua SSH đến `127.0.0.1:8000` của VPS. Cửa sổ trông như đứng yên là bình thường; Ctrl+C sẽ đóng tunnel **nhưng không dừng systemd service**.

**Đừng nhầm:** `http://127.0.0.1:18000` trên laptop A không phải URL mà laptop B có thể dùng để truy cập VPS. Khi Client dùng chính tunnel trên laptop A, nó có thể đặt `REGISTRY_URL=http://127.0.0.1:18000`; điều này chỉ giải quyết Client ↔ Registry, **không** giúp Client gọi Provider ở mạng khác.

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

Khi SSH `exit`, service vẫn chạy trên VPS. Nếu đang mở **tunnel riêng** thì phiên tunnel đó vẫn cần được giữ để laptop truy cập qua `18000`.

## 6. Đưa Registry cho nhiều máy / nhóm ngoài

Một deployment thành công trên VPS và truy cập được qua SSH tunnel **chưa** đồng nghĩa Agent của nhóm khác có thể dùng Registry từ máy riêng.

Cần kiểm chứng độc lập:

1. Provider và Consumer có thể kết nối tới **base URL Registry chung** (HTTPS hoặc mạng riêng/overlay được cho phép).
2. Provider đăng ký bằng REST/SDK, giữ credential riêng, tự heartbeat và re-register khi cần.
3. Consumer discovery qua Registry rồi gọi **trực tiếp Provider endpoint** đã công bố; endpoint đó phải reachable từ mạng của Consumer.

Nếu Provider chỉ công bố `http://192.168.x.x:8001/...` trong mạng nhà riêng, Consumer ở mạng khác thường không gọi được, dù discovery thành công. Registry **không** làm NAT traversal hoặc chuyển tiếp business requests.

Hiện Registry chưa có admission control cho Agent ID mới, tài khoản quản trị Dashboard, rate limiting hoặc TLS do chính FastAPI xử lý. **Không đưa thẳng HTTP/port 8000 và Dashboard ra Internet**. Cần quyết định mạng riêng hoặc reverse proxy HTTPS, giới hạn quyền truy cập và firewall trước khi dùng chung.

Với LAN thử nghiệm có kiểm soát, có thể chạy **một Registry khác trên laptop** bind `0.0.0.0`, giới hạn firewall và dùng IP LAN để các máy gọi tới. Đây là môi trường kiểm thử **tách biệt database** với VPS.

## 7. Troubleshooting nhanh

| Hiện tượng | Kiểm tra |
|---|---|
| `curl 127.0.0.1:8000` trên VPS thất bại | `systemctl status`, `journalctl`, `ss -lntp`; thử lại sau startup |
| `127.0.0.1:18000` trên Windows không mở được | SSH tunnel còn mở? VPS service còn chạy? Cổng 18000 có bị chiếm? |
| Web localhost 8000 và tunnel 18000 có dữ liệu khác | Hai Registry/database khác nhau; đúng theo mô hình |
| Agent đăng ký được nhưng Client không gọi được | Kiểm tra endpoint Provider reachable từ **Client**, firewall, method và business schema |
| `git pull --ff-only` từ chối | Xem `git status`, branch, commit; không reset mù |
| `401` khi re-register | Credential của Agent ID sai/mất, không tự tạo ID khác để chiếm |
| Dashboard bấm “Hủy đăng ký” | Hiện triển khai gọi **DELETE**: xóa record và ownership, không giống graceful unregister |

## 8. Giới hạn kết quả đã kiểm tra

Đã có quan sát thủ công về Ubuntu VPS, `systemd active (running)`, SQLite file tồn tại, `/v1/health` trả OK, và lần kiểm tra restart sau đã thành công. Chưa tuyên bố đã kiểm thử LAN nhiều laptop, Internet public exposure, HTTPS, cross-team integration hay reboot recovery. Xem [Verification](verification.md).
