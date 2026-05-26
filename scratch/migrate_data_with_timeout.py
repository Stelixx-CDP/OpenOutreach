import os
import sys
import django
from django.db.backends.signals import connection_created
from django.dispatch import receiver

# Setup Django environment và PYTHONPATH
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'linkedin.django_settings')
django.setup()

from django.core.management import call_command

# Đăng ký signal để tự động vô hiệu hóa statement timeout trên mọi connection mới
@receiver(connection_created)
def set_db_timeout(sender, connection, **kwargs):
    try:
        with connection.cursor() as cursor:
            cursor.execute("SET statement_timeout = 0;")
            print("   [DB Connection] Vô hiệu hóa statement_timeout thành công (set = 0)")
    except Exception as e:
        print(f"   [DB Connection] Cảnh báo: Không thể set statement_timeout: {e}")

print("═══════════════════════════════════════════════")
print("  OpenOutreach: Khởi chạy loaddata lên Supabase")
print("  (Vô hiệu hóa statement_timeout để tránh lỗi)")
print("═══════════════════════════════════════════════")
print("")

dump_file = "scratch/sqlite_dump.json"

if not os.path.exists(dump_file):
    print(f"❌ Không tìm thấy file dump tại: {dump_file}")
    sys.exit(1)

print(f"📥 Đang nạp dữ liệu từ {dump_file}...")
try:
    # Chạy loaddata
    call_command('loaddata', dump_file)
    print("\n✅ Dữ liệu đã được nạp thành công lên Supabase!")
except Exception as e:
    print(f"\n❌ Lỗi khi nạp dữ liệu: {e}")
    sys.exit(1)
