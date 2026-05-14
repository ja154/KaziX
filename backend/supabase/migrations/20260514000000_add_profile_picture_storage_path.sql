-- Add profile_picture_storage_path column to profiles table
alter table public.profiles
add column profile_picture_storage_path text;

comment on column public.profiles.profile_picture_storage_path
is 'Storage path in Supabase "profile-pictures" bucket for picture deletion tracking';
