# Supabase Storage Setup for Profile Pictures

## Bucket Creation

The `profile-pictures` bucket needs to be created in Supabase Storage with the following configuration:

### Via Supabase Dashboard

1. Go to **Storage** → **New Bucket**
2. Name: `profile-pictures`
3. Privacy: **Public** (to serve images directly)
4. Click **Create bucket**

## Row-Level Security (RLS) Policies

The following RLS policies should be applied to the `profile-pictures` bucket:

### Policy 1: Users can upload their own pictures
```
Name: "Allow users to upload their own profile pictures"
Definition: (bucket_id = 'profile-pictures' AND (auth.uid())::text = (storage.foldername(name))[1])
Allowed operation: INSERT
```

### Policy 2: Users can delete their own pictures
```
Name: "Allow users to delete their own profile pictures"
Definition: (bucket_id = 'profile-pictures' AND (auth.uid())::text = (storage.foldername(name))[1])
Allowed operation: DELETE
```

### Policy 3: Public read access to all pictures
```
Name: "Allow public read access to profile pictures"
Definition: (bucket_id = 'profile-pictures')
Allowed operation: SELECT
```

## Configuration in Supabase Dashboard

1. Go to **Storage** → **Policies**
2. Select the `profile-pictures` bucket
3. Add the three policies above
4. Enable RLS on the bucket if not already enabled

## Verification

After setup, verify:
- ✅ Users can upload JPG/PNG files to `profile-pictures/{user_id}/{uuid}.{ext}`
- ✅ Users cannot access other users' pictures for deletion
- ✅ Public URLs like `https://{project}.supabase.co/storage/v1/object/public/profile-pictures/{path}` are accessible
- ✅ Old pictures are automatically deleted when new ones are uploaded

## Notes

- Images are stored in the format: `profile-pictures/{user_id}/{uuid}.{ext}`
- The `profile_picture_storage_path` column in the `profiles` table tracks this path for cleanup
- Public URLs have cache control set to 1 week (`max-age=604800`)
- If bucket RLS is not properly configured, image uploads will fail with 403 errors
