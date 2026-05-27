import os
import django
import sys
import time
import asyncio
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

# Load .env manually
env_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), '.env')
if os.path.exists(env_path):
    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                key, val = line.split('=', 1)
                os.environ[key.strip()] = val.strip().strip('"').strip("'")

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'linkedin.django_settings')
django.setup()

from django.db import transaction
from django.utils import timezone
from django.contrib.contenttypes.models import ContentType
from crm.models import Deal, Lead
from chat.models import ChatMessage
from linkedin.models import Campaign, LinkedInProfile
from linkedin.agents.follow_up import run_follow_up_agent, FollowUpDecision
from linkedin.agents.output_validator import validate_message

# List of 7 models to test
TEST_MODELS = [
    "gh/gpt-5-mini",
    "gh/gpt-4.1",
    "gh/gpt-4o",
    "gh/claude-haiku-4.5",
    "gh/gemini-3-flash-preview",
    "cf/@cf/meta/llama-3.3-70b-instruct-fp8-fast",
    "cf/@cf/deepseek-ai/deepseek-r1-distill-qwen-32b",
]

# Scenario templates to apply to real leads
SCENARIO_TEMPLATES = [
    # --- LEAD_REPLIED Scenarios ---
    {
        "desc": "Replied - Short Decline",
        "messages": [
            {"is_outgoing": True, "content": "Hey, noticed you lead SEO at your agency. How are you measuring brand visibility in ChatGPT for SaaS?", "age_hours": 24},
            {"is_outgoing": False, "content": "No budget for new tools right now, sorry.", "age_hours": 2}
        ]
    },
    {
        "desc": "Replied - Ask for email",
        "messages": [
            {"is_outgoing": True, "content": "Hey, how do you track brand citations across Gemini and Perplexity for clients?", "age_hours": 48},
            {"is_outgoing": False, "content": "Can you email me some info at contact@agency.com?", "age_hours": 3}
        ]
    },
    {
        "desc": "Replied - Ask for pricing",
        "messages": [
            {"is_outgoing": True, "content": "Hey, how do you handle clients asking about search optimization in ChatGPT?", "age_hours": 24},
            {"is_outgoing": False, "content": "What's the pricing on this?", "age_hours": 2}
        ]
    },
    {
        "desc": "Replied - Too busy",
        "messages": [
            {"is_outgoing": True, "content": "Hey, how do your clients measure AI search impact?", "age_hours": 36},
            {"is_outgoing": False, "content": "Super busy this week, ping me next month.", "age_hours": 4}
        ]
    },
    {
        "desc": "Replied - Freelancer skeptical",
        "messages": [
            {"is_outgoing": True, "content": "Hey, how do you show clients their visibility in AI search engines?", "age_hours": 48},
            {"is_outgoing": False, "content": "Is GEO even a real thing? Sounds like a buzzword.", "age_hours": 5}
        ]
    },
    {
        "desc": "Replied - Already has solution",
        "messages": [
            {"is_outgoing": True, "content": "Hey, how do you track brand citations across Perplexity and Google AI overviews?", "age_hours": 24},
            {"is_outgoing": False, "content": "We already build our own internal scrapers to check Perplexity citations.", "age_hours": 2}
        ]
    },
    {
        "desc": "Replied - Referral to team",
        "messages": [
            {"is_outgoing": True, "content": "Hey, how does your agency report ChatGPT visibility to clients?", "age_hours": 48},
            {"is_outgoing": False, "content": "I don't handle SEO here. Reach out to Dwight, our SEO director, at dwight@office.com.", "age_hours": 6}
        ]
    },
    {
        "desc": "Replied - Wrong fit",
        "messages": [
            {"is_outgoing": True, "content": "Hey, how does your agency measure AI search visibility for clients?", "age_hours": 24},
            {"is_outgoing": False, "content": "We sell paper offline. No SEO/GEO needed.", "age_hours": 1}
        ]
    },
    {
        "desc": "Replied - Warm interest",
        "messages": [
            {"is_outgoing": True, "content": "Hey, how are you measuring AI search engine visibility for clients?", "age_hours": 24},
            {"is_outgoing": False, "content": "This is exactly what we've been struggling with. Do you have a deck or a quick demo?", "age_hours": 2}
        ]
    },
    {
        "desc": "Replied - Collaborative / Metaphor",
        "messages": [
            {"is_outgoing": True, "content": "Hey, how do you currently measure client visibility in Perplexity and Claude?", "age_hours": 36},
            {"is_outgoing": False, "content": "Honestly, the client thinks SEO is dead and ChatGPT is just magic. It's a tough education battle.", "age_hours": 4}
        ]
    },
    # --- NO_REPLY_BUMP Scenarios ---
    {
        "desc": "No Reply - Bump 1",
        "messages": [
            {"is_outgoing": True, "content": "Hey, how are you currently measuring brand visibility in ChatGPT for SaaS?", "age_hours": 25}
        ]
    },
    {
        "desc": "No Reply - Bump 2",
        "messages": [
            {"is_outgoing": True, "content": "Hey, how are you measuring brand visibility in ChatGPT?", "age_hours": 50},
            {"is_outgoing": True, "content": "Bumping this - totally fine if it's not on your radar.", "age_hours": 24}
        ]
    },
    {
        "desc": "No Reply - Bump 3",
        "messages": [
            {"is_outgoing": True, "content": "Hey, how are you measuring brand visibility in ChatGPT?", "age_hours": 75},
            {"is_outgoing": True, "content": "Bumping this - totally fine if not on your radar.", "age_hours": 50},
            {"is_outgoing": True, "content": "No worries if not a fit, happy to drop it.", "age_hours": 24}
        ]
    },
    {
        "desc": "No Reply - Already pitch, Bump 1",
        "messages": [
            {"is_outgoing": True, "content": "Hey, how do you track startups visibility in AI search engines?", "age_hours": 72},
            {"is_outgoing": False, "content": "Mostly manually. Do you have start metrics?", "age_hours": 48},
            {"is_outgoing": True, "content": "Yes, we run custom audits showing citation coverage. Here is the audit page: https://geolify.ai/geo-ai-visibility-audit", "age_hours": 24}
        ]
    },
    {
        "desc": "No Reply - Already pitch, Bump 2",
        "messages": [
            {"is_outgoing": True, "content": "Hey, how do you track startups visibility?", "age_hours": 96},
            {"is_outgoing": False, "content": "Do you have start metrics?", "age_hours": 72},
            {"is_outgoing": True, "content": "Yes, we run custom audits. Here is the link: https://geolify.ai/geo-ai-visibility-audit", "age_hours": 48},
            {"is_outgoing": True, "content": "Just wanted to bump this in case you had a chance to look.", "age_hours": 24}
        ]
    },
    {
        "desc": "No Reply - Bump 1 (Alt)",
        "messages": [
            {"is_outgoing": True, "content": "Hey, how are you measuring brand citations in ChatGPT?", "age_hours": 24}
        ]
    },
    {
        "desc": "No Reply - Bump 2 (Alt)",
        "messages": [
            {"is_outgoing": True, "content": "Hey, how are you measuring brand citations?", "age_hours": 48},
            {"is_outgoing": True, "content": "Bumping this - totally fine if it's not a fit.", "age_hours": 24}
        ]
    },
    {
        "desc": "No Reply - Bump 1 (Campaign B)",
        "messages": [
            {"is_outgoing": True, "content": "Hey, noticed you run indie SaaS. How are you tracking if ChatGPT or Perplexity cite your apps?", "age_hours": 26}
        ]
    },
    {
        "desc": "No Reply - Bump 2 (Campaign B)",
        "messages": [
            {"is_outgoing": True, "content": "Hey, noticed you run indie SaaS. How are you tracking if ChatGPT cites your apps?", "age_hours": 50},
            {"is_outgoing": True, "content": "Bumping this - in case it got buried in your feed.", "age_hours": 24}
        ]
    },
    {
        "desc": "No Reply - Bump 3 (Campaign B)",
        "messages": [
            {"is_outgoing": True, "content": "Hey, noticed you run indie SaaS. How are you tracking if ChatGPT cites your apps?", "age_hours": 75},
            {"is_outgoing": True, "content": "Bumping this - in case it got buried.", "age_hours": 48},
            {"is_outgoing": True, "content": "No worries if not a fit, happy to drop it.", "age_hours": 24}
        ]
    },
    # --- INITIAL_OUTREACH Scenarios ---
    {
        "desc": "Initial Outreach - 1",
        "messages": []
    },
    {
        "desc": "Initial Outreach - 2",
        "messages": []
    },
    {
        "desc": "Initial Outreach - 3",
        "messages": []
    },
    {
        "desc": "Initial Outreach - 4",
        "messages": []
    },
    {
        "desc": "Initial Outreach - 5",
        "messages": []
    },
    {
        "desc": "Initial Outreach - 6",
        "messages": []
    },
    {
        "desc": "Initial Outreach - 7",
        "messages": []
    },
    {
        "desc": "Initial Outreach - 8",
        "messages": []
    },
    {
        "desc": "Initial Outreach - 9",
        "messages": []
    }
]


