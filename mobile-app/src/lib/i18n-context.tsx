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

import {
  DEFAULT_LANGUAGE,
  isLanguage,
  translate,
  type Language,
  type TranslationKey,
  type TranslationParams,
} from '@/lib/i18n';

/** Persisted on the device so the choice survives app restarts. */
const STORAGE_KEY = 'framepulse.language';

type I18nValue = {
  language: Language;
  setLanguage: (next: Language) => void;
  toggleLanguage: () => void;
  t: (key: TranslationKey, params?: TranslationParams) => string;
};

const I18nContext = createContext<I18nValue | null>(null);

export function I18nProvider({ children }: { children: ReactNode }) {
  const [language, setLanguageState] = useState<Language>(DEFAULT_LANGUAGE);

  useEffect(() => {
    let active = true;

    AsyncStorage.getItem(STORAGE_KEY)
      .then((stored) => {
        if (active && isLanguage(stored)) setLanguageState(stored);
      })
      .catch(() => {
        // Storage unavailable – keep the default language.
      });

    return () => {
      active = false;
    };
  }, []);

  const setLanguage = useCallback((next: Language) => {
    setLanguageState(next);
    void AsyncStorage.setItem(STORAGE_KEY, next).catch(() => {
      // The switch still works for this run even if persisting fails.
    });
  }, []);

  const toggleLanguage = useCallback(() => {
    setLanguage(language === 'en' ? 'cs' : 'en');
  }, [language, setLanguage]);

  const value = useMemo<I18nValue>(
    () => ({
      language,
      setLanguage,
      toggleLanguage,
      t: (key, params) => translate(language, key, params),
    }),
    [language, setLanguage, toggleLanguage],
  );

  return <I18nContext.Provider value={value}>{children}</I18nContext.Provider>;
}

export function useI18n(): I18nValue {
  const value = useContext(I18nContext);

  if (!value) {
    throw new Error('useI18n must be used inside <I18nProvider>.');
  }

  return value;
}
