-- SciVerify: verification history persistence
-- Apply in Supabase Dashboard → SQL Editor, or via Supabase CLI:
--   supabase db push

create table if not exists public.verification_history (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  claim text not null,
  doi text not null,
  paper_title text,
  verdict text not null,
  confidence numeric not null,
  summary text,
  result_json jsonb not null,
  created_at timestamptz not null default now()
);

create index if not exists verification_history_user_created_idx
  on public.verification_history (user_id, created_at desc);

alter table public.verification_history enable row level security;

drop policy if exists "Users can view own verification history" on public.verification_history;
drop policy if exists "Users can insert own verification history" on public.verification_history;
drop policy if exists "Users can update own verification history" on public.verification_history;
drop policy if exists "Users can delete own verification history" on public.verification_history;

create policy "Users can view own verification history"
  on public.verification_history
  for select
  using (auth.uid() = user_id);

create policy "Users can insert own verification history"
  on public.verification_history
  for insert
  with check (auth.uid() = user_id);

create policy "Users can update own verification history"
  on public.verification_history
  for update
  using (auth.uid() = user_id)
  with check (auth.uid() = user_id);

create policy "Users can delete own verification history"
  on public.verification_history
  for delete
  using (auth.uid() = user_id);

