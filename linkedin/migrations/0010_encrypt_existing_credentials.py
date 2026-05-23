from django.db import migrations

def encrypt_credentials(apps, schema_editor):
    LinkedInProfile = apps.get_model("linkedin", "LinkedInProfile")
    SiteConfig = apps.get_model("linkedin", "SiteConfig")

    from linkedin.crypto import encrypt_value, is_encrypted

    for lp in LinkedInProfile.objects.all():
        if lp.linkedin_password and not is_encrypted(lp.linkedin_password):
            lp.linkedin_password = encrypt_value(lp.linkedin_password)
            lp.save(update_fields=["linkedin_password"])

    for sc in SiteConfig.objects.all():
        if sc.llm_api_key and not is_encrypted(sc.llm_api_key):
            sc.llm_api_key = encrypt_value(sc.llm_api_key)
            sc.save(update_fields=["llm_api_key"])

class Migration(migrations.Migration):

    dependencies = [
        ('linkedin', '0009_alter_linkedinprofile_linkedin_password_and_more'),
    ]

    operations = [
        migrations.RunPython(
            encrypt_credentials,
            reverse_code=migrations.RunPython.noop,
        ),
    ]