# ── Dynamic Model Helper ──────────────────────────────────────────────
def get_custom_model(model_name: str):
    from openai import AsyncOpenAI
    from pydantic_ai.models.openai import OpenAIModel
    from pydantic_ai.providers.openai import OpenAIProvider
    
    api_base = os.environ.get("LLM_API_BASE", "https://9router.stelixx.com/v1")
    api_key = os.environ.get("LLM_API_KEY")
    
    client = AsyncOpenAI(
        base_url=api_base,
        api_key=api_key,
        max_retries=3,
    )
    return OpenAIModel(model_name, provider=OpenAIProvider(openai_client=client))

# ── LLM Judge Evaluation ──────────────────────────────────────────────
def evaluate_message_with_judge(
    lead_name: str | None,
    scenario_desc: str,
    conversation_history: str,
    generated_message: str,
) -> tuple[float, str]:
    """Evaluate generated message using GPT-4o as an LLM Judge."""
    from pydantic_ai import Agent
    from pydantic import BaseModel, Field
    from linkedin.llm import run_agent_sync
    
    class JudgeEvaluation(BaseModel):
        score: float = Field(description="Score between 1.0 and 10.0")
        analysis: str = Field(description="1-2 sentences explaining why the score was given.")

    judge_model = get_custom_model("gh/gpt-4o")
    agent = Agent(judge_model, output_type=JudgeEvaluation)
    
    prompt = f"""
    You are an expert LinkedIn sales coach evaluating an AI agent's outreach message.
    
    Context:
    - Lead Name: {lead_name or 'Unknown (neutral greeting)'}
    - Scenario Description: {scenario_desc}
    - Conversation History:
    {conversation_history}
    
    Generated Message under evaluation:
    "{generated_message}"
    
    Evaluate the message strictly based on:
    1. Human-like naturalness: Does it sound like a real person on LinkedIn? (LinkedIn messages should be short, casual, and warm. 1-3 sentences, no em-dashes, no formal email closures).
    2. Context alignment/Empathy: Does it address the lead's point directly, showing active listening, or does it ignore their input?
    3. Conversational flow (Mom Test): Does it keep the conversation open naturally without being pushy or interrogation-like?
    4. Compliance: If the lead has not replied, the message must be a short check-in (<= 20 words) with no greeting and no heavy question.
    
    Give a score from 1.0 (terrible, clear bot) to 10.0 (perfect, indistinguishable from a skilled human).
    Provide a concise 1-2 sentence analysis.
    """
    try:
        result = run_agent_sync(agent.run(prompt))
        return result.output.score, result.output.analysis
    except Exception as e:
        return 0.0, f"Judge failed: {str(e)}"

