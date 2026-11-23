import { useMemo } from 'react';
import { Text, useWindowDimensions, View } from 'react-native';
import { LineChart } from 'react-native-gifted-charts';

import { toClock } from '@/lib/format';
import { useI18n } from '@/lib/i18n-context';
import { formatPercent } from '@/lib/session-display';
import { tabularNums } from '@/lib/theme';
import { useTheme } from '@/lib/theme-context';
import type { FpsSample } from '@/types/telemetry';

type LoadChartProps = {
  samples: FpsSample[];
  /** Clock base: local minutes since midnight of the session start. */
  startMinutes?: number;
  height?: number;
};

/** Fixed y-axis range: 0–100 %. */
const AXIS_MIN = 0;
const AXIS_STEP = 10;
const AXIS_SECTIONS = 10;

/**
 * Minimalist GPU/CPU load curve (same style as TemperatureChart): a card with
 * a legend and a live-inspectable line chart with % on the y-axis. Renders
 * nothing when no sample carries a load (older sessions).
 */
export function LoadChart({ samples, startMinutes = 0, height = 160 }: LoadChartProps) {
  const { t } = useI18n();
  const { colors } = useTheme();
  const { width: windowWidth } = useWindowDimensions();

  const hasGpu = samples.some((sample) => typeof sample.gpuLoad === 'number');
  const hasCpu = samples.some((sample) => typeof sample.cpuLoad === 'number');

  const gpuData = useMemo(
    () => samples.map((sample) => ({ value: sample.gpuLoad as number | undefined })),
    [samples],
  );
  const cpuData = useMemo(
    () => samples.map((sample) => ({ value: sample.cpuLoad as number | undefined })),
    [samples],
  );

  if (!hasGpu && !hasCpu) return null;

  const chartWidth = Math.max(180, windowWidth - 104);

  const clockAt = (sample: FpsSample | undefined): string =>
    sample ? toClock(startMinutes + sample.offsetSeconds / 60) : '';

  const tooltipParts = (sample: FpsSample | undefined): string => {
    const parts: string[] = [];
    const gpu = formatPercent(sample?.gpuLoad ?? null);
    const cpu = formatPercent(sample?.cpuLoad ?? null);
    if (gpu) parts.push(t('legendGpu'), gpu);
    if (cpu) parts.push(t('legendCpu'), cpu);
    return parts.join(' · ');
  };

  return (
    <View className="rounded-2xl border border-hairline bg-surface px-4 pb-4 pt-4">
      <View className="flex-row items-center justify-between">
        <Text className="text-[13px] font-semibold text-ink">{t('loadChartTitle')}</Text>
        <View className="flex-row items-center gap-3">
          {hasGpu ? (
            <View className="flex-row items-center gap-1.5">
              <View className="h-1.5 w-1.5 rounded-full bg-accent" />
              <Text className="text-[10px] text-muted">{t('legendGpu')}</Text>
            </View>
          ) : null}
          {hasCpu ? (
            <View className="flex-row items-center gap-1.5">
              <View className="h-1.5 w-1.5 rounded-full bg-muted" />
              <Text className="text-[10px] text-muted">{t('legendCpu')}</Text>
            </View>
          ) : null}
        </View>
      </View>

      <View className="mt-4" style={{ marginLeft: -4 }}>
        <LineChart
          data={hasGpu ? gpuData : cpuData}
          data2={hasGpu && hasCpu ? cpuData : undefined}
          width={chartWidth}
          height={height}
          adjustToWidth
          initialSpacing={0}
          endSpacing={0}
          disableScroll
          curved
          curvature={0.15}
          thickness={2}
          color={hasGpu ? colors.accent : colors.muted}
          color2={hasGpu ? colors.muted : undefined}
          hideDataPoints
          hideDataPoints2
          yAxisOffset={AXIS_MIN}
          maxValue={AXIS_STEP * AXIS_SECTIONS}
          noOfSections={AXIS_SECTIONS}
          yAxisLabelWidth={32}
          yAxisLabelSuffix="%"
          roundToDigits={0}
          yAxisTextStyle={{
            color: colors.faint,
            fontSize: 9,
            ...tabularNums,
          }}
          yAxisColor="transparent"
          xAxisColor={colors.hairline}
          xAxisThickness={1}
          rulesColor={colors.grid}
          rulesThickness={1}
          showVerticalLines={false}
          pointerConfig={{
            activatePointersInstantlyOnTouch: true,
            showPointerStrip: true,
            pointerStripColor: colors.strip,
            pointerStripWidth: 1,
            pointerStripHeight: height,
            pointerColor: colors.ink,
            radius: 4,
            pointerLabelWidth: 130,
            pointerLabelHeight: 46,
            autoAdjustPointerLabelPosition: true,
            pointerLabelComponent: (_items: { value?: number }[], _secondary: unknown, index: number) => {
              const sample = samples[index];
              return (
                <View className="items-center rounded-lg border border-tooltip-border bg-tooltip px-2.5 py-1.5">
                  <Text className="text-[9px] font-medium uppercase tracking-[1px] text-faint">
                    {clockAt(sample) || '—'}
                  </Text>
                  <Text
                    className="mt-0.5 text-[13px] font-semibold text-ink"
                    style={tabularNums}
                  >
                    {tooltipParts(sample)}
                  </Text>
                </View>
              );
            },
          }}
        />
      </View>
    </View>
  );
}
