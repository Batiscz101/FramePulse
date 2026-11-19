import { Pressable, Text } from 'react-native';

import { useI18n } from '@/lib/i18n-context';

/** Minimal `EN / CZ` pill – one tap flips the whole app. */
export function LanguageToggle() {
  const { language, toggleLanguage, t } = useI18n();

  const codeClass = (code: 'en' | 'cs') =>
    `text-[10px] font-semibold tracking-[1px] ${
      language === code ? 'text-ink' : 'text-faint'
    }`;

  return (
    <Pressable
      onPress={toggleLanguage}
      hitSlop={8}
      accessibilityRole="button"
      accessibilityLabel={t('languageToggle')}
      accessibilityValue={{ text: language.toUpperCase() }}
      className="h-9 flex-row items-center rounded-full border border-hairline bg-surface px-3"
      style={({ pressed }) => ({ opacity: pressed ? 0.7 : 1 })}
    >
      <Text className={codeClass('en')}>EN</Text>
      <Text className="mx-1.5 text-[10px] text-faint">/</Text>
      <Text className={codeClass('cs')}>CZ</Text>
    </Pressable>
  );
}
