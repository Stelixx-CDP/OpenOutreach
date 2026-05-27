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

from django.db import connection

print("=== DB Connection and Tables Inspection ===")
print(f"DATABASE_URL: {os.environ.get('DATABASE_URL')}")
with connection.cursor() as cursor:
    cursor.execute("""
        SELECT table_name 
        FROM information_schema.tables 
        WHERE table_schema = 'public'
    """)
    tables = [row[0] for row in cursor.fetchall()]
    print(f"Tables count: {len(tables)}")
    print(f"Tables: {tables}")
    
    # Check crm_deal count
    if 'crm_deal' in tables:
        cursor.execute("SELECT COUNT(*) FROM crm_deal")
        print(f"crm_deal rows: {cursor.fetchone()[0]}")
