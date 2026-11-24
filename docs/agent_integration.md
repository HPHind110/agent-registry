# Tích hợp Agent nâng cao: Provider và Consumer

**Mặc định cho Provider:** dùng [Companion Onboarding](companion_onboarding.md). Tài liệu này dành cho nhóm muốn gọi REST trực tiếp, nhúng Python SDK hoặc viết Client.

[README](../README.md) · [API Contract](api_contract.md) · [Invocation Contract](invocation_contract.md)

## 1. Chọn vai trò

| Vai trò | Cần làm |
|---|---|
| **Provider** | Có business API; đăng ký Agent Card; duy trì lease (Companion, SDK hoặc REST); bảo vệ ownership credential. |
| **Consumer / Client** | Discovery theo capability/domain, chọn Provider rồi gọi business endpoint theo hợp đồng của Provider. Không cần đăng ký nếu chỉ tiêu thụ dịch vụ. |

Một Agent có thể vừa là Provider, vừa là Consumer.

Ví dụ Agent Card:

~~~json
{
  "agent_id": "text-team-a",
  "name": "Text Agent",
  "domain": "text",
  "description": "Text processing service",
  "capabilities": ["echo_text"],
  "endpoint": "http://192.168.1.20:8010/invoke",
  "version": "1.0"
}
~~~

`endpoint` phải là **URL nghiệp vụ đầy đủ**, có thể truy cập từ phía Client. Registry không tự nối thêm path và không kiểm tra reachability khi đăng ký.

## 2. Provider: dùng REST hoặc SDK thay Companion

**REST từ bất kỳ ngôn ngữ:** ID mới dùng `POST /v1/agents` với `X-Registry-Join-Token`. ID đã có dùng `POST /v1/agents` với `Authorization: Bearer <credential>` và full card. Gửi `POST /v1/agents/{id}/heartbeat` theo thời gian server cấp. Khi heartbeat trả `409`, authenticated re-register. Khi dừng bình thường, `POST /v1/agents/{id}/unregister`; **không dùng DELETE** nếu muốn giữ ownership.

**Python SDK (tùy chọn):** cài package trong môi trường Provider của chính bạn nếu muốn nhúng lifecycle sâu:

~~~bash
python -m pip install git+https://github.com/HPHind110/agent-registry.git
~~~

Sử dụng `agent_registry_client.registered_agent(card, registry_url, credential_file, http)` với `http` là một `httpx.AsyncClient` do ứng dụng sở hữu. Ví dụ khung tích hợp với FastAPI lifespan:

~~~python
from contextlib import asynccontextmanager
import httpx
from agent_registry_client import registered_agent

card = {
    "agent_id": "text-team-a",
    "name": "Text Agent",
    "domain": "text",
    "description": "Text processing service",
    "capabilities": ["echo_text"],
    "endpoint": "http://192.168.1.20:8010/invoke",
    "version": "1.0",
}

@asynccontextmanager
async def lifespan(app):
    async with httpx.AsyncClient(timeout=5) as client:
        async with registered_agent(
            card, "https://103-180-134-53.sslip.io",
            "/private/agent-text-team-a.credential", client
        ):
            yield
~~~

Gắn `lifespan` vào ứng dụng FastAPI của bạn. Mẫu trên giả định **ID đã được đăng ký và credential có sẵn**, không thích hợp để copy nguyên đường dẫn/endpoint vào production. SDK chạy task lifecycle bất đồng bộ; việc mở business API **không đồng nghĩa re-registration đã thành công**. Chỉ dùng SDK **hoặc** Companion cho cùng ID, không chạy cả hai.

## 3. Consumer: discovery và gọi Provider

Dùng HTTPS Registry:

~~~powershell
$registry = "https://103-180-134-53.sslip.io"
$agents = Invoke-RestMethod "$registry/v1/agents?capability=echo_text"
$agents | Select-Object agent_id, status, endpoint
~~~

`GET /v1/agents` mặc định chỉ trả `ONLINE`. Có thể thêm `domain=...`; dùng `active_only=false` để xem cả registration không hoạt động khi chẩn đoán.

**Sau discovery:** Client gọi trực tiếp `endpoint` với method, request body và business authentication do Provider cung cấp. **Không dùng Registry Join Token hoặc ownership credential để gọi business API.** Một capability có thể có nhiều Provider; Client nên có timeout, kiểm tra response và xử lý lỗi/không tìm thấy.

SDK có `discover(...)` và `invoke_with_rediscovery(...)` phục vụ **quy ước demo**. Helper có thể thử thêm một vòng discovery khi `safe_to_retry=True`; chỉ bật cho tác vụ **an toàn khi gọi lặp lại**. Xem [Invocation Contract](invocation_contract.md).

## 4. Demo trong repository

`demo/weather_agent.py` và `demo/news_agent.py` minh họa Provider; `demo/travel_client.py` và `demo/planner_client.py` minh họa Consumer. News có chế độ `NEWS_REGISTRY_MODE=manual` (chỉ phục vụ HTTP) hoặc `auto` (nhúng SDK). Chỉ dùng **một** lifecycle manager cho mỗi ID.

Các demo có logic nghiệp vụ mẫu, **không phải yêu cầu bắt buộc** dành cho Agent của các nhóm khác. Xem [Verification](verification.md) để chạy smoke tests.

## 5. Giới hạn tích hợp

- Registry lưu metadata, không chứa input/output schema, HTTP method hay business auth của Provider.
- `127.0.0.1` và IP LAN không tự khả dụng từ mạng khác; Registry không chuyển tiếp request hay giải quyết NAT/firewall.
- Không có instance fencing liên máy hoặc cơ chế tự phục hồi ownership credential bị mất.
- Nếu đổi metadata/endpoint, đồng bộ Agent Card và cấu hình lifecycle trước khi khởi động lại; Companion chủ động từ chối card lệch.

[Companion](companion_onboarding.md) · [API](api_contract.md) · [Kiến trúc](architecture.md)
