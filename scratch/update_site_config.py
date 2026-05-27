# scratch/update_site_config.py
import os
import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "linkedin.django_settings")
django.setup()

from linkedin.models import SiteConfig

def update_config():
    cfg = SiteConfig.load()
    cfg.llm_provider = "openai_compatible"
    cfg.llm_api_base = "https://9router.stelixx.com/v1"
    cfg.llm_api_key = "sk-ebef1445d0fd330c-ut4e5v-5f9e2fd3"
    cfg.ai_model = "gh/gpt-4.1"
    cfg.save()
    print("=== SiteConfig Updated in Database ===")
    print(f"Provider: {cfg.llm_provider}")
    print(f"API Base: {cfg.llm_api_base}")
    print(f"AI Model: {cfg.ai_model}")
    print("API Key has been encrypted and saved.")

if __name__ == "__main__":
    update_config()
