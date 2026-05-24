# Kế hoạch Thiết kế & Triển khai Nâng cấp OpenOutreach (8 Phases)

Tài liệu này là nguồn sự thật (Source of Truth) cho quá trình nâng cấp, hoàn thiện và tích hợp hệ thống OpenOutreach phục vụ cho chiến dịch GTM của **Geolify.ai**. Kế hoạch được chia thành 8 Phase chạy độc lập và cuốn chiếu.

---

## Phân tích Hiện trạng Mã nguồn (Phase 4 & Phase 5)

### 1. Phase 4: Cơ chế Tự phục hồi lỗi (Self-healing & Error Recovery)
* **Hiện trạng mã nguồn:**
  * Dự án có module `linkedin/diagnostics.py` cung cấp context manager `failure_diagnostics`.
  * Khi Playwright hoặc tiến trình Chrome gặp lỗi, `failure_diagnostics` sẽ bắt lấy lỗi đó, chụp screenshot, lưu HTML của trang hiện tại và ghi lại log lỗi (stack trace) vào thư mục cục bộ `/tmp/openoutreach-diagnostics/`. Sau đó, nó **ném (raise) lỗi lên tiếp** khiến tác vụ đó bị đánh dấu là `FAILED`.
  * Trong `linkedin/daemon.py`, daemon sẽ tiếp tục xử lý vòng lặp và chạy `reconcile()` để tạo lại tác vụ bị thiếu ở chu kỳ rảnh (idle cycle) tiếp theo.
  * **Đánh giá:** Chưa có cơ chế **Self-healing** thực sự. Nếu lỗi xảy ra do Chrome bị lag đột ngột, việc trực tiếp mark FAILED ngay chu kỳ đầu tiên mà không thử lại (retry) sẽ làm gián đoạn tiến trình. Đặc biệt, hệ thống chưa hề có cơ chế gửi ảnh chụp lỗi hay cảnh báo Telegram về thiết bị của Admin.
* **Giải pháp nâng cấp:**
  * Bổ sung cơ chế **Auto-retry** ngay trong handler khi phát hiện lỗi trình duyệt (ví dụ: `TargetClosedError`, `TimeoutError`).
  * Thực hiện đóng trình duyệt cũ (`session.close()`), thiết lập lại `session.page = None`, khởi động lại trình duyệt mới và chạy lại tác vụ tối đa 2 lần.
  * Nếu sau 2 lần vẫn lỗi, chụp screenshot cuối cùng, gửi thông báo khẩn cấp qua Telegram đính kèm hình ảnh và báo lỗi chi tiết, lúc này mới thực sự chuyển Deal sang `FAILED`.

### 2. Phase 5: Phân loại Ý định (Intent Detection)
* **Hiện trạng mã nguồn:**
  * Trong tệp `linkedin/agents/follow_up.py`, đối tượng cấu trúc đầu ra của AI Agent (`FollowUpDecision`) chỉ định nghĩa 3 hành động: `send_message`, `mark_completed`, `wait`.
  * Giai đoạn kết thúc cuộc trò chuyện (`mark_completed`) chỉ ghi nhận các `outcome` tĩnh như `converted`, `not_interested`, `wrong_fit`, `no_budget`...
  * **Đánh giá:** Hệ thống **hoàn toàn chưa có** tính năng phân loại ý định (Intent Detection). AI Agent hiện tại sẽ tự động trả lời theo kịch bản bất chấp khách hàng phản hồi tích cực hay tiêu cực. Không có cơ chế nhận biết "Hot Lead" (muốn mua, muốn call gấp) để bàn giao quyền điều khiển lại cho con người (Admin).
* **Giải pháp nâng cấp:**
  * Thêm trường `intent` vào cấu trúc đầu ra `FollowUpDecision`:
    `intent: Literal["high", "low", "none"]`
  * Khi Lead trả lời và AI phân tích thấy `intent == "high"`, hệ thống sẽ:
    * Bắn thông báo Telegram khẩn cấp gắn tag `[🔥 HIGH INTENT]` kèm link chat trực tiếp.
    * Tự động chuyển Deal sang trạng thái tạm dừng tự động hóa (`PAUSED_FOR_MANUAL`) để tránh AI tiếp tục nhắn tin tự động làm mất tự nhiên khi Admin đã can thiệp thủ công.

