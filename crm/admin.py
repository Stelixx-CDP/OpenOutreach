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
