import os
import sys
import django

# Setup Django environment
from pathlib import Path
project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'linkedin.django_settings')
django.setup()

from crm.models import Lead, Deal

print("═══════════════════════════════════════════════")
print("🔄 Đang sửa thông tin Lead Names & Chat Summaries trên Supabase...")
print("═══════════════════════════════════════════════\n")

# Định nghĩa map thông tin chính xác của các lead
leads_data = {
    'simmonet': {'first_name': 'Grant', 'last_name': 'Simmons'},
    'danieljburford': {'first_name': 'Daniel', 'last_name': 'Burford'},
    'chrisharrisonseo': {'first_name': 'Chris', 'last_name': 'Harrison'},
    'olga-kunger': {'first_name': 'Olga', 'last_name': 'Kunger'},
    'kristanbauer': {'first_name': 'Kristan', 'last_name': 'Bauer'},
    'lily-ray-44755615': {'first_name': 'Lily', 'last_name': 'Ray'}
}

# 1. Cập nhật profile_summary
for pub_id, names in leads_data.items():
    deals = Deal.objects.filter(lead__public_identifier=pub_id)
    if deals.exists():
        print(f"📍 Lead: {pub_id}")
        for deal in deals:
            # Tạo hoặc cập nhật profile_summary
            p_sum = deal.profile_summary or {}
            
            # Đảm bảo là dict
            if isinstance(p_sum, list):
                 p_sum = {'facts': p_sum}
            elif not isinstance(p_sum, dict):
                 p_sum = {'facts': []}
                 
            p_sum['first_name'] = names['first_name']
            p_sum['last_name'] = names['last_name']
            
            deal.profile_summary = p_sum
            deal.save(update_fields=['profile_summary'])
            print(f"   ✅ Đã cập nhật profile_summary cho Deal ID={deal.id} (Tên: {names['first_name']} {names['last_name']})")

# 2. Làm sạch chat_summary bị nhiễm của simmonet
simmonet_deals = Deal.objects.filter(lead__public_identifier='simmonet')
for deal in simmonet_deals:
    if deal.chat_summary and 'facts' in deal.chat_summary:
        facts = deal.chat_summary['facts']
        # Lọc bỏ các fact sai liên quan tới tên "Cong"
        clean_facts = [
            f for f in facts 
            if "name is Cong" not in f.lower() 
            and "cong works" not in f.lower()
            and "cong is measuring" not in f.lower()
        ]
        
        # Thêm fact đúng về tên của Lead
        if "The lead's name is Grant." not in clean_facts:
             clean_facts.insert(0, "The lead's name is Grant.")
             
        deal.chat_summary['facts'] = clean_facts
        deal.save(update_fields=['chat_summary'])
        print(f"\n🧹 Đã làm sạch chat_summary cho simmonet (Deal ID={deal.id}):")
        for f in clean_facts:
            print(f"   • {f}")

print("\n═══════════════════════════════════════════════")
print("🎉 ĐÃ HOÀN TẤT CẬP NHẬT DỮ LIỆU SẠCH! 🎉")
print("═══════════════════════════════════════════════")
