-- KaziX baseline schema
-- Covers existing backend APIs + newly added notifications/messages/reviews/disputes APIs.

create extension if not exists pgcrypto;

create or replace function public.set_updated_at()
returns trigger
language plpgsql
as $$
begin
  new.updated_at = timezone('utc', now());
  return new;
end;
$$;

create table if not exists public.profiles (
  id uuid primary key references auth.users (id) on delete cascade,
  role text not null default 'client' check (role in ('client', 'fundi', 'admin')),
  full_name text not null default 'User',
  phone text not null unique,
  email text,
  county text,
  area text,
  avatar_url text,
  mpesa_number text,
  preferred_language text not null default 'en' check (preferred_language in ('en', 'sw')),
  is_verified boolean not null default false,
  is_suspended boolean not null default false,
  created_at timestamptz not null default timezone('utc', now()),
  updated_at timestamptz not null default timezone('utc', now())
);

create table if not exists public.fundi_profiles (
  id uuid primary key references public.profiles (id) on delete cascade,
  trade text not null,
  bio text,
  rate_min integer check (rate_min is null or rate_min >= 0),
  rate_max integer check (rate_max is null or rate_max >= 0),
  experience_years integer check (experience_years is null or (experience_years >= 0 and experience_years <= 60)),
  skills text[] not null default '{}'::text[],
  service_radius_km integer not null default 15 check (service_radius_km >= 0),
  rating_avg numeric(3,2) not null default 0,
  jobs_completed integer not null default 0,
  is_available boolean not null default true,
  kyc_status text not null default 'pending' check (kyc_status in ('pending', 'approved', 'rejected', 'resubmission_requested')),
  kyc_reviewer_id uuid references public.profiles (id),
  kyc_reviewed_at timestamptz,
  created_at timestamptz not null default timezone('utc', now()),
  updated_at timestamptz not null default timezone('utc', now())
);

create table if not exists public.jobs (
  id uuid primary key default gen_random_uuid(),
  client_id uuid not null references public.profiles (id) on delete cascade,
  title text not null,
  description text not null,
  trade text not null,
  county text not null,
  area text not null,
  street text,
  budget_min integer check (budget_min is null or budget_min >= 0),
  budget_max integer check (budget_max is null or budget_max >= 0),
  payment_type text not null default 'negotiable' check (payment_type in ('fixed', 'hourly', 'daily', 'negotiable')),
  urgency text not null default 'flexible' check (urgency in ('flexible', 'urgent')),
  preferred_date date,
  preferred_time text,
  materials_provided boolean not null default false,
  status text not null default 'open' check (status in ('open', 'reviewing', 'active', 'completed', 'cancelled', 'expired')),
  expires_at timestamptz,
  created_at timestamptz not null default timezone('utc', now()),
  updated_at timestamptz not null default timezone('utc', now())
);

create table if not exists public.applications (
  id uuid primary key default gen_random_uuid(),
  job_id uuid not null references public.jobs (id) on delete cascade,
  fundi_id uuid not null references public.profiles (id) on delete cascade,
  bid_amount integer check (bid_amount is null or bid_amount >= 0),
  cover_note text,
  status text not null default 'pending' check (status in ('pending', 'shortlisted', 'hired', 'rejected', 'withdrawn')),
  created_at timestamptz not null default timezone('utc', now()),
  updated_at timestamptz not null default timezone('utc', now()),
  constraint uq_application unique (job_id, fundi_id)
);

create table if not exists public.bookings (
  id uuid primary key default gen_random_uuid(),
  job_id uuid not null references public.jobs (id) on delete cascade,
  application_id uuid not null references public.applications (id) on delete restrict,
  client_id uuid not null references public.profiles (id) on delete cascade,
  fundi_id uuid not null references public.profiles (id) on delete cascade,
  agreed_amount integer not null check (agreed_amount >= 0),
  start_date date,
  status text not null default 'confirmed' check (status in ('confirmed', 'in_progress', 'completed', 'cancelled')),
  escrow_status text not null default 'pending' check (escrow_status in ('pending', 'held', 'disputed', 'released', 'refunded', 'failed')),
  escrow_held_at timestamptz,
  escrow_released_at timestamptz,
  mpesa_receipt text,
  created_at timestamptz not null default timezone('utc', now()),
  updated_at timestamptz not null default timezone('utc', now()),
  constraint uq_booking_application unique (application_id)
);

create table if not exists public.transactions (
  id uuid primary key default gen_random_uuid(),
  booking_id uuid not null references public.bookings (id) on delete cascade,
  type text not null check (type in ('escrow_in', 'escrow_out', 'refund', 'adjustment')),
  amount integer not null check (amount >= 0),
  mpesa_ref text,
  from_phone text,
  to_phone text,
  status text not null default 'pending' check (status in ('pending', 'confirmed', 'failed')),
  created_at timestamptz not null default timezone('utc', now())
);