# ── Mocking database and running the Agent ────────────────────────────
class MockLinkedInProfile:
    def __init__(self):
        self.linkedin_username = "cong.nguyen@example.com"

class MockSession:
    def __init__(self):
        self.self_profile = {"first_name": "Cong", "last_name": "Nguyen"}
        self.linkedin_profile = MockLinkedInProfile()
        self.django_user = None

def run_scenario(deal_id: int, scenario_desc: str, messages_to_create: list, model_name: str, use_actual_messages: bool = False) -> dict:
    """Run follow up agent on an actual Deal, optionally creating temporary messages inside a rollback transaction."""
    session = MockSession()
    start_time = time.time()
    
    with transaction.atomic():
        # Load the actual Deal
        deal = Deal.objects.select_related('lead', 'campaign').get(pk=deal_id)
        lead = deal.lead
        
        # If we are not using the lead's actual messages, delete existing and insert mock ones
        if not use_actual_messages:
            # Delete existing messages for this lead inside the transaction
            ct = ContentType.objects.get_for_model(lead.__class__)
            ChatMessage.objects.filter(content_type=ct, object_id=lead.id).delete()
            
            # Create scenario messages
            import uuid
            now = timezone.now()
            for msg in messages_to_create:
                ChatMessage.objects.create(
                    content_type=ct,
                    object_id=lead.id,
                    content=msg["content"],
                    is_outgoing=msg["is_outgoing"],
                    creation_date=now - timezone.timedelta(hours=msg["age_hours"]),
                    linkedin_urn=f"mock-urn-{uuid.uuid4()}"
                )
        
        # Load and compile conversation history for LLM Judge
        recent_messages = []
        ct = ContentType.objects.get_for_model(lead.__class__)
        db_messages = list(ChatMessage.objects.filter(content_type=ct, object_id=lead.id).order_by('creation_date'))
        
        history_lines = []
        for msg in db_messages:
            speaker = "Me" if msg.is_outgoing else "Lead"
            history_lines.append(f"{speaker}: {msg.content}")
        history_text = "\n".join(history_lines) if history_lines else "(No previous history)"
        
        # Setup mock model
        custom_model = get_custom_model(model_name)
        
        # Determine mode
        from linkedin.agents.conversation_mode import compute_conversation_mode
        mode = compute_conversation_mode(db_messages)
        
        # Patch get_llm_model to return our custom model at its source
        with patch('linkedin.llm.get_llm_model', return_value=custom_model):
            try:
                # Mock sync_conversation to do nothing
                with patch('linkedin.db.chat.sync_conversation') as mock_sync:
                    decision = run_follow_up_agent(session, deal)
                    
                    latency = time.time() - start_time
                    message_text = decision.message or ""
                    
                    profile_sum = deal.profile_summary or {}
                    
                    # Run validator on output
                    val_ok, val_reason = validate_message(
                        message_text,
                        conversation_mode=mode.value,
                        lead_first_name_safe=profile_sum.get("first_name"),
                        seller_name="Cong"
                    )
                    
                    # Run judge only if action is send_message
                    score, analysis = 0.0, "N/A"
                    if decision.action == "send_message" and message_text:
                        score, analysis = evaluate_message_with_judge(
                            lead_name=profile_sum.get("first_name"),
                            scenario_desc=scenario_desc,
                            conversation_history=history_text,
                            generated_message=message_text
                        )
                    
                    # Force roll back
                    transaction.set_rollback(True)
                    
                    return {
                        "scenario_name": scenario_desc,
                        "lead_public_id": lead.public_identifier,
                        "lead_first_name": profile_sum.get("first_name") or "None",
                        "lead_last_name": profile_sum.get("last_name") or "None",
                        "model": model_name,
                        "action": decision.action,
                        "message": message_text,
                        "outcome": decision.outcome or "N/A",
                        "follow_up_hours": decision.follow_up_hours,
                        "latency": latency,
                        "validation_passed": val_ok,
                        "validation_error": val_reason or "N/A",
                        "judge_score": score,
                        "judge_analysis": analysis,
                        "history_text": history_text
                    }
                    
            except Exception as e:
                # Force roll back on exception
                transaction.set_rollback(True)
                profile_sum = deal.profile_summary or {}
                return {
                    "scenario_name": scenario_desc,
                    "lead_public_id": lead.public_identifier,
                    "lead_first_name": profile_sum.get("first_name") or "None",
                    "lead_last_name": profile_sum.get("last_name") or "None",
                    "model": model_name,
                    "action": "error",
                    "message": f"Error: {str(e)}",
                    "outcome": "N/A",
                    "follow_up_hours": 0,
                    "latency": time.time() - start_time,
                    "validation_passed": False,
                    "validation_error": str(e),
                    "judge_score": 0.0,
                    "judge_analysis": "Execution failed.",
                    "history_text": history_text
                }

