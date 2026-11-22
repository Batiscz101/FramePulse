import AsyncStorage from '@react-native-async-storage/async-storage';
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from 'react';
import { View } from 'react-native';

import {
  DEFAULT_THEME_MODE,
  isThemeMode,
  palettes,
  themeVariables,
  type ThemeMode,
  type ThemePalette,
} from '@/lib/theme';

/** Persisted on the device so the choice survives app restarts. */
const STORAGE_KEY = 'framepulse.theme';

type ThemeValue = {
  mode: ThemeMode;
  colors: ThemePalette;
  setMode: (next: ThemeMode) => void;
  toggleTheme: () => void;
};

const ThemeContext = createContext<ThemeValue | null>(null);

export function ThemeProvider({ children }: { children: ReactNode }) {
  const [mode, setModeState] = useState<ThemeMode>(DEFAULT_THEME_MODE);

  useEffect(() => {
    let active = true;

    AsyncStorage.getItem(STORAGE_KEY)
      .then((stored) => {
        if (active && isThemeMode(stored)) setModeState(stored);
      })
      .catch(() => {
        // Storage unavailable – keep the dark default.
      });

    return () => {
      active = false;
    };
  }, []);

  const setMode = useCallback((next: ThemeMode) => {
    setModeState(next);
    void AsyncStorage.setItem(STORAGE_KEY, next).catch(() => {
      // The switch still works for this run even if persisting fails.
    });
  }, []);

  const toggleTheme = useCallback(() => {
    setMode(mode === 'dark' ? 'light' : 'dark');
  }, [mode, setMode]);

  const variables = useMemo(() => themeVariables(mode), [mode]);

  const value = useMemo<ThemeValue>(
    () => ({ mode, colors: palettes[mode], setMode, toggleTheme }),
    [mode, setMode, toggleTheme],
  );

  return (
    <ThemeContext.Provider value={value}>
      {/* Defines the --color-* variables for every descendant screen. */}
      <View style={variables} className="flex-1 bg-canvas">
        {children}
      </View>
    </ThemeContext.Provider>
  );
}

export function useTheme(): ThemeValue {
  const value = useContext(ThemeContext);

  if (!value) {
    throw new Error('useTheme must be used inside <ThemeProvider>.');
  }

  return value;
}
