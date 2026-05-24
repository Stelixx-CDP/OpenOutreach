# linkedin/management/commands/send_daily_report.py
import datetime
from django.core.management.base import BaseCommand
from django.utils import timezone
from django.contrib.contenttypes.models import ContentType
from zoneinfo import ZoneInfo
import html

from linkedin.models import ActionLog, Campaign, Task, LinkedInProfile
from crm.models.deal import Deal, Outcome
from crm.models.lead import Lead
from chat.models import ChatMessage
from linkedin.enums import ProfileState
from linkedin.notifications import send_text


class Command(BaseCommand):
    help = "Send a daily report digest of LinkedIn automation stats and messages to Telegram"

    def handle(self, *args, **options):
        # Timezone Asia/Ho_Chi_Minh
        tz = ZoneInfo("Asia/Ho_Chi_Minh")
        local_now = timezone.localtime(timezone.now(), timezone=tz)
        today_start = local_now.replace(hour=0, minute=0, second=0, microsecond=0)
        today_end = local_now.replace(hour=23, minute=59, second=59, microsecond=999999)

        # Convert back to UTC for DB filtering (Django handles aware datetimes automatically)
        self.stdout.write(f"Generating daily report for VN day: {today_start.strftime('%Y-%m-%d')}...")

        campaigns = Campaign.objects.all()
        if not campaigns.exists():
            self.stdout.write("No campaigns found in database.")
            return

        report_lines = [
            f"📊 <b>DAILY DIGEST BÁO CÁO HÀNG NGÀY</b>",
            f"📅 <i>Ngày: {local_now.strftime('%d/%m/%Y')} (Giờ VN)</i>",
            "========================"
        ]

        total_connects_sent = 0
        total_connects_accepted = 0
        total_follow_ups_sent = 0
        total_replies_received = 0

        for campaign in campaigns:
            # 1. Connects sent in this campaign today
            connects_sent = ActionLog.objects.filter(
                campaign=campaign,
                action_type=ActionLog.ActionType.CONNECT,
                created_at__range=(today_start, today_end)
            ).count()
            total_connects_sent += connects_sent

            # 2. Connects accepted (Deals in this campaign moved to CONNECTED/COMPLETED today)
            connects_accepted = Deal.objects.filter(
                campaign=campaign,
                state__in=[ProfileState.CONNECTED, ProfileState.COMPLETED],
                update_date__range=(today_start, today_end)
            ).count()
            total_connects_accepted += connects_accepted

            # 3. Pending connects total currently
            pending_total = Deal.objects.filter(
                campaign=campaign,
                state=ProfileState.PENDING
            ).count()

            # 4. Follow-up messages sent today
            follow_ups_sent = ActionLog.objects.filter(
                campaign=campaign,
                action_type=ActionLog.ActionType.FOLLOW_UP,
                created_at__range=(today_start, today_end)
            ).count()
            total_follow_ups_sent += follow_ups_sent

            # 5. Leads that replied today
            lead_ct = ContentType.objects.get_for_model(Lead)
            leads_in_campaign = Deal.objects.filter(campaign=campaign).values_list("lead_id", flat=True)
            replies_received = ChatMessage.objects.filter(
                content_type=lead_ct,
                object_id__in=leads_in_campaign,
                is_outgoing=False,
                creation_date__range=(today_start, today_end)
            ).values("object_id").distinct().count()
            total_replies_received += replies_received

            # 6. New leads qualified today (Deals created today)
            leads_qualified = Deal.objects.filter(
                campaign=campaign,
                creation_date__range=(today_start, today_end)
            ).count()

            # 7. Disqualified leads today (wrong_fit outcome today)
            leads_disqualified = Deal.objects.filter(
                campaign=campaign,
                state=ProfileState.FAILED,
                outcome=Outcome.WRONG_FIT,
                update_date__range=(today_start, today_end)
            ).count()

            # Add campaign header & stats
            report_lines.append(f"\n📌 <b>Chiến dịch: {campaign.name}</b>")
            report_lines.append(f"• Connects: Sent {connects_sent} | Accepted {connects_accepted} | Pending total {pending_total}")
            report_lines.append(f"• Follow-ups sent: {follow_ups_sent} | Replies received: {replies_received}")
            report_lines.append(f"• Leads pipeline today: +{leads_qualified} qualified | -{leads_disqualified} disqualified")

            # 8. Hot Leads (replied today, conversation active)
            hot_lead_ids = ChatMessage.objects.filter(
                content_type=lead_ct,
                object_id__in=leads_in_campaign,
                is_outgoing=False,
                creation_date__range=(today_start, today_end)
            ).values_list("object_id", flat=True).distinct()

            hot_deals = Deal.objects.filter(
                campaign=campaign,
                lead_id__in=hot_lead_ids
            ).exclude(state__in=[ProfileState.COMPLETED, ProfileState.FAILED]).select_related("lead")

            if hot_deals.exists():
                report_lines.append("🔥 <b>Hot Leads phản hồi cần check:</b>")
                for deal in hot_deals:
                    lead_label = deal.lead.public_identifier or f"Lead#{deal.lead_id}"
                    report_lines.append(f"  - <code>{lead_label}</code> (<a href='{deal.lead.linkedin_url}'>LinkedIn</a>) - State: <code>{deal.state}</code>")

            # 9. Drill-down: Follow-up messages sent details
            sent_messages = ChatMessage.objects.filter(
                content_type=lead_ct,
                object_id__in=leads_in_campaign,
                is_outgoing=True,
                creation_date__range=(today_start, today_end)
            ).order_by("creation_date")

            if sent_messages.exists():
                report_lines.append("💬 <b>Tin nhắn Agent đã gửi hôm nay:</b>")
                msg_count = sent_messages.count()
                
                # Limit message body size if there are too many messages to prevent reaching Telegram text limit (4096 chars)
                max_display = 10
                display_messages = sent_messages[:max_display]
                
                for idx, msg in enumerate(display_messages):
                    lead_obj = Lead.objects.filter(pk=msg.object_id).first()
                    lead_label = lead_obj.public_identifier if lead_obj else f"Lead#{msg.object_id}"
                    msg_time = timezone.localtime(msg.creation_date, timezone=tz).strftime("%H:%M")
                    escaped_content = html.escape(msg.content)
                    
                    report_lines.append(f"  - <b>{lead_label}</b> ({msg_time}): <i>\"{escaped_content}\"</i>")

                if msg_count > max_display:
                    report_lines.append(f"  <i>...và {msg_count - max_display} tin nhắn khác. Xem chi tiết trên Django Admin.</i>")

        # Global health metrics (past 7 days)
        seven_days_ago = today_start - datetime.timedelta(days=7)
        sent_7d = ActionLog.objects.filter(
            action_type=ActionLog.ActionType.CONNECT,
            created_at__range=(seven_days_ago, today_end)
        ).count()
        # Count deals whose connect was sent in the 7d window AND are now accepted.
        # Use creation_date (= when the Deal/connect was created), not update_date
        # which can be bumped by follow-ups or other state changes.
        accepted_7d = Deal.objects.filter(
            state__in=[ProfileState.CONNECTED, ProfileState.COMPLETED],
            creation_date__range=(seven_days_ago, today_end)
        ).count()
        acceptance_rate_7d = (accepted_7d / sent_7d * 100) if sent_7d > 0 else 0.0

        llm_tasks_count = Task.objects.filter(
            status=Task.Status.COMPLETED,
            completed_at__range=(today_start, today_end)
        ).count()
        
        # Estimate OpenRouter cost (blended rate roughly $0.20 per 1M tokens, average task is ~5k tokens)
        est_cost = llm_tasks_count * 0.001  # roughly $0.001 per task

        report_lines.append("\n========================")
        report_lines.append("📊 <b>TỔNG HỢP TOÀN CỤC (GLOBAL HEALTH)</b>")
        report_lines.append(f"• Tổng connects gửi/nhận hôm nay: {total_connects_sent} / {total_connects_accepted}")
        report_lines.append(f"• Tỷ lệ chấp nhận kết bạn 7d: <b>{acceptance_rate_7d:.1f}%</b> (Gửi {sent_7d} | Đồng ý {accepted_7d})")
        report_lines.append(f"• LLM Tasks completed: {llm_tasks_count} (~${est_cost:.3f})")

        # Send to Telegram
        final_report = "\n".join(report_lines)
        success = send_text(final_report)
        if success:
            self.stdout.write(self.style.SUCCESS("Daily report sent successfully to Telegram!"))
        else:
            self.stdout.write(self.style.ERROR("Failed to send daily report to Telegram."))
