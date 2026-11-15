# Agent Registry — lifecycle tự động

Python 3.11+, FastAPI/Uvicorn, Pydantic, SQLAlchemy/SQLite, pytest/httpx. Registry quản lý tên, binding và trạng thái suy luận; Travel discovery rồi gọi Weather trực tiếp. Weather trả dữ liệu mẫu cố định, không gọi API thời tiết thật.

## Kiến trúc thực tế

- `registry/routes.py`, `schemas.py`: REST, Bearer auth, validation/OpenAPI.
- `registry/service.py`: ownership, register, discovery, cập nhật và unregister.
- `registry/database.py`: ORM và migration SQLite bổ sung cột withdrawn.
- `registry/leases.py`: trạng thái tính từ clock server; `health.py`: quan sát thay đổi để ghi log.
- `registry/dashboard.html`: web tổng quát; chỉ refresh GET, không gửi heartbeat.
- `demo/registry_client.py`: lifecycle dùng lại được; `weather_agent.py`: tích hợp bằng FastAPI lifespan.
- `demo/travel_client.py`: discovery và gọi trực tiếp endpoint nhận được.

## Cài đặt và kiểm tra (PowerShell)

```powershell
Set-Location C:\agent-registry
python -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements.txt
.\.venv\Scripts\python -m pytest -q
node --test tests/dashboard.test.cjs
.\.venv\Scripts\python scripts/smoke_test.py
```

Node chỉ dùng cho test controller giao diện, không cần để chạy dịch vụ. `.env.example` không được tự nạp; đặt biến bằng PowerShell. Không cần activate venv.

## Ba terminal

Terminal 1 — Registry:

```powershell
Set-Location C:\agent-registry
$env:REGISTRY_TTL_SECONDS = '30'
$env:REGISTRY_HEARTBEAT_SECONDS = '10'
$env:REGISTRY_SUSPECT_SECONDS = '20'
.\.venv\Scripts\python -m uvicorn registry.main:app --port 8000
```

Terminal 2 — Weather (một worker, không dùng --lifespan off):

```powershell
Set-Location C:\agent-registry
$env:REGISTRY_URL = 'http://127.0.0.1:8000'
$env:WEATHER_AGENT_ID = 'weather-lifecycle-demo'
$env:WEATHER_ENDPOINT = 'http://127.0.0.1:8001/forecast'
$env:WEATHER_CREDENTIAL_FILE = 'weather-lifecycle-demo.credential'
.\.venv\Scripts\python -m uvicorn demo.weather_agent:app --port 8001
```

Terminal 3 — Travel:

```powershell
Set-Location C:\agent-registry
$env:REGISTRY_URL = 'http://127.0.0.1:8000'
.\.venv\Scripts\python -m demo.travel_client --city Hanoi
Invoke-RestMethod 'http://127.0.0.1:8000/v1/agents/weather-lifecycle-demo/status'
```

Web: http://127.0.0.1:8000/ ; Swagger: http://127.0.0.1:8000/docs ; health Registry: http://127.0.0.1:8000/v1/health ; health Weather: http://127.0.0.1:8001/health . Root Registry là dashboard; các URL còn lại là API/tài liệu.

## Demo có thể quan sát

1. Start ba terminal như trên. Weather tự đăng ký, lưu credential rồi heartbeat mỗi 10s. Không bấm heartbeat; web đã bỏ nút đó.
2. Đợi hơn 90s: Agent vẫn ONLINE qua nhiều lease cycle. Đóng browser không ảnh hưởng. TTL không giới hạn thời gian chạy service.
3. Crash: dùng Task Manager kết thúc đúng process Weather (xem PID trong log), không Ctrl+C. Mở browser vẫn không giữ Agent sống. Tính từ heartbeat cuối: dưới 20s ONLINE, từ 20s SUSPECT, từ 30s UNREACHABLE. Discovery chỉ trả ONLINE; chọn Tất cả trạng thái trên web để quan sát.
4. Khởi động Weather lại, giữ ID và file credential, đổi `$env:WEATHER_ENDPOINT = 'http://127.0.0.1:9005/forecast'` và lệnh Uvicorn `--port 9005`. Cùng identity trở về ONLINE với binding mới. Chạy lại Travel để nhận endpoint mới.
5. Graceful: Ctrl+C ở Weather. Nó hủy task heartbeat, gửi `/unregister` có xác thực trong tối đa 4s. Registry chuyển UNREGISTERED, giữ khóa; restart hoạt động bình thường. Nếu Registry đang mất kết nối thì shutdown vẫn hoàn tất, lease tự hết.
6. Partial failure: giữ Weather chạy, dừng Registry hơn 30s. `/forecast` và `/health` của Weather vẫn trả lời; log báo reconnect. Bật Registry với cùng DB: Weather thử heartbeat, nếu 409 thì tự đăng ký lại. Cuối cùng discovery lại thấy ONLINE.
7. Không reset DB giữa các bước: mất DB là mất ownership, khác với Registry restart.