# ── Load 30 Real Deals and Map to Scenarios ───────────────────────────
def get_test_scenarios_from_db() -> list[dict]:
    """Retrieve 30 real deals from database and pair them with scenario templates."""
    # Scenario 1 is Grant Simmons ('simmonet') using actual messages
    simmonet_deal = Deal.objects.filter(lead__public_identifier='simmonet').first()
    if not simmonet_deal:
        print("ERROR: Lead 'simmonet' not found in database! Please check migration.")
        sys.exit(1)
        
    # Get 29 other real deals from the database
    other_deals = list(Deal.objects.exclude(lead__public_identifier='simmonet')[:29])
    if len(other_deals) < 29:
        print(f"WARNING: Database only has {len(other_deals) + 1} deals. Replicating deals to reach 30 test cases.")
        # Replicate to make it 29
        while len(other_deals) < 29:
            other_deals.extend(other_deals[:29 - len(other_deals)])
            
    scenarios_to_run = []
    
    # 1. Add Simmonet as Scenario 1 (using its real DB messages)
    scenarios_to_run.append({
        "deal_id": simmonet_deal.id,
        "scenario_desc": "Replied - Real History Metaphor (Grant Simmons)",
        "messages": [], # Empty list since we use actual messages
        "use_actual_messages": True
    })
    
    # 2. Add 29 other deals paired with scenario templates
    for i, deal in enumerate(other_deals):
        template = SCENARIO_TEMPLATES[i % len(SCENARIO_TEMPLATES)]
        scenarios_to_run.append({
            "deal_id": deal.id,
            "scenario_desc": f"{template['desc']} (Lead: {deal.lead.public_identifier})",
            "messages": template["messages"],
            "use_actual_messages": False
        })
        
    return scenarios_to_run

