-- Add profile picture storage path tracking
-- This column stores the Supabase Storage path for cleanup when pictures are deleted

alter table public.profiles
add column profile_picture_storage_path text;

-- Add comment for context
comment on column public.profiles.profile_picture_storage_path is 'Storage path in Supabase "profile-pictures" bucket for picture deletion tracking';
