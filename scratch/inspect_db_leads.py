import os
import django

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

from crm.models import Deal
from chat.models import ChatMessage
from django.contrib.contenttypes.models import ContentType

print("=== DB Inspection ===")
deals = Deal.objects.all()
print(f"Total Deals: {deals.count()}")

# Find deals with chat_summary facts
deals_with_summary = [d for d in deals if d.chat_summary and d.chat_summary.get('facts')]
print(f"Deals with chat_summary facts: {len(deals_with_summary)}")

# Find chat messages
messages = ChatMessage.objects.all()
print(f"Total ChatMessages in DB: {messages.count()}")

# Print some details of deals with summary
for d in deals_with_summary[:10]:
    lead = d.lead
    print(f"Lead: {lead.public_identifier}")
    print(f"  Profile Summary: {d.profile_summary}")
    print(f"  Chat Summary: {d.chat_summary}")
    # Check messages
    ct = ContentType.objects.get_for_model(lead.__class__)
    msg_count = ChatMessage.objects.filter(content_type=ct, object_id=lead.id).count()
    print(f"  ChatMessage count: {msg_count}")
    print("-" * 30)
