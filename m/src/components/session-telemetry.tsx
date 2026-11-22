import { Text, View } from 'react-native';

import { formatPercent, formatTempC } from '@/lib/session-display';
import { useI18n } from '@/lib/i18n-context';
import { tabularNums } from '@/lib/theme';
import type { GameSession } from '@/types/telemetry';

type StatRow = { label: string; value: string };

/**
 * Clean hardware telemetry overview of the selected session: average and
 * maximum GPU temperature, average GPU load, and the CPU temperature and
 * load averages. Rows without stored data are omitted.
 */
export function SessionTelemetry({ session }: { session: GameSession }) {
  const { t } = useI18n();

  const rows: StatRow[] = [
    typeof session.gpuTempAvg === 'number'
      ? { label: t('telemetryGpuTempAvg'), value: formatTempC(session.gpuTempAvg) ?? '—' }
      : null,
    typeof session.gpuTempMax === 'number'
      ? { label: t('telemetryGpuTempMax'), value: formatTempC(session.gpuTempMax) ?? '—' }
      : null,
    typeof session.gpuLoadAvg === 'number'
      ? { label: t('telemetryGpuLoad'), value: formatPercent(session.gpuLoadAvg) ?? '—' }
      : null,
    typeof session.cpuTempAvg === 'number'
      ? { label: t('telemetryCpuTempAvg'), value: formatTempC(session.cpuTempAvg) ?? '—' }
      : null,
    typeof session.cpuLoadAvg === 'number'
      ? { label: t('telemetryCpuLoad'), value: formatPercent(session.cpuLoadAvg) ?? '—' }
      : null,
  ].filter((row): row is StatRow => row !== null);

  if (rows.length === 0) return null;

  return (
    <View className="mt-5 rounded-2xl border border-hairline bg-surface px-4 py-3">
      <Text className="text-[10px] font-medium uppercase tracking-[1.2px] text-faint">
        {t('telemetryTitle')}
      </Text>
      <View className="mt-3 flex-wrap gap-2">
        {rows.map((row) => (
          <Text key={row.label} className="text-[12px] font-medium text-muted" style={tabularNums}>
            {`${row.label}: ${row.value}`}
          </Text>
        ))}
      </View>
    </View>
  );
}
