import { useMemo } from 'react';
import { Text, useWindowDimensions, View } from 'react-native';
import { LineChart } from 'react-native-gifted-charts';

import { toClock } from '@/lib/format';
import { useI18n } from '@/lib/i18n-context';
import { tabularNums } from '@/lib/theme';
import { useTheme } from '@/lib/theme-context';
import type { FpsSample } from '@/types/telemetry';

type TemperatureChartProps = {
  samples: FpsSample[];
  /** Clock base: local minutes since midnight of the session start. */
  startMinutes?: number;
  height?: number;
};

type Axis = {
  min: number;
  step: number;
  sections: number;
};

/** Picks a readable axis range over the temperature values. */
function buildAxis(values: number[]): Axis {
  if (values.length === 0) {
    return { min: 0, step: 10, sections: 4 };
  }

  const rawMin = Math.min(...values);
  const rawMax = Math.max(...values);
  const span = Math.max(rawMax - rawMin, 1);

  const roughStep = span / 3;
  const magnitude = 10 ** Math.floor(Math.log10(roughStep));
  const normalized = roughStep / magnitude;
  const nice = [1, 2, 2.5, 5, 10].find((candidate) => normalized <= candidate) ?? 10;
  const step = Math.max(1, nice * magnitude);

  const min = Math.max(0, Math.floor((rawMin - step * 0.5) / step) * step);
  const sections = Math.max(3, Math.ceil((rawMax - min) / step));

  return { min, step, sections };
}

function formatTemp(value: number | null): string | null {
  return value === null ? null : `${Math.round(value)}°C`;
}

/**
 * Minimalist GPU/CPU temperature curve (same style as FpsChart): a card with
 * a legend and a live-inspectable line chart with °C on the y-axis. Renders
 * nothing when no sample carries a temperature (older sessions).
 */
export function TemperatureChart({ samples, startMinutes = 0, height = 160 }: TemperatureChartProps) {
  const { t } = useI18n();
  const { colors } = useTheme();
  const { width: windowWidth } = useWindowDimensions();

  const hasGpu = samples.some((sample) => typeof sample.gpuTemp === 'number');
  const hasCpu = samples.some((sample) => typeof sample.cpuTemp === 'number');

  const axis = useMemo(() => {
    const values: number[] = [];
    for (const sample of samples) {
      if (typeof sample.gpuTemp === 'number') values.push(sample.gpuTemp);
      if (typeof sample.cpuTemp === 'number') values.push(sample.cpuTemp);
    }
    return buildAxis(values);
  }, [samples]);

  const gpuData = useMemo(
    () => samples.map((sample) => ({ value: sample.gpuTemp as number | undefined })),
    [samples],
  );
  const cpuData = useMemo(
    () => samples.map((sample) => ({ value: sample.cpuTemp as number | undefined })),
    [samples],
  );

  if (!hasGpu && !hasCpu) return null;

  const chartWidth = Math.max(180, windowWidth - 104);

  const clockAt = (sample: FpsSample | undefined): string =>
    sample ? toClock(startMinutes + sample.offsetSeconds / 60) : '';

  const tooltipParts = (sample: FpsSample | undefined): string =>
    [
      t('legendGpu'),
      formatTemp(sample?.gpuTemp ?? null),
      t('legendCpu'),
      formatTemp(sample?.cpuTemp ?? null),
    ]
      .filter((part): part is string => part !== null)
      .join(' · ');

  return (
    <View className="rounded-2xl border border-hairline bg-surface px-4 pb-4 pt-4">
      <View className="flex-row items-center justify-between">
        <Text className="text-[13px] font-semibold text-ink">{t('temperatureChartTitle')}</Text>
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
          yAxisOffset={axis.min}
          maxValue={Math.max(axis.step * axis.sections, 1)}
          noOfSections={axis.sections}
          yAxisLabelWidth={32}
          yAxisLabelSuffix="°C"
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
