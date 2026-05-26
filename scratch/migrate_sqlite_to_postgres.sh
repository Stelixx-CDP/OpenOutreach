#!/usr/bin/env bash
# migrate_sqlite_to_postgres.sh
# Script chuyển data từ SQLite sang PostgreSQL (Supabase).
#
# Cách dùng:
#   1. Đảm bảo DATABASE_URL đã set trong .env (trỏ tới Supabase, port 5432)
#   2. Chạy: bash scratch/migrate_sqlite_to_postgres.sh
#
# Script sẽ:
#   1. Dump data từ SQLite hiện tại (KHÔNG cần DATABASE_URL)
#   2. Chạy migrate trên PostgreSQL (dùng DATABASE_URL)
#   3. Load data vào PostgreSQL
#
# Lưu ý: Script backup data trước khi thao tác.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
cd "$PROJECT_DIR"

VENV_PYTHON=".venv/bin/python"
DUMP_FILE="data/sqlite_dump.json"

echo "═══════════════════════════════════════════════"
echo "  OpenOutreach: SQLite → PostgreSQL Migration"
echo "═══════════════════════════════════════════════"
echo ""

# Kiểm tra DATABASE_URL
if [ -z "${DATABASE_URL:-}" ]; then
    # Thử load từ .env
    if [ -f .env ]; then
        export $(grep -v '^#' .env | grep DATABASE_URL | xargs 2>/dev/null) || true
    fi
fi

if [ -z "${DATABASE_URL:-}" ]; then
    echo "❌ DATABASE_URL chưa được set."
    echo "   Set trong .env hoặc: export DATABASE_URL=postgresql://..."
    exit 1
fi

echo "📊 Database URL: ${DATABASE_URL%%@*}@***"
echo ""

# Step 1: Dump từ SQLite (tạm unset DATABASE_URL để force SQLite)
echo "📦 Step 1: Dumping data from SQLite..."
(
    unset DATABASE_URL
    $VENV_PYTHON manage.py dumpdata \
        --natural-foreign --natural-primary \
        --indent 2 \
        -e contenttypes \
        -e auth.Permission \
        -e sessions \
        -e admin.logentry \
        -o "$DUMP_FILE"
)
DUMP_SIZE=$(wc -l < "$DUMP_FILE" | tr -d ' ')
echo "   ✅ Dumped to $DUMP_FILE ($DUMP_SIZE lines)"
echo ""

# Step 2: Migrate schema trên PostgreSQL
echo "🏗️  Step 2: Running migrations on PostgreSQL..."
$VENV_PYTHON manage.py migrate --no-input
echo "   ✅ Schema created/updated"
echo ""

# Step 3: Load data vào PostgreSQL
echo "📥 Step 3: Loading data into PostgreSQL..."
$VENV_PYTHON manage.py loaddata "$DUMP_FILE"
echo "   ✅ Data loaded successfully"
echo ""

# Step 4: Verify
echo "🔍 Step 4: Verifying..."
$VENV_PYTHON -c "
import django, os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'linkedin.django_settings')
django.setup()
from crm.models import Lead, Deal
from chat.models import ChatMessage
from linkedin.models import Campaign, LinkedInProfile, SiteConfig
print(f'   Leads:    {Lead.objects.count()}')
print(f'   Deals:    {Deal.objects.count()}')
print(f'   Messages: {ChatMessage.objects.count()}')
print(f'   Campaigns:{Campaign.objects.count()}')
print(f'   Profiles: {LinkedInProfile.objects.count()}')
cfg = SiteConfig.load()
print(f'   LLM:      {cfg.llm_provider} / {cfg.ai_model}')
"
echo ""
echo "═══════════════════════════════════════════════"
echo "  ✅ Migration complete!"
echo ""
echo "  Bước tiếp theo trên VPS:"
echo "  1. Thêm DATABASE_URL vào .env"
echo "  2. Restart daemon: make run"
echo "═══════════════════════════════════════════════"
