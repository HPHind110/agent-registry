# Kết nối một HTTP Agent đang chạy với Registry

Companion là một tiến trình nhỏ chạy trên máy Provider. Nó đọc hai file Dashboard cấp, kiểm tra sức khỏe Agent và duy trì lease. Agent có thể viết bằng Java, Go, Node.js, Python hoặc ngôn ngữ khác. Máy chạy Companion cần Python 3.11 trở lên. Không cần pip, SDK, quyền admin hoặc clone repo.

## 1. Chuẩn bị hai địa chỉ

- **Health URL** dùng riêng trên máy Provider. Chọn URL mà Agent thực sự hỗ trợ, ví dụ `http://127.0.0.1:9000/health`. Companion gửi GET và coi HTTP 2xx là khỏe; nội dung JSON không được diễn giải. Endpoint này nên trả 503 khi Agent chưa sẵn sàng. Trang đăng nhập hoặc trang tĩnh luôn trả 200 không phản ánh sức khỏe nghiệp vụ.
- **Endpoint trên Agent Card** là URL Consumer gọi cho nghiệp vụ. Với demo nhiều máy, dùng địa chỉ mà Consumer truy cập được. Nếu card chứa `127.0.0.1`, Consumer trên máy khác sẽ gọi chính máy của họ.

Bật Agent theo hướng dẫn của nhóm bạn. Mở health URL trên máy Provider. Để Companion làm chủ lifecycle, tắt chế độ tự heartbeat của SDK/sidecar khác cho cùng ID (với demo News có thể chọn MANUAL).

## 2. Đăng ký và tải ba file