# ── Parallel execution logic ──────────────────────────────────────────
def run_benchmark_for_model(model_name: str, scenarios: list[dict]) -> list[dict]:
    results = []
    print(f"Starting benchmark for model: {model_name}...")
    for idx, sc in enumerate(scenarios):
        print(f"  Running Scenario {idx+1}/{len(scenarios)} on {model_name}...")
        res = run_scenario(
            deal_id=sc["deal_id"],
            scenario_desc=sc["scenario_desc"],
            messages_to_create=sc["messages"],
            model_name=model_name,
            use_actual_messages=sc["use_actual_messages"]
        )
        results.append(res)
    return results

def main():
    scenarios = get_test_scenarios_from_db()
    print(f"=== Starting Multi-Model Benchmark on {len(scenarios)} Real Lead Profiles ===")
    total_start = time.time()
    
    all_results = []
    
    # We run models in parallel using ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=len(TEST_MODELS)) as executor:
        futures = {executor.submit(run_benchmark_for_model, model, scenarios): model for model in TEST_MODELS}
        for future in futures:
            model = futures[future]
            try:
                results = future.result()
                all_results.extend(results)
                print(f"Completed benchmark for model: {model}")
            except Exception as e:
                print(f"Error running benchmark for {model}: {e}")
                
    total_time = time.time() - total_start
    print(f"\nAll benchmarks finished in {total_time:.2f} seconds.")
    
    # Generate report
    generate_markdown_report(all_results, total_time)

