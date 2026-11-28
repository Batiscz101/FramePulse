import { Text, View } from 'react-native';
import { formatPercent, formatTempC } from '@/lib/session-display';
import { useI18n } from '@/lib/i18n-context';
import { tabularNums } from '@/lib/theme';
import type { GameSession } from '@/types/telemetry';
type StatRow = { label: string; value: string };
function TelemetryColumn({ title, rows }: { title: string; rows: StatRow[] }) {
  if (rows.length === 0) return null;
  return (
    <View className="flex-1 rounded-xl border border-hairline bg-surface/60 px-3 py-2.5">
      <Text className="text-[10px] font-semibold uppercase tracking-[1.2px] text-faint">{title}</Text>
      <View className="mt-2 gap-1.5">
        {rows.map((row) => (
          <View key={row.label} className="flex-row items-center justify-between gap-2">
            <Text className="text-[11px] text-muted" numberOfLines={1}>{row.label}</Text>
            <Text className="text-[12px] font-medium text-ink" style={tabularNums} numberOfLines={1}>{row.value}</Text>
          </View>
        ))}
      </View>
    </View>
  );
}
export function SessionTelemetry({ session }: { session: GameSession }) {
  const { t } = useI18n();
  const gpuRows: StatRow[] = [
    typeof session.gpuTempAvg === 'number' ? { label: t('telemetryGpuTempAvg'), value: formatTempC(session.gpuTempAvg) ?? '—' } : null,
    typeof session.gpuTempMax === 'number' ? { label: t('telemetryGpuTempMax'), value: formatTempC(session.gpuTempMax) ?? '—' } : null,
    typeof session.gpuLoadAvg === 'number' ? { label: t('telemetryGpuLoad'), value: formatPercent(session.gpuLoadAvg) ?? '—' } : null,
  ].filter((row): row is StatRow => row !== null);
  const cpuRows: StatRow[] = [
    typeof session.cpuTempAvg === 'number' ? { label: t('telemetryCpuTempAvg'), value: formatTempC(session.cpuTempAvg) ?? '—' } : null,
    typeof session.cpuTempMax === 'number' ? { label: t('telemetryCpuTempMax'), value: formatTempC(session.cpuTempMax) ?? '—' } : null,
    typeof session.cpuLoadAvg === 'number' ? { label: t('telemetryCpuLoad'), value: formatPercent(session.cpuLoadAvg) ?? '—' } : null,
  ].filter((row): row is StatRow => row !== null);
  if (gpuRows.length === 0 && cpuRows.length === 0) return null;
  return (
    <View className="mt-5 rounded-2xl border border-hairline bg-surface px-4 py-3">
      <Text className="text-[10px] font-medium uppercase tracking-[1.2px] text-faint">{t('telemetryTitle')}</Text>
      <View className="mt-3 flex-row gap-2.5">
        <TelemetryColumn title={t('legendGpu')} rows={gpuRows} />
        <TelemetryColumn title={t('legendCpu')} rows={cpuRows} />
      </View>
    </View>
  );
}
