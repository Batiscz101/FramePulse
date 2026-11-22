import { CloudOff } from 'lucide-react-native';
import { Text, View } from 'react-native';

import { formatSyncTime } from '@/lib/format';
import { useI18n } from '@/lib/i18n-context';
import { useTheme } from '@/lib/theme-context';
import { tabularNums } from '@/lib/theme';

type OfflineBadgeProps = {
  /** Epoch milliseconds of the cached data, or `null` when unknown. */
  lastSync: number | null;
};

/** Quiet pill shown only while the screen renders locally saved data. */
export function OfflineBadge({ lastSync }: OfflineBadgeProps) {
  const { t } = useI18n();
  const { colors } = useTheme();
  const syncedAt = lastSync !== null ? formatSyncTime(lastSync) : '';

  return (
    <View
      className="flex-row items-center gap-1.5 self-start rounded-full border border-hairline bg-surface px-2.5 py-1"
      accessible
      accessibilityLabel={`${t('offlineBadge')}. ${t('offlineHint')}${
        syncedAt ? ` ${t('offlineSynced', { time: syncedAt })}` : ''
      }`}
    >
      <CloudOff size={11} color={colors.muted} strokeWidth={2} />
      <Text className="text-[9px] font-medium uppercase tracking-[1.2px] text-muted">
        {t('offlineBadge')}
      </Text>
      {syncedAt ? (
        <Text className="text-[9px] text-faint" style={tabularNums}>
          {t('offlineSynced', { time: syncedAt })}
        </Text>
      ) : null}
    </View>
  );
}