---

## Chi tiết Lộ trình 8 Phase & Kế hoạch Xác minh (Verification Plan)

Dưới đây là kế hoạch chi tiết cho từng Phase, bao gồm các bước xác minh tự động (Automated Tests) và xác minh thủ công (Manual Verification) tương ứng cho từng tính năng.

### Phase 1: Hệ thống báo cáo & Cảnh báo qua Telegram (OO -> Telegram)
* **Mục tiêu:** Nhận thông tin hiệu suất phễu lead hàng ngày và cảnh báo lỗi thời gian thực.
* **Giải pháp thiết kế:**
  * Tạo file `linkedin/telegram.py` chứa các helper gửi tin nhắn HTML và ảnh chụp màn hình thông qua Telegram Bot API.
  * Tạo Django command `send_daily_report` thống kê các số liệu gửi lúc 20:00 VN hàng ngày:
    * Số connection đã gửi/được chấp nhận trong ngày.
    * Số tin nhắn follow-up gửi đi/nhận lại.
    * Chi phí API LLM ước tính trong ngày.
    * Danh sách các Lead mới nhắn tin chưa được trả lời.
* **Kế hoạch Xác minh (Verification Plan):**
  * **Kiểm thử tự động (Automated Tests):**
    * Viết unit test trong `tests/test_telegram.py` sử dụng `unittest.mock` để giả lập các request POST (như `httpx.post` hoặc `requests.post`) gửi tới API của Telegram (`api.telegram.org`). Xác nhận payload gửi đi chứa đúng `chat_id`, `text` (được định dạng HTML đúng chuẩn) và ảnh binary nếu là gửi screenshot.
    * Chạy thử Django command `call_command('send_daily_report')` trong môi trường test với cơ sở dữ liệu mock để xác nhận truy vấn SQL lấy chính xác số liệu thống kê trong ngày.
  * **Xác minh thủ công (Manual Verification):**
    * Điền thông tin `TELEGRAM_BOT_TOKEN` và `TELEGRAM_CHAT_ID` kiểm thử vào file `.env`.
    * Chạy thủ công lệnh `python manage.py send_daily_report` và kiểm tra giao diện tin nhắn nhận được trên ứng dụng Telegram (điện thoại/máy tính) để đảm bảo định dạng văn bản hiển thị rõ ràng, không bị lỗi font hay lỗi tag HTML.
    * Giả lập một lỗi kết nối internet hoặc lỗi LLM khi daemon đang chạy để xác nhận tin nhắn cảnh báo lỗi thời gian thực (đính kèm hình ảnh screenshot chụp từ Chrome) được gửi về Telegram của bạn trong vòng 60 giây.

### Phase 2: Tự động rút lại lời mời kết bạn cũ (Auto-withdraw)
* **Mục tiêu:** Giữ danh sách pending invites luôn sạch sẽ (< 200) để bảo vệ tài khoản LinkedIn khỏi thuật toán quét spam.
* **Giải pháp thiết kế:**
  * Tạo một tác vụ định kỳ `withdraw_old_invites` chạy 1 lần/tuần.
  * Tự động điều hướng đến trang `mynetwork/invitation-manager/sent/` và click nút "Withdraw" đối với các lời mời đã gửi quá 21-30 ngày.
