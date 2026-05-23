from django.db import migrations

def delete_freemium_campaigns(apps, schema_editor):
    Campaign = apps.get_model("linkedin", "Campaign")
    Task = apps.get_model("linkedin", "Task")

    freemium_campaigns = Campaign.objects.filter(is_freemium=True)
    freemium_campaign_ids = list(freemium_campaigns.values_list("id", flat=True))

    for campaign_id in freemium_campaign_ids:
        # Delete tasks associated with the freemium campaign
        for task in Task.objects.all():
            if task.payload.get("campaign_id") == campaign_id:
                task.delete()

    # Cascade delete campaigns (will delete Deals, ActionLogs, SearchKeywords)
    freemium_campaigns.delete()

class Migration(migrations.Migration):

    dependencies = [
        ("linkedin", "0007_siteconfig_llm_provider"),
    ]

    operations = [
        migrations.RunPython(
            delete_freemium_campaigns,
            reverse_code=migrations.RunPython.noop,
        ),
    ]
