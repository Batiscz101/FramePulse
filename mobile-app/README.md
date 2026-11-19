# FramePulse — mobile app

Expo (React Native + TypeScript) telemetrie FPS. Tmavý minimalistický design ve stylu Apple Health / Whoop / Linear.

## Připojení k Supabase

Data se načítají ze stejného Supabase projektu jako u `pc-agent`. Zkopírujte vzor
a doplňte údaje z **Project Settings → API**:

```bash
cp .env.example .env.local   # Windows: copy .env.example .env.local
```

```dotenv
EXPO_PUBLIC_SUPABASE_URL=https://<project-ref>.supabase.co
EXPO_PUBLIC_SUPABASE_ANON_KEY=<anon nebo publishable klíč>
```

`.env.local` je ignorovaný gitem. Bez něj aplikace použije ukázkovou adresu a
zobrazí chybu připojení. Tabulky vytvoří [`supabase_schema.sql`](../supabase_schema.sql).

## Spuštění

```bash
npm install
npx expo start
```

Poté naskenujte QR kód v aplikaci **Expo Go** (Android/iOS). Po změně
`.env.local` restartujte dev server.

## Obrazovky

- `src/app/index.tsx` — seznam her s vyhledáváním, posledním průměrným FPS a datem.
- `src/app/game/[id].tsx` — detail hry: výběr seance, Avg / Min / Max FPS a interaktivní graf.
- `src/components/fps-chart.tsx` — `react-native-gifted-charts` s pointer tooltipem.
- `src/lib/telemetry-api.ts` — čtení a zápis dat přes Supabase (PostgREST).
- `src/lib/i18n.ts` — překlady do češtiny a angličtiny.

## Kontrola

```bash
npx tsc --noEmit   # typecheck
npx expo lint      # lint
npx expo-doctor    # kontrola závislostí
```
