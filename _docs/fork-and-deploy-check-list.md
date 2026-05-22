# Checklist Cập nhật Code & Hướng dẫn Deploy Docker Compose lên VPS (Tối giản: 1 Tài khoản & SQLite)

Tài liệu này hướng dẫn chi tiết từng bước cho local agent thực hiện cập nhật mã nguồn dự án **OpenOutreach** (bản fork của Geolify.ai) để chạy **một tài khoản duy nhất**, sử dụng cơ sở dữ liệu SQLite mặc định và thiết lập Proxy đơn giản qua biến môi trường để deploy lên VPS thông qua Docker Compose.

---

## I. Các Phần Cần Cập Nhật Trong Source Code

### 1. Kích hoạt hiển thị CRM trong Django Admin (Đã thực hiện ở Local)
Đảm bảo file [crm/admin.py](file:///Users/gn/Documents/Gnoc/Github/OpenOutreach/crm/admin.py) đã được tạo để hiển thị các mục **Leads** và **Deals** trong CRM nhằm giúp Founder theo dõi chiến dịch:
```python
from django.contrib import admin
from crm.models.lead import Lead
from crm.models.deal import Deal

@admin.register(Lead)
class LeadAdmin(admin.ModelAdmin):
    list_display = ("__str__", "public_identifier", "urn", "disqualified", "creation_date")
    list_filter = ("disqualified", "creation_date")
    search_fields = ("linkedin_url", "public_identifier", "urn")
    date_hierarchy = "creation_date"
    readonly_fields = ("creation_date", "update_date")

@admin.register(Deal)
class DealAdmin(admin.ModelAdmin):
    list_display = ("__str__", "lead", "campaign", "state", "outcome", "connect_attempts", "creation_date")
    list_filter = ("state", "outcome", "campaign", "creation_date")
    search_fields = ("lead__linkedin_url", "lead__public_identifier", "reason")
    raw_id_fields = ("lead", "campaign")
    date_hierarchy = "creation_date"
    readonly_fields = ("creation_date", "update_date")
```

### 2. Tùy biến khởi chạy Playwright sử dụng Proxy qua Biến môi trường
Thay vì lưu proxy phức tạp trong Database, ta chỉ cần đọc Proxy duy nhất từ file cấu hình môi trường `.env` của hệ thống để Playwright khởi chạy trình duyệt đi qua Proxy đó.

*   **File cần sửa:** [linkedin/browser/login.py](file:///Users/gn/Documents/Gnoc/Github/OpenOutreach/linkedin/browser/login.py)
*   **Đoạn code cần sửa:**
    *   *Sửa hàm `launch_browser`:*
        ```python
        import os

        def launch_browser(storage_state=None):
            logger.debug("Launching Playwright")
            playwright = sync_playwright().start()
            
            launch_args = {"headless": True, "slow_mo": BROWSER_SLOW_MO} # Chuyển headless=True khi chạy trên VPS
            
            # Đọc proxy duy nhất từ cấu hình môi trường
            proxy_server = os.environ.get("PROXY_SERVER") # Ví dụ: http://ip:port
            proxy_user = os.environ.get("PROXY_USERNAME")
            proxy_pass = os.environ.get("PROXY_PASSWORD")
            
            proxy_config = None
            if proxy_server:
                proxy_config = {"server": proxy_server}
                if proxy_user and proxy_pass:
                    proxy_config["username"] = proxy_user
                    proxy_config["password"] = proxy_pass
                    
            if proxy_config:
                launch_args["proxy"] = {"server": proxy_config["server"]}
                
            browser = playwright.chromium.launch(**launch_args)
            
            context_args = {"storage_state": storage_state}
            if proxy_config and "username" in proxy_config:
                context_args["proxy"] = proxy_config
                
            context = browser.new_context(**context_args)
            context.set_default_timeout(BROWSER_DEFAULT_TIMEOUT_MS)
            context.set_default_navigation_timeout(BROWSER_DEFAULT_TIMEOUT_MS)
            Stealth().apply_stealth_sync(context)
            page = context.new_page()
            return page, context, browser, playwright
        ```
    *   *Sửa hàm `start_browser_session`:*
        Vì hàm `launch_browser` bây giờ tự động đọc proxy từ biến môi trường, ta khôi phục hàm `start_browser_session` về dạng cơ bản, chỉ cần gọi:
        ```python
        session.page, session.context, session.browser, session.playwright = launch_browser(storage_state=storage_state)
        ```

---

## II. Đóng Gói Và Cấu Hình Docker Compose Cho VPS

Vì chỉ chạy một tài khoản duy nhất, chúng ta giữ nguyên cơ sở dữ liệu SQLite lưu trong thư mục `data/` dùng chung qua volume Docker. Hệ thống cực kỳ nhẹ và đơn giản.

### 1. Cấu hình file `docker-compose.yml`
```yaml
version: '3.8'

services:
  web:
    build:
      context: .
      dockerfile: ./compose/linkedin/Dockerfile
    # Chạy lệnh khởi tạo DB SQLite và bật Django Server
    command: >
      sh -c "python manage.py migrate --noinput &&
             python manage.py setup_crm &&
             python manage.py runserver 0.0.0.0:8000"
    volumes:
      - .:/app
      - django_data:/app/data
    ports:
      - "8000:8000"
    env_file:
      - .env
    restart: always

  daemon:
    build:
      context: .
      dockerfile: ./compose/linkedin/Dockerfile
    # Chạy vòng lặp worker ngầm
    command: python manage.py rundaemon
    volumes:
      - .:/app
      - django_data:/app/data
    env_file:
      - .env
    environment:
      - DISPLAY=:99 # Chạy headless ảo thông qua Xvfb
    depends_on:
      - web
    restart: always

volumes:
  django_data:
```

### 2. File cấu hình môi trường `.env`
Tạo file `.env` nằm cùng thư mục với `docker-compose.yml` trên VPS:
```env
# Cấu hình API Key của Mô hình Ngôn ngữ lớn
LLM_PROVIDER=openai
LLM_API_KEY=sk-proj-...
AI_MODEL=gpt-4o

# Cấu hình Proxy cố định cho tài khoản LinkedIn của bạn
PROXY_SERVER=http://your_proxy_ip:port
PROXY_USERNAME=your_proxy_user
PROXY_PASSWORD=your_proxy_pass

# Trực quan hóa
BROWSER_SLOW_MO=50
```

---

## III. Các Bước Triển Khai Trên VPS (VPS Deployment Steps)

1.  **Cài đặt Docker trên VPS Linux (Ubuntu):**
    ```bash
    sudo apt update
    sudo apt install git docker.io docker-compose -y
    ```
2.  **Clone code và di chuyển vào thư mục:**
    ```bash
    git clone <url_fork_cua_geolify_ai> openoutreach
    cd openoutreach
    ```
3.  **Tạo file `.env`** và nhập thông tin LLM Key cũng như Proxy (như mẫu ở Phần II).
4.  **Khởi chạy hệ thống bằng Docker Compose:**
    ```bash
    docker-compose up --build -d
    ```
5.  **Tạo tài khoản Superadmin cho CRM Admin:**
    ```bash
    docker-compose exec web python manage.py createsuperadmin
    ```
6.  **Truy cập CRM:** Mở cổng `http://<IP_VPS>:8000/admin` để cấu hình Chiến dịch (Campaign) và Tài khoản LinkedIn duy nhất của bạn.

---

## IV. Những Điểm Lưu Ý Quan Trọng Khi Vận Hành

> [!CAUTION]
> ### 1. Vấn đề "Bypass OTP / Checkpoint" khi đăng nhập lần đầu trên VPS:
> * Khi đăng nhập lần đầu từ một IP mới (IP của VPS), LinkedIn hầu như chắc chắn sẽ yêu cầu xác thực OTP qua Email hoặc mã pin.
> * **Giải pháp:** Trong file `docker-compose.yml`, tạm thời chạy container `daemon` hoặc `web` ở chế độ **non-headless (headless=False) kết hợp VNC** (OpenOutreach đã cài sẵn VNC trên cổng `5900` trong docker). Sử dụng phần mềm kết nối VNC (như TigerVNC, RealVNC) kết nối tới IP VPS qua cổng 5900 để tự tay nhập mã xác thực OTP lần đầu tiên. Sau khi đăng nhập thành công, cookie sẽ được lưu vào DB (`cookie_data`), các lần sau container sẽ tự động chạy ngầm mà không hỏi lại.
>
> ### 2. Chọn Proxy cố định:
> * Phải mua **Residential Proxy tĩnh (IPv4)** cố định. Không dùng proxy xoay vòng (rotating proxy) vì đổi IP liên tục sẽ khiến LinkedIn khóa tài khoản ngay lập tức vì nghi ngờ tài khoản bị xâm nhập.
