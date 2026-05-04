create table public.messages (
  id uuid primary key default gen_random_uuid(),
  sender_id uuid not null references public.profiles (id) on delete cascade,
  recipient_id uuid not null references public.profiles (id) on delete cascade,
  job_id uuid references public.jobs (id) on delete cascade,
  application_id uuid references public.applications (id) on delete cascade,
  booking_id uuid references public.bookings (id) on delete cascade,
  body text not null check (char_length(btrim(body)) >= 1 and char_length(body) <= 2000),
  read_at timestamptz,
  created_at timestamptz not null default now(),
  constraint ck_messages_distinct_participants check (sender_id <> recipient_id),
  constraint ck_messages_has_context check (
    job_id is not null
    or application_id is not null
    or booking_id is not null
  )
);

create index idx_messages_sender_created_at
  on public.messages (sender_id, created_at desc);

create index idx_messages_recipient_created_at
  on public.messages (recipient_id, created_at desc);

create index idx_messages_context_created_at
  on public.messages (application_id, booking_id, job_id, created_at desc);

create index idx_messages_recipient_read_at
  on public.messages (recipient_id, read_at, created_at desc);

alter table public.messages enable row level security;

create policy messages_participant_read
  on public.messages
  for select
  to authenticated
  using (
    sender_id = auth.uid()
    or recipient_id = auth.uid()
    or public.is_admin()
  );

create policy messages_sender_insert
  on public.messages
  for insert
  to authenticated
  with check (
    sender_id = auth.uid()
    or public.is_admin()
  );

create or replace function public.mark_message_read(p_message_id uuid)
returns void
language plpgsql
security definer
set search_path = public
as $$
begin
  update public.messages
     set read_at = now()
   where id = p_message_id
     and recipient_id = auth.uid()
     and read_at is null;
end;
$$;

revoke all on function public.mark_message_read(uuid) from public;
grant execute on function public.mark_message_read(uuid) to authenticated, service_role;

create policy messages_service_role_all
  on public.messages
  for all
  to service_role
  using (true)
  with check (true);
