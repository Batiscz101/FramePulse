import { ScrollView, Text, View } from 'react-native';

import { useI18n } from '@/lib/i18n-context';
import {
  formatDisplayMode,
  formatGraphicsApi,
  formatResolution,
  gameSettingRows,
  type GameSettingRow,
} from '@/lib/session-display';
import { tabularNums } from '@/lib/theme';
import type { GameSession } from '@/types/telemetry';

type BadgeRow = { label: string; value: string };

function Badge({ label, value }: BadgeRow) {
  return (
    <View className="flex-row items-baseline gap-1.5 rounded-full border border-hairline bg-raised px-3 py-1.5">
      <Text className="text-[9px] font-medium uppercase tracking-[1px] text-muted">{label}</Text>
      <Text className="text-[12px] font-semibold text-ink" style={tabularNums}>
        {value}
      </Text>
    </View>
  );
}

/**
 * Minimalist settings badges of the selected session: resolution, window
 * mode, graphics API and the key graphics settings from the game config.
 */
export function SessionInfoBadges({ session }: { session: GameSession }) {
  const { t } = useI18n();

  const settingRows = gameSettingRows(session).filter(
    (row): row is { labelKey: GameSettingRow['labelKey']; value: string } => row.value !== null,
  );

  const rows: BadgeRow[] = [
    { label: t('badgeResolution'), value: formatResolution(session.resolution) ?? '—' },
    { label: t('badgeDisplayMode'), value: formatDisplayMode(session.displayMode) ?? '—' },
    { label: t('badgeGraphicsApi'), value: formatGraphicsApi(session.graphicsApi) ?? '—' },
    ...settingRows.map((row) => ({ label: t(row.labelKey), value: row.value })),
  ];

  if (rows.length === 0) return null;

  return (
    <View className="mt-5">
      <ScrollView
        horizontal
        showsHorizontalScrollIndicator={false}
        contentContainerStyle={{ gap: 8, paddingRight: 4 }}
        className="mt-3"
      >
        {rows.map((row) => (
          <Badge key={`${row.label}:${row.value}`} label={row.label} value={row.value} />
        ))}
      </ScrollView>
    </View>
  );
}
