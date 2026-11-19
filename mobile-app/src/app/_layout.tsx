import '../../global.css';

import { Stack } from 'expo-router';
import { StatusBar } from 'expo-status-bar';

import { I18nProvider } from '@/lib/i18n-context';
import { palette } from '@/lib/theme';

export default function RootLayout() {
  return (
    <I18nProvider>
      <StatusBar style="light" />
      <Stack
        screenOptions={{
          headerShown: false,
          contentStyle: { backgroundColor: palette.canvas },
          animation: 'slide_from_right',
        }}
      >
        <Stack.Screen name="index" />
        <Stack.Screen name="game/[id]" />
      </Stack>
    </I18nProvider>
  );
}