1. Mở [Dashboard của nhóm](https://103-180-134-53.sslip.io/). Chọn **Đăng ký Agent**, nhập card và join token do quản trị viên cấp qua kênh riêng. Nếu ID đã tồn tại, dùng credential của chủ sở hữu. Không tạo lại ID chỉ để dùng Companion.
2. Ở hộp thoại thành công, bấm **Tải credential** và **Tải cấu hình JSON**. Đặt hai file trong thư mục chỉ tài khoản chạy Provider đọc được, ngoài Git. Giữ đúng tên file. Đường dẫn tương đối trong `AGENT_CREDENTIAL_FILE` được tính từ **thư mục chứa JSON**; đường dẫn tuyệt đối cũng dùng được.
3. Tải [registry-companion-kit.zip](../downloads/registry-companion-kit.zip?raw=true) rồi **giải nén toàn bộ** vào một thư mục cá nhân có quyền ghi, ngoài Git. Giữ nguyên bốn file trong cùng thư mục. Nếu dùng CLI trực tiếp, chỉ cần tải [registry-companion.pyz](../downloads/registry-companion.pyz?raw=true). Trên GitHub có thể chọn **Download raw file**.

| File | Nội dung |
|---|---|
| `agent-example.json` | Registry URL, Agent ID, name, domain, description, capabilities, endpoint, version và **đường dẫn** file credential |
| `agent-example.credential` | Ownership credential do Registry cấp một lần |
| `registry-companion.pyz` | Chương trình dùng chung cho mọi Provider |

Kiểm tra `REGISTRY_URL` trong JSON trỏ đúng Registry tin cậy trước khi chạy. Chỉ cấp cấu hình từ nguồn tin cậy vì nó xác định nơi gửi credential. Companion chấp nhận Registry HTTPS với xác minh chứng chỉ mặc định hoặc HTTP loopback để test local. Nó không theo redirect, không gửi join token và không đính kèm Bearer khi kiểm tra Agent.

## 3. Chạy Companion

### Lần đầu và những lần sau bằng launcher

1. Bật ứng dụng Agent và chuẩn bị health URL của nó. Trên **Windows**, nhấp đúp `registry-companion-start.cmd` trong thư mục vừa giải nén. Trên **Linux**, mở terminal tại thư mục đó và chạy `sh ./registry-companion-start.sh`. Máy cần Python 3.11+.
2. Ở dòng **Dashboard JSON path**, nhấn Enter để mở hộp chọn file hoặc dán đường dẫn JSON. Nếu máy thiếu giao diện đồ họa/Tk, nhập đường dẫn ngay trong terminal. Credential vẫn nằm ở vị trí mà JSON chỉ định.
3. Nhập health URL của Agent trên máy này. Dùng URL HTTP(S) trả 2xx khi Agent khỏe và có thể lưu công khai, không kèm token, mật khẩu hay query string.
4. Launcher chạy `check`. Khi kiểm tra thành công, nó lưu profile cạnh launcher, tạo file mở riêng cho ID và chạy `start` ngay trong cửa sổ hiện tại. Đợi dòng **registration ONLINE** để xác nhận ownership. Giữ cửa sổ mở để theo dõi heartbeat. Nhấn **Ctrl+C** để Companion thử graceful unregister.
5. Lần sau, bật Agent rồi mở file **`start-<Agent-ID>-<mã>.cmd`** trên Windows. Trên Linux, nhấp đúp file **`.desktop`** tương ứng và chọn **Allow Launching** nếu desktop yêu cầu. Trên máy không có desktop, chạy `sh ./start-<Agent-ID>-<mã>.sh` với tên thực tế. Mỗi cửa sổ quản lý một Agent.

**Thêm Agent hoặc đổi cấu hình.** Mở lại launcher chung, chọn **N** (New setup), chọn JSON và nhập health URL. Cùng Registry và Agent ID sẽ cập nhật profile cũ sau khi `check` thành công. Nếu JSON bị sửa hoặc chuyển chỗ, launcher riêng yêu cầu thiết lập lại. Hãy kiểm tra `REGISTRY_URL` trước khi xác nhận. Nếu di chuyển thư mục bộ công cụ trên Linux, chạy New setup để cập nhật đường dẫn trong file `.desktop`.

**Các file được lưu.** `start-*.profile.json` chỉ chứa đường dẫn JSON, health URL và mã SHA-256 của JSON để phát hiện thay đổi. Credential tiếp tục được Companion đọc từ `AGENT_CREDENTIAL_FILE`. Muốn bỏ một profile, dừng Companion rồi xóa file profile và các launcher cùng tên. Bạn vẫn giữ được JSON và credential do Dashboard cấp.

### Dùng CLI trực tiếp cho tự động hóa

Ví dụ dưới đặt file `.pyz`, JSON và credential trong `$HOME/agent-config`.

**Windows PowerShell**, thay tên JSON và URL health của bạn:

```powershell
cd "$HOME\agent-config"
py -3 --version
py -3 registry-companion.pyz check --config agent-example.json --health-url http://127.0.0.1:9000/health
if ($LASTEXITCODE -eq 0) {
    py -3 registry-companion.pyz start --config agent-example.json --health-url http://127.0.0.1:9000/health
}
```

**Linux**:

```bash
cd "$HOME/agent-config"
chmod 600 agent-example.credential
python3 --version
python3 registry-companion.pyz check --config agent-example.json --health-url http://127.0.0.1:9000/health &&
python3 registry-companion.pyz start --config agent-example.json --health-url http://127.0.0.1:9000/health
```

`check` chỉ đọc file và gửi GET. Thành công cho biết credential đọc được, Agent trả 2xx và card trên Registry khớp cấu hình. Registry hiện chỉ xác minh **ownership** khi nhận lệnh ghi có Bearer. `start` xác minh điều này bằng re-registration và lấy interval/TTL từ response.

Để chạy lâu dài, giữ terminal Companion mở. Xem Agent trên Dashboard: trạng thái **ONLINE**, `last_heartbeat` và `lease_expires_at` tiến lên qua nhiều chu kỳ. Đóng Dashboard rồi mở lại cũng thấy heartbeat mới.

## 4. Thử dừng và phục hồi

- **Dừng Agent, giữ Companion chạy.** Ngay khi thấy probe lỗi, Companion ngừng gửi heartbeat. Mặc định sau 3 lần probe lỗi liên tiếp, Companion thử graceful unregister. Khi Registry nhận được, card thành UNREGISTERED và ownership còn nguyên. Nếu Registry mất kết nối, lease sẽ tự hết và card có thể chuyển SUSPECT rồi UNREACHABLE.
- **Bật lại Agent**, giữ cùng health URL và config. Companion thấy 2xx, đọc lại card, re-register có Bearer và tiếp tục heartbeat. Nếu Registry ngừng lâu hơn TTL, heartbeat có thể trả 409; Companion tự so khớp card rồi re-register.
- **Dừng Companion bằng Ctrl+C** (Linux cũng hỗ trợ SIGTERM). Sau khi đã attach, Companion thử unregister với timeout ngắn. Kill cưỡng bức hoặc mất điện để Registry tự xử lý bằng TTL. Không cần DELETE.
- **Đổi endpoint có chủ ý:** dừng Companion, mở card trên Dashboard → **Sửa card** bằng ownership credential → nhập endpoint mới → cập nhật đúng `AGENT_ENDPOINT` trong JSON → chạy lại `check` rồi `start`. Làm tương tự với các trường metadata khác. Nếu health URL cũng đổi, cập nhật tham số CLI.

## 5. Các Agent ví dụ

| Project | Config cho identity hiện có | Health URL theo cấu hình mặc định |
|---|---|---|
| [File Organization Agent](https://github.com/HPHind110/file-organizer-agent) | `agent-demo-file-organizer-01.json` | `http://127.0.0.1:8101/health` |
| [Study Planning Agent](https://github.com/HPHind110/study-planning-agent) | `agent-demo-study-planner-01.json` | `http://127.0.0.1:8102/health` |

Thay hai tham số trong cùng lệnh ở mục 3. Nếu vận hành cả hai Agent, mở hai terminal, mỗi Companion quản lý một ID. Không cần sửa repository của hai nhóm.

## 6. Chẩn đoán

| Hiện tượng | Cách xử lý |
|---|---|
| Không đọc được JSON/credential | Kiểm tra tên file sau khi tải (trình duyệt có thể thêm “(1)”), đường dẫn và quyền đọc. Giữ nguyên nội dung khóa. |
| Card differs in … | Đối chiếu trường được báo trên Dashboard. Cập nhật JSON theo card hiện hành hoặc chủ động sửa card trước. |
| Registry 401/403/404 | Kiểm tra Registry URL, ID và đúng ownership credential. Companion dừng. ID thiếu cần xử lý riêng qua Dashboard. |
| Registry 408/429/5xx hoặc lỗi kết nối | `start` retry với exponential backoff có jitter, tối đa 30 giây mỗi lần đợi. Health và Registry có log riêng. |
| Agent health unavailable | Kiểm tra process và health URL trên máy Provider. Health URL cần GET không yêu cầu auth và trả 2xx trực tiếp. |
| Cannot acquire lock | Kiểm tra Companion khác chạy cùng Registry origin, Agent ID và tài khoản hệ điều hành. Khóa do OS giải phóng khi process thoát; không xóa file lock đang dùng. |
| ONLINE nhưng Consumer gọi lỗi | Thử business endpoint từ máy Consumer. Kiểm tra DNS, firewall, mạng và xác thực nghiệp vụ. |

`--timeout` mặc định 3 giây cho socket HTTP; `--poll-interval` mặc định 2 giây; `--failure-threshold` mặc định 3, tối thiểu 2. Companion cũng probe khi đến hạn heartbeat. Mã thoát 0 cho kiểm tra thành công hoặc dừng bình thường, 2 cho lỗi cấu hình/ownership/card/lock, 3 cho lỗi tạm thời khi chạy `check`. Một lần `check` không gia hạn lease.

**Giới hạn:** Dùng duy nhất một chủ thể ghi lifecycle cho mỗi ID. Lock không phát hiện SDK, máy khác, tài khoản OS khác hoặc hostname alias. Registry v1 nhận cả card khi re-register và chưa có conditional write/instance fencing; tránh sửa card đồng thời trong khoảng từ GET đến POST. Companion đọc lại card trước mỗi re-registration và từ chối khi metadata khác. Health local phản ánh HTTP tại thời điểm probe, không chứng minh reachability từ xa. Companion không mở port, tạo tunnel, triển khai business auth, xử lý message broker hoặc định nghĩa giao thức invocation.

## 7. Build dành cho người bảo trì

Tại repo, chạy `python scripts/build_companion.py`. Script tạo `downloads/registry-companion.pyz` và `downloads/registry-companion-kit.zip` với timestamp và newline cố định. ZIP gồm bản CLI đó, hai launcher và `registry_companion_launcher.py`. Chạy `python -m pytest tests/test_companion.py tests/test_companion_launchers.py -q` để kiểm tra artifact và các luồng CLI/launcher. Trên Windows test gọi CMD, trên Linux test gọi `/bin/sh`. Có thể kiểm tra mã SHA-256 bằng `Get-FileHash` hoặc `sha256sum`.

[README](../README.md) · [Registry API](api_contract.md) · [Tích hợp SDK hoặc REST](agent_integration.md)
