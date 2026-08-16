-- ==========================================================================
-- Fiscus — Row Level Security for the Track tables
--
-- How to use: run `python manage.py migrate` first (creates the tables),
-- then run this file in Supabase → Project → SQL Editor → New query → Run.
--
-- Why it matters: Auth lives in Supabase. RLS makes sure that even with the
-- public anon key, direct PostgREST access can only ever see a user's own
-- rows. Django connects with the privileged postgres role (bypasses RLS as
-- table owner) and enforces the same ownership rule itself by filtering
-- every query on the JWT-verified user id.
-- ==========================================================================

ALTER TABLE public.track_expense ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.track_budget  ENABLE ROW LEVEL SECURITY;

-- ---- track_expense: users may only touch their own rows ----
CREATE POLICY "expense_select_own" ON public.track_expense
  FOR SELECT USING (auth.uid() = user_id);

CREATE POLICY "expense_insert_own" ON public.track_expense
  FOR INSERT WITH CHECK (auth.uid() = user_id);

CREATE POLICY "expense_update_own" ON public.track_expense
  FOR UPDATE USING (auth.uid() = user_id);

CREATE POLICY "expense_delete_own" ON public.track_expense
  FOR DELETE USING (auth.uid() = user_id);

-- ---- track_budget: users may only touch their own rows ----
CREATE POLICY "budget_select_own" ON public.track_budget
  FOR SELECT USING (auth.uid() = user_id);

CREATE POLICY "budget_insert_own" ON public.track_budget
  FOR INSERT WITH CHECK (auth.uid() = user_id);

CREATE POLICY "budget_update_own" ON public.track_budget
  FOR UPDATE USING (auth.uid() = user_id);

CREATE POLICY "budget_delete_own" ON public.track_budget
  FOR DELETE USING (auth.uid() = user_id);

-- Sanity check: list policies
-- SELECT schemaname, tablename, policyname FROM pg_policies
--   WHERE tablename IN ('track_expense', 'track_budget') ORDER BY tablename;
