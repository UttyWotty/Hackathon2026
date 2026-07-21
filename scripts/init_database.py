#!/usr/bin/env python
"""
Initialize Manufacturing Analytics Database

Creates SQLite database with all required tables for:
- Scheduled jobs
- Audit logs
- Monitoring metrics and alerts

Usage:
    python scripts/init_database.py

This is safe to run multiple times - it won't overwrite existing data.
"""

import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from models.database import get_database_info, init_database  # noqa: E402


def main():
    """Initialize database."""
    print("=" * 70)
    print("🏭 Manufacturing Analytics - Database Initialization")
    print("=" * 70)
    print()

    # Initialize database
    print("📦 Creating database tables...")
    success = init_database()

    if not success:
        print()
        print("❌ Database initialization failed!")
        print("   Check the error messages above.")
        sys.exit(1)

    # Get database info
    db_info = get_database_info()

    print()
    print("=" * 70)
    print("✅ DATABASE INITIALIZED SUCCESSFULLY!")
    print("=" * 70)
    print()
    print("📊 Database Information:")
    print(f"   Location: {db_info['database_path']}")
    print(f"   Size: {db_info['database_size_mb']} MB")
    print("   Type: SQLite 3")
    print()
    print("📋 Tables Created:")
    print("   ✅ scheduled_jobs    - Recurring job configuration")
    print("   ✅ audit_logs        - API call tracking and compliance")
    print("   ✅ metrics           - System metrics time-series")
    print("   ✅ alert_rules       - Alert rule configuration")
    print("   ✅ alert_history     - Alert trigger history")
    print()
    print("🚀 Next Steps:")
    print("   1. Start the server: python main.py")
    print("   2. View API docs: http://localhost:3020/docs")
    print("   3. Test scheduler: POST /scheduler/jobs")
    print()
    print("=" * 70)

    return 0


if __name__ == "__main__":
    sys.exit(main())
