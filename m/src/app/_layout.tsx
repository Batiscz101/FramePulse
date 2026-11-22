import '../../global.css';

import { Stack } from 'expo-router';
import { StatusBar } from 'expo-status-bar';

import { I18nProvider } from '@/lib/i18n-context';
import { ThemeProvider, useTheme } from '@/lib/theme-context';

export default function RootLayout() {
  return (
    <ThemeProvider>
      <I18nProvider>
        <ThemedStack />
      </I18nProvider>
    </ThemeProvider>
  );
}

function ThemedStack() {
  const { mode, colors } = useTheme();

  return (
    <>
      <StatusBar style={mode === 'dark' ? 'light' : 'dark'} />
      <Stack
        screenOptions={{
          headerShown: false,
          contentStyle: { backgroundColor: colors.canvas },
          animation: 'slide_from_right',
        }}
      >
        <Stack.Screen name="index" />
        <Stack.Screen name="game/[id]" />
      </Stack>
    </>
  );
}