# ── Report Generator ──────────────────────────────────────────────────
def generate_markdown_report(results: list[dict], total_duration: float):
    # Compute summary stats per model
    model_stats = {}
    for m in TEST_MODELS:
        model_results = [r for r in results if r["model"] == m]
        if not model_results:
            continue
        total_runs = len(model_results)
        val_passes = sum(1 for r in model_results if r["validation_passed"])
        avg_latency = sum(r["latency"] for r in model_results) / total_runs
        
        # Calculate average judge score for send_message actions
        judge_scores = [r["judge_score"] for r in model_results if r["action"] == "send_message" and r["judge_score"] > 0]
        avg_judge = sum(judge_scores) / len(judge_scores) if judge_scores else 0.0
        
        model_stats[m] = {
            "val_pass_rate": (val_passes / total_runs) * 100,
            "avg_latency": avg_latency,
            "avg_judge": avg_judge,
            "send_count": sum(1 for r in model_results if r["action"] == "send_message"),
            "wait_count": sum(1 for r in model_results if r["action"] == "wait"),
            "complete_count": sum(1 for r in model_results if r["action"] == "mark_completed"),
            "error_count": sum(1 for r in model_results if r["action"] == "error"),
        }
        
    report = []
    report.append("# Multi-Model Benchmark Evaluation Report\n")
    report.append(f"Tested **30 Real Leads** from database across **{len(TEST_MODELS)} Models** through 9router.")
    report.append(f"Total benchmark run duration: **{total_duration:.2f} seconds** (parallelized by model).\n")
    
    report.append("## 1. Summary Performance Dashboard\n")
    report.append("| Model | 9router Pricing | Validation Pass Rate | Avg Latency (s) | Avg Judge Score (1-10) | Actions (Send/Wait/Complete/Err) |")
    report.append("| :--- | :---: | :---: | :---: | :---: | :---: |")
    
    pricing_map = {
        "gh/gpt-5-mini": "0x (Free)",
        "gh/gpt-4.1": "0x (Free)",
        "gh/gpt-4o": "1x",
        "gh/claude-haiku-4.5": "0.33x",
        "gh/gemini-3-flash-preview": "0.33x",
        "cf/@cf/meta/llama-3.3-70b-instruct-fp8-fast": "Free (Cloudflare)",
        "cf/@cf/deepseek-ai/deepseek-r1-distill-qwen-32b": "Free (Cloudflare)"
    }
    
    for m in TEST_MODELS:
        stats = model_stats.get(m)
        if not stats:
            continue
        pricing = pricing_map.get(m, "Unknown")
        actions_str = f"{stats['send_count']} / {stats['wait_count']} / {stats['complete_count']} / {stats['error_count']}"
        report.append(f"| `{m}` | {pricing} | **{stats['val_pass_rate']:.1f}%** | {stats['avg_latency']:.2f}s | **{stats['avg_judge']:.2f}** | {actions_str} |")
        
    report.append("\n## 2. Key Findings & Recommendations\n")
    # Determine winner
    judge_sorted = sorted([(m, stats["avg_judge"], stats["val_pass_rate"]) for m, stats in model_stats.items()], key=lambda x: x[1], reverse=True)
    best_quality_model = judge_sorted[0][0] if judge_sorted else "N/A"
    
    val_sorted = sorted([(m, stats["val_pass_rate"]) for m, stats in model_stats.items()], key=lambda x: x[1], reverse=True)
    best_rule_follower = val_sorted[0][0] if val_sorted else "N/A"
    
    report.append(f"- **Best Conversational Quality (LLM Judge):** `{best_quality_model}`")
    report.append(f"- **Best Rule Follower (Validation Pass Rate):** `{best_rule_follower}`")
    report.append("- **Top Value Pick (Quality/Cost ratio):** `gh/gpt-5-mini` (0x pricing, very fast) or `cf/@cf/deepseek-ai/deepseek-r1-distill-qwen-32b` (Free reasoning model).")
    report.append("\n*Reviewer instructions: Check section 3 below to read the exact text generated by each model.*")
    
    report.append("\n## 3. Raw Output Data by Scenario (30 Real Lead Profiles)\n")
    report.append("Use the sections below to review and compare the exact text generated by each model for each real lead profile.\n")
    
    scenarios = get_test_scenarios_from_db()
    for idx, sc in enumerate(scenarios):
        scenario_id = idx + 1
        
        # Compile history text safely
        history_lines = []
        if sc["use_actual_messages"]:
            simmonet_deal = Deal.objects.filter(lead__public_identifier='simmonet').first()
            if simmonet_deal:
                ct = ContentType.objects.get_for_model(simmonet_deal.lead.__class__)
                db_messages = ChatMessage.objects.filter(content_type=ct, object_id=simmonet_deal.lead.id).order_by('creation_date')
                for msg in db_messages:
                    speaker = "Me" if msg.is_outgoing else "Lead"
                    history_lines.append(f"{speaker}: {msg.content}")
        else:
            for msg in sc["messages"]:
                speaker = "Me" if msg["is_outgoing"] else "Lead"
                history_lines.append(f"{speaker}: {msg['content']}")
        history_text = "\n".join(history_lines) if history_lines else "(No previous history)"

        report.append(f"### Scenario {scenario_id}: {sc['scenario_desc']}")
        report.append(f"**Lead name in DB:** {sc['scenario_desc']}")
        report.append(f"**Context / Message History:**")
        report.append("```")
        report.append(history_text)
        report.append("```\n")
        
        report.append("| Model | Action | Validation Status | Judge Score | Generated Message / Analysis |")
        report.append("| :--- | :---: | :---: | :---: | :--- |")
        
        for m in TEST_MODELS:
            res = next((r for r in results if r["model"] == m and r["scenario_name"] == sc["scenario_desc"]), None)
            if not res:
                # Fallback matching by name
                res = next((r for r in results if r["model"] == m and r["scenario_name"].startswith(sc["scenario_desc"][:20])), None)
            if not res:
                continue
            val_status = "✅ Pass" if res["validation_passed"] else f"❌ Fail: {res['validation_error']}"
            msg_cell = f"**\"{res['message']}\"**<br/>_Judge: {res['judge_analysis']}_" if res["action"] == "send_message" else f"_Action: {res['action']}_"
            score_str = f"{res['judge_score']:.1f}" if res["action"] == "send_message" else "N/A"
            report.append(f"| `{m}` | `{res['action']}` | {val_status} | {score_str} | {msg_cell} |")
        report.append("\n---\n")
        
    # Write to file
    os.makedirs("scratch", exist_ok=True)
    with open("scratch/benchmark_results.md", "w") as f:
        f.write("\n".join(report))
        
    print("\nBenchmark results report written to scratch/benchmark_results.md")

if __name__ == "__main__":
    main()
