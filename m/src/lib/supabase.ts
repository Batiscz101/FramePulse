import { createClient } from '@supabase/supabase-js';

/**
 * The publishable (anon) key is meant to be embedded in the client app – the
 * data is protected by RLS policies (see `supabase_schema.sql` in the project
 * root). Never put the Secret / service_role key here.
 *
 * Values are read from `EXPO_PUBLIC_SUPABASE_URL` and
 * `EXPO_PUBLIC_SUPABASE_ANON_KEY` in the `.env.local` file (template:
 * `.env.example`). Without them the sample address is used and the app shows
 * a connection error until you create your own Supabase project.
 */
const SUPABASE_URL =
  process.env.EXPO_PUBLIC_SUPABASE_URL ?? 'https://your-project.supabase.co';

const SUPABASE_KEY = process.env.EXPO_PUBLIC_SUPABASE_ANON_KEY ?? 'your-anon-key';

export const supabase = createClient(SUPABASE_URL, SUPABASE_KEY, {
  auth: {
    // The app is not signed in – it reads and writes under the anon role.
    persistSession: false,
    autoRefreshToken: false,
    detectSessionInUrl: false,
  },
});