* **Kế hoạch Xác minh (Verification Plan):**
  * **Kiểm thử tự động (Automated Tests):**
    * Tạo một trang HTML tĩnh giả lập cấu trúc DOM của trang quản lý lời mời đã gửi của LinkedIn (`mynetwork/invitation-manager/sent/`), chứa một số thẻ thông báo thời gian khác nhau (ví dụ: "1 week ago", "1 month ago").
    * Chạy test Playwright trên trang HTML mock này để xác nhận bot nhận diện đúng nút "Withdraw" của các lời mời cũ hơn 21 ngày và bỏ qua các lời mời mới gửi gần đây.
  * **Xác minh thủ công (Manual Verification):**
    * Khởi chạy tác vụ `withdraw_old_invites` trên VPS ở chế độ Headless=False (qua VNC) để quan sát trực tiếp bot tự động cuộn trang (scroll), tìm kiếm và click chính xác nút "Withdraw" của các lời mời cũ. Kiểm tra log của Playwright xem có phát sinh lỗi DOM hay không.

### Phase 3: Cổng phê duyệt tin nhắn AI (AI Message Approval Gate)
* **Mục tiêu:** Cho phép người dùng kiểm duyệt nội dung tin nhắn AI soạn thảo trước khi gửi đi.
* **Giải pháp thiết kế:**
  * Thêm trường `require_approval_for_outreach` (Boolean, mặc định=False) vào cấu hình Campaign.
  * Nếu ON: Khi AI soạn xong tin nhắn follow-up, Deal chuyển sang trạng thái `WAITING_APPROVAL` và gửi thông báo Telegram.
  * Admin có thể click nút duyệt trực tiếp trên Telegram (sử dụng Telegram Webhook/Inline Keyboard) hoặc bấm duyệt trên giao diện Django Admin.
* **Kế hoạch Xác minh (Verification Plan):**
  * **Kiểm thử tự động (Automated Tests):**
    * Viết test thiết lập một Campaign có `require_approval_for_outreach=True`. Chạy agent follow-up và kiểm tra xem sau khi LLM phản hồi tin nhắn, Deal có tự động chuyển trạng thái sang `WAITING_APPROVAL` thay vì gửi tin nhắn trực tiếp không.
    * Gửi request mock duyệt tin nhắn (giả lập HTTP POST từ Telegram callback query hoặc action trên Django Admin). Xác nhận trạng thái Deal chuyển về follow-up bình thường và tin nhắn được đẩy vào hàng đợi thực thi gửi đi.
  * **Xác minh thủ công (Manual Verification):**
    * Chạy thử nghiệm trên một lead test với Campaign đã bật cổng duyệt.
    * Đợi AI soạn tin nhắn và kiểm tra xem có nhận được thông báo Telegram kèm nút "Duyệt" (Approve) và "Sửa" (Edit) không.
    * Bấm nút "Duyệt" trên điện thoại và quan sát qua noVNC để đảm bảo trình duyệt tự động gửi tin nhắn đó sang LinkedIn của lead.

### Phase 4: Tự phục hồi lỗi trình duyệt (Self-healing & Error Recovery)
* **Mục tiêu:** Tự động sửa lỗi và relaunch trình duyệt khi Chrome crash trên VPS.
* **Giải pháp thiết kế:**
  * Tích hợp cơ chế bắt lỗi Playwright, tự động `session.close()` và khởi động lại phiên làm việc sạch để thử lại trước khi đánh dấu lỗi task.
* **Kế hoạch Xác minh (Verification Plan):**
  * **Kiểm thử tự động (Automated Tests):**
    * Mock lỗi của Playwright (ví dụ ném lỗi `TargetClosedError` hoặc `TimeoutError` khi gọi các hành động như click hoặc navigation).
    * Xác nhận logic handler bắt đúng loại lỗi này, tự động gọi `session.close()` và thiết lập lại các đối tượng trình duyệt về `None`, sau đó khởi động lại trình duyệt mới và chạy lại tác vụ.
    * Xác nhận nếu lỗi liên tục xảy ra quá 2 lần, hệ thống sẽ dừng thử lại, gửi tin nhắn cảnh báo lỗi qua Telegram và mark task là `FAILED`.
  * **Xác minh thủ công (Manual Verification):**
    * Khi daemon đang chạy một tác vụ kết nối hoặc nhắn tin, bạn hãy sử dụng lệnh `pkill chrome` hoặc tắt tiến trình Chrome ngầm trên VPS để giả lập crash.
    * Theo dõi log của daemon và VNC xem hệ thống có tự động phát hiện trình duyệt bị đóng đột ngột, tự động khởi chạy lại một phiên Chrome mới và tiếp tục hoàn thành tác vụ đang chạy dở hay không.

