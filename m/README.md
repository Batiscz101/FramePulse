# FramePulse — mobile app

Expo (React Native + TypeScript) FPS telemetry. Minimalist dark design
inspired by Apple Health / Whoop / Linear.

## Connect to Supabase

Data is loaded from the same Supabase project as `pc-agent`. Copy the sample
and fill in the values from **Project Settings → API**:

```bash
cp .env.example .env.local   # Windows: copy .env.example .env.local
```

```dotenv
EXPO_PUBLIC_SUPABASE_URL=https://<project-ref>.supabase.co
EXPO_PUBLIC_SUPABASE_ANON_KEY=<anon or publishable key>
```

`.env.local` is ignored by git. Without it the app uses the sample address
and shows a connection error. The tables are created by
[`supabase_schema.sql`](../supabase_schema.sql).

## Running

```bash
npm install
npx expo start
```

Then scan the QR code in the app **Expo Go** (Android/iOS). After changing
`.env.local`, restart the dev server.

## Screens

- `src/app/index.tsx` — list of games with search, last average FPS and date.
- `src/app/game/[id].tsx` — game detail: session selection, Avg / Min / Max
  FPS and the interactive chart.
- `src/components/fps-chart.tsx` — `react-native-gifted-charts` with a pointer
  tooltip.
- `src/lib/telemetry-api.ts` — reading and writing data via Supabase
  (PostgREST).
- `src/lib/i18n.ts` — translations to Czech and English.

## Checks

```bash
npx tsc --noEmit   # typecheck
npx expo lint      # lint
npx expo-doctor    # check dependencies
```
