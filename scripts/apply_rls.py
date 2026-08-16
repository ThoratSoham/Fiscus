"""Apply the RLS policies from supabase/rls_policies.sql to the connected DB.

Usage: .venv/Scripts/python.exe scripts/apply_rls.py

Run after `python manage.py migrate` has created the tables. Idempotent:
any existing policies on track_expense / track_budget are dropped first.
"""
import os
import sys

import django

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "fiscus.settings")
django.setup()

from django.db import connection  # noqa: E402

SQL_PATH = os.path.join(ROOT, "supabase", "rls_policies.sql")


def main():
    with open(SQL_PATH, encoding="utf-8") as f:
        content = f.read()

    drop_existing = """
        DO $$
        DECLARE p RECORD;
        BEGIN
            FOR p IN
                SELECT policyname, tablename FROM pg_policies
                WHERE tablename IN ('track_expense', 'track_budget')
            LOOP
                EXECUTE format('DROP POLICY IF EXISTS %I ON public.%I', p.policyname, p.tablename);
            END LOOP;
        END $$;
    """

    # Strip comment lines so statements that follow comments aren't dropped.
    clean_lines = [ln for ln in content.splitlines() if not ln.lstrip().startswith("--")]
    clean_sql = "\n".join(clean_lines)

    with connection.cursor() as cursor:
        cursor.execute(drop_existing)
        for statement in clean_sql.split(";"):
            statement = statement.strip()
            if not statement:
                continue
            cursor.execute(statement)

    print("RLS policies applied.")


if __name__ == "__main__":
    main()
