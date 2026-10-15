create table if not exists public."kboTodaySchedule" (
  date        date        primary key,
  games       jsonb       not null default '[]'::jsonb,
  updated_at  timestamptz not null default now()
);

alter table "kboTodaySchedule" enable row level security;

create policy "kboTodaySchedule_public_read"
  on "kboTodaySchedule" for select
  using (true);
