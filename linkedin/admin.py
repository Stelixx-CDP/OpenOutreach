# linkedin/admin.py
from django.contrib import admin

from chat.models import ChatMessage

from linkedin.models import ActionLog, Campaign, LinkedInProfile, SearchKeyword, SiteConfig, Task, PendingMessage, AgentFeedback


@admin.register(SiteConfig)
class SiteConfigAdmin(admin.ModelAdmin):
    list_display = ("__str__", "llm_provider", "ai_model", "llm_api_base")

    def has_add_permission(self, request):
        return not SiteConfig.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Campaign)
class CampaignAdmin(admin.ModelAdmin):
    list_display = ("name", "booking_link", "is_freemium", "action_fraction")
    filter_horizontal = ("users",)


@admin.register(LinkedInProfile)
class LinkedInProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "linkedin_username", "active", "legal_accepted")
    list_filter = ("active",)
    raw_id_fields = ("user", "self_lead")


@admin.register(SearchKeyword)
class SearchKeywordAdmin(admin.ModelAdmin):
    list_display = ("keyword", "campaign", "used", "used_at")
    list_filter = ("used", "campaign")
    raw_id_fields = ("campaign",)


@admin.register(ActionLog)
class ActionLogAdmin(admin.ModelAdmin):
    list_display = ("action_type", "linkedin_profile", "campaign", "created_at")
    list_filter = ("action_type", "campaign")
    raw_id_fields = ("linkedin_profile", "campaign")
    date_hierarchy = "created_at"
    readonly_fields = ("linkedin_profile", "campaign", "action_type", "created_at")


@admin.register(Task)
class TaskAdmin(admin.ModelAdmin):
    list_display = ("task_type", "status", "scheduled_at", "payload", "created_at")
    list_filter = ("task_type", "status")
    readonly_fields = (
        "task_type", "status", "scheduled_at", "payload",
        "created_at", "started_at", "completed_at",
    )
    date_hierarchy = "scheduled_at"


@admin.register(ChatMessage)
class ChatMessageAdmin(admin.ModelAdmin):
    list_display = ("content_type", "object_id", "owner", "creation_date")
    list_filter = ("content_type", "owner")
    raw_id_fields = ("owner", "answer_to", "topic")
    date_hierarchy = "creation_date"
    readonly_fields = ("content_type", "object_id", "content", "owner", "creation_date")


@admin.register(PendingMessage)
class PendingMessageAdmin(admin.ModelAdmin):
    list_display = ("deal", "message_text", "telegram_message_id", "created_at")
    raw_id_fields = ("deal",)
    readonly_fields = ("created_at",)
    actions = ["approve_messages", "skip_messages"]

    @admin.action(description="Approve selected messages")
    def approve_messages(self, request, queryset):
        import os
        import html
        import requests
        from linkedin.models import AgentFeedback, Task
        from django.utils import timezone
        
        count = 0
        for pending in queryset:
            # Save Feedback
            AgentFeedback.objects.create(
                campaign=pending.deal.campaign,
                deal=pending.deal,
                original_message=pending.message_text,
                feedback_type=AgentFeedback.FeedbackType.APPROVED,
            )
            # Create Task
            Task.objects.create(
                task_type=Task.TaskType.SEND_APPROVED_MESSAGE,
                scheduled_at=timezone.now(),
                payload={
                    "campaign_id": pending.deal.campaign_id,
                    "pending_message_id": pending.id,
                }
            )
            count += 1
            
            # Edit Telegram original message if configured
            token = os.environ.get("TELEGRAM_BOT_TOKEN")
            chat_id = os.environ.get("TELEGRAM_CHAT_ID")
            if token and chat_id and pending.telegram_message_id:
                new_text = (
                    f"✅ <b>Đã duyệt qua Django Admin và đang xếp lịch gửi:</b>\n"
                    f"• Lead: <code>{pending.deal.lead.public_identifier}</code>\n"
                    f"• Nội dung: <i>\"{html.escape(pending.message_text)}\"</i>"
                )
                url = f"https://api.telegram.org/bot{token}/editMessageText"
                try:
                    requests.post(url, json={
                        "chat_id": chat_id,
                        "message_id": pending.telegram_message_id,
                        "text": new_text,
                        "parse_mode": "HTML",
                    }, timeout=5)
                except Exception:
                    pass

        self.message_user(request, f"Successfully approved {count} messages.")

    @admin.action(description="Skip selected messages")
    def skip_messages(self, request, queryset):
        import os
        import html
        import requests
        from linkedin.models import AgentFeedback
        from linkedin.enums import ProfileState
        
        count = 0
        for pending in queryset:
            deal = pending.deal
            lead_id = deal.lead.public_identifier
            
            # Save Feedback
            AgentFeedback.objects.create(
                campaign=deal.campaign,
                deal=deal,
                original_message=pending.message_text,
                feedback_type=AgentFeedback.FeedbackType.REJECTED,
            )
            
            # Move deal back to CONNECTED using set_profile_state
            from linkedin.db.deals import set_profile_state
            class SimpleSession:
                def __init__(self, campaign):
                    self.campaign = campaign
            
            set_profile_state(SimpleSession(deal.campaign), lead_id, ProfileState.CONNECTED.value, reason="skipped_via_django_admin", enqueue_task=False)
            from linkedin.tasks.scheduler import enqueue_follow_up
            enqueue_follow_up(deal.campaign.id, lead_id, delay_seconds=24 * 3600)
            
            # Edit Telegram original message
            token = os.environ.get("TELEGRAM_BOT_TOKEN")
            chat_id = os.environ.get("TELEGRAM_CHAT_ID")
            if token and chat_id and pending.telegram_message_id:
                new_text = (
                    f"🚫 <b>Đã bỏ qua qua Django Admin:</b>\n"
                    f"• Lead: <code>{lead_id}</code>\n"
                    f"• Nội dung bị bỏ qua: <i>\"{html.escape(pending.message_text)}\"</i>"
                )
                url = f"https://api.telegram.org/bot{token}/editMessageText"
                try:
                    requests.post(url, json={
                        "chat_id": chat_id,
                        "message_id": pending.telegram_message_id,
                        "text": new_text,
                        "parse_mode": "HTML",
                    }, timeout=5)
                except Exception:
                    pass
            
            # Delete pending
            pending.delete()
            count += 1
            
        self.message_user(request, f"Successfully skipped {count} messages.")


@admin.register(AgentFeedback)
class AgentFeedbackAdmin(admin.ModelAdmin):
    list_display = ("campaign", "deal", "feedback_type", "created_at")
    list_filter = ("feedback_type", "campaign")
    raw_id_fields = ("campaign", "deal")
    readonly_fields = ("created_at",)

