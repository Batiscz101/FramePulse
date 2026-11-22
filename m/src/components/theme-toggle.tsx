import { Moon, Sun } from 'lucide-react-native';
import { Pressable } from 'react-native';

import { useI18n } from '@/lib/i18n-context';
import { useTheme } from '@/lib/theme-context';

/** Minimal sun/moon button next to the language switch. */
export function ThemeToggle() {
  const { mode, colors, toggleTheme } = useTheme();
  const { t } = useI18n();

  // The icon shows the theme the tap will switch to.
  const Icon = mode === 'dark' ? Sun : Moon;

  return (
    <Pressable
      onPress={toggleTheme}
      hitSlop={8}
      accessibilityRole="button"
      accessibilityLabel={t('themeToggle')}
      accessibilityValue={{ text: mode === 'dark' ? t('themeDark') : t('themeLight') }}
      className="h-9 w-9 items-center justify-center rounded-full border border-hairline bg-surface"
      style={({ pressed }) => ({ opacity: pressed ? 0.7 : 1 })}
    >
      <Icon size={16} color={colors.muted} strokeWidth={2} />
    </Pressable>
  );
}