### Phase 5: Phân loại Ý định (Intent Detection)
* **Mục tiêu:** Phát hiện lead có mức độ quan tâm cao để chuyển giao cho con người chốt deal.
* **Giải pháp thiết kế:**
  * Nâng cấp AI Follow-up Agent để phân loại `high` / `low` / `none` intent.
  * Phát cảnh báo Telegram khẩn cấp `[🔥 HIGH INTENT]` khi có lead hot phản hồi.
* **Kế hoạch Xác minh (Verification Plan):**
  * **Kiểm thử tự động (Automated Tests):**
    * Chuẩn bị một bộ dữ liệu kiểm thử (fixtures) gồm các tin nhắn phản hồi thực tế của lead:
      * Nhóm tích cực (High Intent): "Tôi muốn xem thử demo", "Chi phí thế nào?", "Hãy gửi link đặt lịch".
      * Nhóm thông thường (Low Intent): "Cảm ơn đã kết nối", "Tôi sẽ xem sau".
      * Nhóm từ chối (No Intent): "Tôi không quan tâm", "Đừng làm phiền nữa".
    * Chạy test kiểm thử qua LLM và xác nhận giá trị `intent` trả về trong đối tượng `FollowUpDecision` khớp chính xác với phân loại mong muốn.
    * Xác nhận khi `intent == "high"`, Deal chuyển sang trạng thái tạm dừng tự động hóa (`PAUSED_FOR_MANUAL`).
  * **Xác minh thủ công (Manual Verification):**
    * Sử dụng một tài khoản LinkedIn phụ nhắn tin test cho tài khoản chạy bot với nội dung: "Chúng tôi đang gặp vấn đề về hiển thị trên ChatGPT, bạn có thể gọi điện tư vấn không?".
    * Chạy daemon đồng bộ tin nhắn và kiểm tra xem có nhận được thông báo khẩn cấp `[🔥 HIGH INTENT]` trên Telegram của bạn hay không.

### Phase 6: Giờ hoạt động thông minh (Smart Active Hours)
* **Mục tiêu:** Chạy bot theo giờ sinh hoạt thực tế của tài khoản VN nhưng tối ưu hóa thời gian gửi tin nhắn theo múi giờ của khách hàng.
* **Giải pháp thiết kế:**
  * Định nghĩa **Quy tắc an toàn cứng** (chạy tối đa 10h/ngày, nghỉ trưa ngẫu nhiên, chỉ mở bot 8h-22h VN).
  * Định nghĩa **Quy tắc tiếp cận mềm** (reschedule task gửi tin nhắn rơi vào giờ làm việc của Lead nếu khung giờ đó an toàn cho tài khoản VN).
* **Kế hoạch Xác minh (Verification Plan):**
  * **Kiểm thử tự động (Automated Tests):**
    * Viết unit test cho hàm `seconds_until_active` với múi giờ tài khoản gửi (Asia/Ho_Chi_Minh). Xác nhận nó trả về 0 khi nằm trong khung 8h-22h VN và trả về thời gian chờ phù hợp khi nằm ngoài khung giờ này hoặc rơi vào ngày nghỉ cuối tuần.
    * Viết test tính toán reschedule thời điểm chạy task của lead Mỹ (EST) và lead EU (CET). Xác nhận task gửi tin nhắn được lên lịch đúng vào giờ làm việc của lead nhưng nằm trong khung an toàn của tài khoản gửi.
  * **Xác minh thủ công (Manual Verification):**
    * Thiết lập giờ hệ thống trên VPS lệch múi giờ VN (ví dụ UTC).
    * Khởi chạy daemon và kiểm tra log xem nó có nhận diện chính xác múi giờ `Asia/Ho_Chi_Minh` được thiết lập trong file cấu hình để ngủ/thức đúng giờ làm việc Việt Nam hay không.

