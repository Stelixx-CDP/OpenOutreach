# scratch/test_llm.py
import os
import sys
import openai
import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "linkedin.django_settings")
django.setup()

from linkedin.models import SiteConfig

def test_connection():
    cfg = SiteConfig.load()
    print("=== OpenOutreach LLM Connection Test ===")
    print(f"Provider in DB: {cfg.llm_provider}")
    print(f"API Base: {cfg.llm_api_base}")
    print(f"AI Model: {cfg.ai_model}")
    print(f"Has API Key in DB: {bool(cfg.llm_api_key)}")
    
    if not cfg.llm_api_key:
        print("ERROR: No API Key found in SiteConfig DB!")
        return

    # Initialize OpenAI Client
    client = openai.OpenAI(
        base_url=cfg.llm_api_base,
        api_key=cfg.llm_api_key,
        default_headers={
            "HTTP-Referer": "https://github.com/eracle/OpenOutreach",
            "X-Title": "OpenOutreach",
        },
        timeout=15.0
    )

    print("\n--- Test 1: Direct Chat Completion ---")
    print("Sending Test 1 request...")
    try:
        response = client.chat.completions.create(
            model=cfg.ai_model,
            messages=[{"role": "user", "content": "Respond with the word 'SUCCESS' only."}],
            max_tokens=10
        )
        result = response.choices[0].message.content.strip()
        print(f"Result: {result}")
        print("👉 Test 1: PASSED")
    except Exception as e:
        print(f"❌ Test 1: FAILED -> {e}")

    print("\n--- Test 2: Structured Output (JSON format) ---")
    print("Sending Test 2 request...")
    try:
        response = client.chat.completions.create(
            model=cfg.ai_model,
            messages=[{"role": "user", "content": "Respond with JSON containing 'status': 'success'"}],
            response_format={"type": "json_object"},
            max_tokens=20
        )
        result = response.choices[0].message.content.strip()
        print(f"Result: {result}")
        print("👉 Test 2: PASSED")
    except Exception as e:
        print(f"❌ Test 2: FAILED -> {e}")
        print("\nNote: Some free model providers on OpenRouter do not support response_format={'type': 'json_object'}.")
        print("If Test 1 passed but Test 2 failed, you should switch to a paid model (like meta-llama/llama-3.3-70b-instruct) which has full support.")

if __name__ == "__main__":
    test_connection()