Smoke tự động dùng DB/credential/port riêng, TTL=3s, heartbeat=1s. Bộ runner chỉ dành cho test: file điều khiển riêng cho phép process tự thoát đột ngột hoặc shutdown tử tế; không thêm API điều khiển vào service. Log server được in khi smoke thất bại.

## Đăng ký bằng web trước

Đăng ký card không khởi chạy chương trình Agent. Lưu credential một lần vào file riêng, ví dụ `weather-lifecycle-demo.credential`, chỉ chứa khóa (UTF-8 không BOM), cấu hình Weather đúng cùng ID và đường dẫn file rồi chạy Weather bình thường. Nó đăng ký lại có xác thực và tự heartbeat. Không đưa khóa lên URL hoặc log. Đăng ký thủ công mà không chạy Agent sẽ tự hết lease.

Web có thể sửa card, đăng ký lại và DELETE. DELETE xóa cả quyền sở hữu, khác `/unregister` giữ identity. Nếu Weather vẫn chạy mà operator DELETE record, lifecycle dừng khi gặp 404; không tự chiếm lại ID. Endpoint trong cấu hình Weather là nguồn chính, sẽ được gửi lại lúc startup/re-register.

## Trạng thái và tương thích

`status` đổi từ ACTIVE/EXPIRED sang ONLINE/SUSPECT/UNREACHABLE/UNREGISTERED. Đây là thay đổi contract có chủ ý; client cũ kiểm tra literal phải cập nhật. Giữ route và Agent Card cũ; `active_only=true` nay chỉ trả ONLINE. `active_only=false` phục vụ quan sát toàn bộ record, không phải discovery dùng cho Travel.

Ngưỡng mặc định: heartbeat=10s, suspect=20s, TTL=30s. Nếu không đặt SUSPECT, ngưỡng là trung bình interval và TTL. Luôn yêu cầu interval < suspect < TTL. Heartbeat khi SUSPECT còn lease đưa về ONLINE; khi lease hết hoặc đã unregister trả 409, cần đăng ký lại bằng khóa. Refresh, PATCH, GET không renew lease.

## Giới hạn

- Không active probe: giữ nguyên nguyên tắc không gọi endpoint tùy ý. UNREACHABLE nghĩa hết tín hiệu đáng tin theo lease; không khẳng định process chết. `/health` Weather dành cho operator/client kiểm tra trực tiếp, readiness hiện luôn true vì forecast không có dependency ngoài.
- Chưa có instance_id/fencing. Chỉ một process cho mỗi ID; hai process cùng khóa có thể ghi đè binding hoặc unregister nhau. Đây là extension cần migration/giao thức riêng.
- Chưa xử lý mất response cấp token đầu tiên, rotation hoặc phục hồi khóa mất. Không tự xóa khóa khi 401/404. Windows cần bảo vệ ACL thư mục credential.
- SQLite một nút, chưa benchmark, chưa phân trang/index capability; observer quét mỗi giây chỉ phù hợp MVP. Discovery tính trạng thái ngay khi query, không phụ thuộc observer.
- Lease phụ thuộc wall-clock. Không replication, DHT, broker, consensus hay kiểm tra LAN/liên nhóm.
- Travel có timeout/failover HTTP/JSON nhưng chưa kiểm tra schema forecast. Card chưa mô tả operation contract cho mọi capability.
- HTTP local tin cậy; triển khai mạng thật cần HTTPS và kiểm soát truy cập. Danh sách đọc công khai, không có tài khoản admin.
- Test UI là DOM giả, chưa phải browser E2E.

Chi tiết: [API](docs/api_contract.md), [kiến trúc](docs/architecture.md), [kiểm chứng](docs/verification.md).
