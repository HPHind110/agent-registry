# Provider Onboarding — Registry Lifecycle Companion

Hướng dẫn mặc định cho **nhóm đã có HTTP Agent**. Không phải sửa source Agent, clone Registry hay cài SDK vào project. Companion chạy cạnh Agent và tự quản lý re-registration, heartbeat, phát hiện health lỗi và phục hồi.

**Liên kết:** [Dashboard HTTPS](https://103-180-134-53.sslip.io/) · [Tải Companion v1.0](https://github.com/HPHind110/agent-registry/releases/tag/companion-v1.0.0) · [README](../README.md)

## 1. Chuẩn bị

Cần có:

- HTTP Agent đang chạy; ví dụ `http://127.0.0.1:8101/`.
- **Health URL**: GET trả 2xx khi Agent khỏe, ví dụ `http://127.0.0.1:8101/health`. Không dùng trang tĩnh luôn trả 200 hay URL cần token. Nếu Agent không có health URL phù hợp, cần chọn cách kiểm tra liveness đáng tin cậy khác trước khi dùng Companion.
- **Business endpoint**: URL Client thực sự gọi, ví dụ `/plans` hoặc `/tasks`. Endpoint này phải truy cập được **từ máy Client**, không chỉ từ máy Provider.
- Python **3.11+** trên máy chạy Companion.

## 2. Đăng ký và giữ hai file

1. Mở [Dashboard](https://103-180-134-53.sslip.io/) → **Đăng ký Agent**.
2. Điền Agent ID, tên, domain, capabilities, business endpoint, version, mô tả. **ID mới** cần Join Token cấp riêng; ID đã tồn tại dùng ownership credential cũ để đăng ký lại.
3. Sau khi tạo thành công, tải **cả hai**: `agent-<id>.json` và `agent-<id>.credential`. Credential được cấp khi tạo ID mới, không thể lấy lại qua discovery.
4. Đặt JSON và credential **cạnh nhau**, ngoài thư mục Git, trong folder chỉ người vận hành đọc được (ví dụ `C:\Users\<user>\agent-config\`). Không đăng credential lên GitHub hoặc gửi nó cho Client.

`AGENT_CREDENTIAL_FILE` trong JSON thường là tên file tương đối và được tính từ **thư mục chứa JSON**. Không phải đặt hai file vào source folder Agent.

## 3. Tải và chạy launcher (khuyến nghị)

Tải asset **`registry-companion-kit.zip`** từ [Release v1.0](https://github.com/HPHind110/agent-registry/releases/tag/companion-v1.0.0). Giải nén **toàn bộ** ZIP vào một thư mục có quyền ghi, ví dụ `agent-config\companion-kit\`. Giữ nguyên bốn file gốc:

- `registry-companion-start.cmd` (Windows)
- `registry-companion-start.sh` (Linux)
- `registry_companion_launcher.py`
- `registry-companion.pyz`

**Windows:** bật Agent, nhấp đúp `registry-companion-start.cmd`. Tại `Dashboard JSON path`, nhấn Enter để chọn file hoặc dán đường dẫn JSON. Nhập health URL khi được hỏi. Launcher thực hiện `check`, lưu profile, tạo `start-<id>-<mã>.cmd` và chạy lifecycle ngay. **Giữ cửa sổ mở**.

**Linux:** bật Agent, mở terminal trong thư mục giải nén, chạy `sh ./registry-companion-start.sh`. Launcher tạo profile và launcher `start-...sh` (cùng `.desktop` nếu phù hợp).

**Lần sau:** bật API của Agent rồi mở `start-...cmd` (Windows) hoặc launcher riêng trên Linux. Không cần chọn lại JSON/health URL. Nếu cấu hình thay đổi hoặc cần thêm Agent, chạy **launcher chung** và chọn `N` (New setup). Mỗi Agent ID có profile và tiến trình Companion riêng.

**Không chạy đồng thời Companion, SDK hay adapter khác cùng quản lý lifecycle cho một Agent ID.** Khi dừng bình thường, nhấn `Ctrl+C` để Companion cố gắng graceful unregister, giữ ownership.

## 4. Kiểm tra kết quả

Dấu hiệu thành công trong terminal:

~~~text
[INFO] Agent health: healthy
[INFO] Ownership verified; registration ONLINE (heartbeat every 10s).
[INFO] Heartbeat accepted.
~~~

Trên Dashboard, xem `status`, `last_heartbeat` và `lease_expires_at`. Chờ qua vài chu kỳ (mặc định heartbeat mỗi 10 giây), kiểm tra thời gian tiếp tục cập nhật.

Kiểm thử khôi phục:

1. Dừng **API Agent** nhưng giữ Companion chạy. Companion ngừng heartbeat ngay khi phát hiện probe lỗi; mặc định sau ba lần lỗi liên tiếp sẽ cố gắng gửi `POST /unregister`.
2. Nếu thành công, Registry hiển thị `UNREGISTERED`; nếu Registry không truy cập được, lease sẽ tự hết và có thể chuyển thành `UNREACHABLE`.
3. Bật lại API Agent. Companion sẽ re-register bằng credential cũ và tiếp tục heartbeat.

Health check chỉ chứng minh Agent phản hồi **từ máy Provider**; không chứng minh business endpoint có thể được gọi từ máy khác.

## 5. Dùng CLI trực tiếp (tùy chọn)

Không cần launcher nếu muốn tự động hóa:

~~~powershell
cd "$HOME\agent-config"
py -3 .\companion-kit\registry-companion.pyz check --config .\agent-my-agent.json --health-url http://127.0.0.1:9000/health
py -3 .\companion-kit\registry-companion.pyz start --config .\agent-my-agent.json --health-url http://127.0.0.1:9000/health
~~~

`check` chỉ đọc file và gửi GET; **không xác minh ownership bằng thao tác ghi**. `start` mới re-register với Bearer credential để xác minh ownership và giữ lease.

## 6. Ví dụ đã kiểm thử

| Agent | Cấu hình Dashboard | Health URL local |
|---|---|---|
| [File Organizer](https://github.com/HPHind110/file-organizer-agent) | `agent-demo-file-organizer-01.json` | `http://127.0.0.1:8101/health` |
| [Study Planner](https://github.com/HPHind110/study-planning-agent) | `agent-demo-study-planner-01.json` | `http://127.0.0.1:8102/health` |

Đây chỉ là **ví dụ**; launcher không hard-code framework, Agent ID hoặc port.

## 7. Lỗi thường gặp

| Hiện tượng | Cần làm gì |
|---|---|
| JSON/credential missing | Đối chiếu tên file, quyền đọc và `AGENT_CREDENTIAL_FILE` (tính từ folder JSON). |
| `Registry card differs in ...` | So với Dashboard; nếu chủ động đổi endpoint, cập nhật card bằng credential, đồng bộ JSON rồi New setup. |
| `401` / `404` | Credential không thuộc ID hoặc ID không tồn tại; không tạo ID mới tự động. |
| Registry/network lỗi tạm thời | `start` tự retry/backoff; kiểm tra HTTPS và kết nối mạng. |
| Health unavailable | Bật API, kiểm tra đúng URL GET 2xx và port. |
| Cannot acquire lock | Dừng Companion trùng cùng ID, không xóa lock đang được dùng. |
| Profile yêu cầu New setup | JSON bị đổi/chuyển; chọn lại file trong launcher chung. |
| `ONLINE` nhưng Client gọi lỗi | Kiểm tra business endpoint **từ máy Client**, firewall, HTTP method và business auth. |

**Bảo mật:** Companion chỉ gửi ownership credential đến Registry HTTPS tin cậy, không gửi sang Agent health API, không lưu secret vào profile. Mỗi Agent ID nên có duy nhất một lifecycle owner. Launcher không tự mở port, tạo tunnel, kết nối Broker hay tự định nghĩa schema nghiệp vụ.

[REST API](api_contract.md) · [Tích hợp nâng cao](agent_integration.md)