### Phase 7: Cá nhân hóa Link & Tracking click (Dub.co / Local Redirect)
* **Mục tiêu:** Đo lường chính xác lead nào đã click vào link audit/sản phẩm gửi kèm trong tin nhắn.
* **Giải pháp thiết kế:**
  * Xây dựng hệ thống **Local Redirect** chạy trực tiếp trên Django của OpenOutreach. Người dùng chỉ cần cấu hình một sub-domain (ví dụ `go.geolify.ai` hoặc sử dụng IP công khai) trỏ về VPS chạy OpenOutreach.
  * Hỗ trợ fallback tích hợp API **Dub.co** (cấu hình qua `.env`) nếu người dùng không muốn thiết lập tên miền riêng cho VPS.
* **Kế hoạch Xác minh (Verification Plan):**
  * **Kiểm thử tự động (Automated Tests):**
    * Viết test xác nhận khi gửi tin nhắn chứa link gốc, helper tự động thay thế bằng link local redirect (hoặc link rút gọn của Dub.co nếu bật cấu hình API) chứa mã code định danh duy nhất của Deal đó.
    * Giả lập gửi HTTP GET request click vào link redirect `/l/<short_code>/`. Xác nhận view xử lý của Django lưu chính xác một bản ghi vào model `LinkClick` (ghi nhận IP, User-Agent, thời gian click) và trả về HTTP 302 chuyển hướng chính xác đến trang audit đích của Geolify.
  * **Xác minh thủ công (Manual Verification):**
    * Cấu hình thử nghiệm sub-domain hoặc IP tĩnh của VPS.
    * Click thử vào link rút gọn gửi từ tin nhắn test. Kiểm tra xem thiết bị di động/máy tính có chuyển hướng mượt mà đến Geolify hay không và kiểm tra database Django xem có xuất hiện bản ghi lượt click mới hay không.

### Phase 8: Liên kết với Stelixx CDP
* **Mục tiêu:** Hoàn thiện tích hợp 2 chiều: Đẩy sự kiện về CDP qua Webhook và nhận lead tiềm năng qua upload CSV trên Django Admin.
* **Giải pháp thiết kế:**
  * Tạo module `linkedin/webhook.py` phát các sự kiện thay đổi trạng thái deal, tin nhắn gửi/nhận về CDP (ký số HMAC-SHA256).
  * Viết giao diện upload file CSV trên Django Admin của OpenOutreach để import trực tiếp lead vào chiến dịch.
* **Kế hoạch Xác minh (Verification Plan):**
  * **Kiểm thử tự động (Automated Tests):**
    * Viết test kiểm thử Webhook: Khi trạng thái Deal thay đổi, kiểm tra xem payload gửi đi có đúng cấu trúc JSON đã thống nhất và chữ ký `X-OpenOutreach-Signature` (HMAC-SHA256) được tính toán chính xác dựa trên `WEBHOOK_SECRET` hay không.
    * Viết test kiểm thử tính năng Import CSV: Giả lập gửi file CSV chứa các dòng dữ liệu LinkedIn URLs mẫu lên Django Admin View. Xác nhận view xử lý parse thành công dữ liệu, tạo đúng số lượng `Lead` và `Deal` tương ứng trong Campaign mà không bị trùng lặp.
  * **Xác minh thủ công (Manual Verification):**
    * Cấu hình một webhook URL tạm thời từ trang Webhook.site vào file `.env`.
    * Thay đổi trạng thái một Deal bất kỳ trên Django Admin và kiểm tra trên Webhook.site xem có nhận được payload sự kiện đúng định dạng JSON và chữ ký signature hợp lệ hay không.
    * Đăng nhập Django Admin, truy cập trang Campaign và upload thử một file CSV chứa 5 liên kết LinkedIn. Xác nhận 5 Lead mới được tạo thành công trong DB và được phân bổ chính xác vào Campaign đó.
