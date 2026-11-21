import { Pressable, Text } from 'react-native';

import { formatShortDate, formatWeekday } from '@/lib/format';
import { useI18n } from '@/lib/i18n-context';
import { tabularNums } from '@/lib/theme';

type DayPillProps = {
  date: string;
  /** Shown instead of the weekday when several sessions share one day. */
  caption?: string;
  selected: boolean;
  onPress: () => void;
};

export function DayPill({ date, caption, selected, onPress }: DayPillProps) {
  const { language } = useI18n();

  return (
    <Pressable
      accessibilityRole="button"
      accessibilityState={{ selected }}
      accessibilityLabel={formatShortDate(date, language)}
      onPress={onPress}
      className={`items-center rounded-full border px-4 py-2 ${
        selected ? 'border-ink bg-ink' : 'border-hairline bg-surface'
      }`}
      style={({ pressed }) => ({ opacity: pressed ? 0.72 : 1 })}
    >
      <Text
        className={`text-[9px] font-medium uppercase tracking-[1.2px] ${
          selected ? 'text-on-ink-muted' : 'text-faint'
        }`}
        style={tabularNums}
      >
        {caption ?? formatWeekday(date, language)}
      </Text>
      <Text
        className={`mt-0.5 text-[13px] font-semibold ${selected ? 'text-canvas' : 'text-muted'}`}
        style={tabularNums}
      >
        {formatShortDate(date, language)}
      </Text>
    </Pressable>
  );
}
