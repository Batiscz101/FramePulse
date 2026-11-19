import { createClient } from '@supabase/supabase-js';

/**
 * Publishable (anon) klíč je určený k zabudování do klientské aplikace – data
 * chrání RLS politiky (viz `supabase_schema.sql` v kořeni projektu).
 * Secret / service_role klíč sem nikdy nevkládejte.
 *
 * Hodnoty se načítají z `EXPO_PUBLIC_SUPABASE_URL` a
 * `EXPO_PUBLIC_SUPABASE_ANON_KEY` v souboru `.env.local` (vzor:
 * `.env.example`). Bez nich se použije ukázková adresa a aplikace zobrazí
 * chybu připojení, dokud si nevytvoříte vlastní Supabase projekt.
 */
const SUPABASE_URL =
  process.env.EXPO_PUBLIC_SUPABASE_URL ?? 'https://your-project.supabase.co';

const SUPABASE_KEY = process.env.EXPO_PUBLIC_SUPABASE_ANON_KEY ?? 'your-anon-key';

export const supabase = createClient(SUPABASE_URL, SUPABASE_KEY, {
  auth: {
    // Aplikace se nepřihlašuje – čte a zapisuje pod anon rolí.
    persistSession: false,
    autoRefreshToken: false,
    detectSessionInUrl: false,
  },
});