create table if not exists public.notifications (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references public.profiles (id) on delete cascade,
  type text not null,
  title text not null,
  body text not null,
  action_url text,
  is_read boolean not null default false,
  created_at timestamptz not null default timezone('utc', now()),
  updated_at timestamptz not null default timezone('utc', now())
);

create table if not exists public.messages (
  id uuid primary key default gen_random_uuid(),
  booking_id uuid not null references public.bookings (id) on delete cascade,
  sender_id uuid not null references public.profiles (id) on delete cascade,
  recipient_id uuid not null references public.profiles (id) on delete cascade,
  body text not null check (length(trim(body)) > 0),
  is_read boolean not null default false,
  created_at timestamptz not null default timezone('utc', now()),
  updated_at timestamptz not null default timezone('utc', now())
);

create table if not exists public.reviews (
  id uuid primary key default gen_random_uuid(),
  booking_id uuid not null references public.bookings (id) on delete cascade,
  reviewer_id uuid not null references public.profiles (id) on delete cascade,
  reviewee_id uuid not null references public.profiles (id) on delete cascade,
  rating smallint not null check (rating between 1 and 5),
  quality smallint check (quality is null or quality between 1 and 5),
  punctuality smallint check (punctuality is null or punctuality between 1 and 5),
  communication smallint check (communication is null or communication between 1 and 5),
  value_for_money smallint check (value_for_money is null or value_for_money between 1 and 5),
  would_hire_again boolean,
  comment text not null,
  created_at timestamptz not null default timezone('utc', now()),
  constraint uq_review_booking_reviewer unique (booking_id, reviewer_id)
);

create table if not exists public.disputes (
  id uuid primary key default gen_random_uuid(),
  booking_id uuid not null references public.bookings (id) on delete cascade,
  raised_by uuid not null references public.profiles (id) on delete cascade,
  reason text not null,
  description text not null,
  desired_resolution text,
  amount_disputed integer check (amount_disputed is null or amount_disputed >= 0),
  evidence_urls text[] not null default '{}'::text[],
  status text not null default 'open' check (status in ('open', 'resolved_client', 'resolved_fundi', 'withdrawn')),
  admin_notes text,
  resolved_by uuid references public.profiles (id),
  resolved_at timestamptz,
  created_at timestamptz not null default timezone('utc', now()),
  updated_at timestamptz not null default timezone('utc', now())
);

create index if not exists idx_profiles_role on public.profiles (role);
create index if not exists idx_jobs_client_id on public.jobs (client_id);
create index if not exists idx_jobs_status_created_at on public.jobs (status, created_at desc);
create index if not exists idx_jobs_trade_county on public.jobs (trade, county);
create index if not exists idx_applications_job_id on public.applications (job_id);
create index if not exists idx_applications_fundi_id on public.applications (fundi_id);
create index if not exists idx_bookings_client_id on public.bookings (client_id);
create index if not exists idx_bookings_fundi_id on public.bookings (fundi_id);
create index if not exists idx_transactions_booking_id on public.transactions (booking_id);
create index if not exists idx_transactions_mpesa_ref on public.transactions (mpesa_ref);
create index if not exists idx_notifications_user_created_at on public.notifications (user_id, created_at desc);
create index if not exists idx_messages_booking_created_at on public.messages (booking_id, created_at);
create index if not exists idx_messages_recipient_unread on public.messages (recipient_id, is_read);
create index if not exists idx_reviews_reviewee_created_at on public.reviews (reviewee_id, created_at desc);
create index if not exists idx_disputes_booking_id on public.disputes (booking_id);
create index if not exists idx_disputes_status_created_at on public.disputes (status, created_at desc);
create unique index if not exists uq_disputes_open_per_booking on public.disputes (booking_id) where status = 'open';

drop trigger if exists trg_profiles_updated_at on public.profiles;
create trigger trg_profiles_updated_at
before update on public.profiles
for each row execute function public.set_updated_at();

drop trigger if exists trg_fundi_profiles_updated_at on public.fundi_profiles;
create trigger trg_fundi_profiles_updated_at
before update on public.fundi_profiles
for each row execute function public.set_updated_at();

drop trigger if exists trg_jobs_updated_at on public.jobs;
create trigger trg_jobs_updated_at
before update on public.jobs
for each row execute function public.set_updated_at();

drop trigger if exists trg_applications_updated_at on public.applications;
create trigger trg_applications_updated_at
before update on public.applications
for each row execute function public.set_updated_at();

drop trigger if exists trg_bookings_updated_at on public.bookings;
create trigger trg_bookings_updated_at
before update on public.bookings
for each row execute function public.set_updated_at();

drop trigger if exists trg_notifications_updated_at on public.notifications;
create trigger trg_notifications_updated_at
before update on public.notifications
for each row execute function public.set_updated_at();

drop trigger if exists trg_messages_updated_at on public.messages;
create trigger trg_messages_updated_at
before update on public.messages
for each row execute function public.set_updated_at();

drop trigger if exists trg_disputes_updated_at on public.disputes;
create trigger trg_disputes_updated_at
before update on public.disputes
for each row execute function public.set_updated_at();
