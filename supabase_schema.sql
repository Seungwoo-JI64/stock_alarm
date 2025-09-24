-- Table structure for storing volume snapshots
create table if not exists public.volume_snapshots (
    id bigserial primary key,
    batch_id uuid not null,
    ticker text not null,
    last_trade_date date not null,
    previous_trade_date date not null,
    latest_volume bigint not null,
    previous_volume bigint not null,
    volume_ratio numeric(18,6),
    volume_change_pct numeric(18,6),
    is_spike boolean not null default false,
    fetched_at_utc timestamptz not null,
    fetched_at_kst timestamptz not null,
    created_at timestamptz not null default timezone('utc', now())
);

alter table public.volume_snapshots
    add constraint volume_snapshots_batch_ticker_unique unique (batch_id, ticker);

create index if not exists volume_snapshots_batch_idx on public.volume_snapshots (batch_id);
create index if not exists volume_snapshots_pct_idx on public.volume_snapshots (volume_change_pct desc);
create index if not exists volume_snapshots_ticker_idx on public.volume_snapshots (ticker);

-- Enable and open read access for clients (Supabase anon key)
alter table public.volume_snapshots enable row level security;

do $$
begin
    if not exists (
        select 1 from pg_policies where schemaname = 'public' and tablename = 'volume_snapshots' and policyname = 'volume_snapshots_select_anon'
    ) then
        create policy volume_snapshots_select_anon on public.volume_snapshots
            for select
            using (true);
    end if;
end $$;

-- Helper view to get the latest batch faster
create or replace view public.volume_snapshots_latest as
select vs.*
from public.volume_snapshots vs
join (
    select batch_id
    from public.volume_snapshots
    order by created_at desc
    limit 1
) latest on vs.batch_id = latest.batch_id;
