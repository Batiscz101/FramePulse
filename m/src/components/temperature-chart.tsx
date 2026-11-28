import { memo, useMemo, useState } from 'react';
import { Text, useWindowDimensions, View } from 'react-native';
import { LineChart } from 'react-native-gifted-charts';

import { filterSamples } from '@/lib/chart-data';
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

const CARD_HORIZONTAL_CHROME = 34; // px-4 (16 * 2) + 1px border on each side
const Y_AXIS_LABEL_WIDTH = 32;

/**
 * Minimalist GPU/CPU temperature curve (same style as FpsChart): a card with
 * a legend and a live-inspectable line chart with °C on the y-axis. Renders
 * nothing when no sample carries a temperature (older sessions).
 */
export const TemperatureChart = memo(function TemperatureChart({
  samples,
  startMinutes = 0,
  height = 160,
}: TemperatureChartProps) {
  const { t } = useI18n();
  const { colors } = useTheme();
  const { width: windowWidth } = useWindowDimensions();
  const [cardWidth, setCardWidth] = useState<number | null>(null);

  // Null-safe: only points with a temperature reach the chart.
  const gpuPoints = useMemo(() => filterSamples(samples, 'gpuTemp'), [samples]);
  const cpuPoints = useMemo(() => filterSamples(samples, 'cpuTemp'), [samples]);
  const hasGpu = gpuPoints.length > 0;
  const hasCpu = cpuPoints.length > 0;

  const axis = useMemo(() => {
    const values: number[] = [];
    for (const point of samples) {
      if (typeof point.gpuTemp === 'number') values.push(point.gpuTemp);
      if (typeof point.cpuTemp === 'number') values.push(point.cpuTemp);
    }
    return buildAxis(values);
  }, [samples]);

  const gpuData = useMemo(
    () => gpuPoints.map((point) => ({ value: point.gpuTemp ?? undefined })),
    [gpuPoints],
  );
  const cpuData = useMemo(
    () => cpuPoints.map((point) => ({ value: point.cpuTemp ?? undefined })),
    [cpuPoints],
  );
  const chartPoints = hasGpu ? gpuPoints : cpuPoints;
  const primaryData = hasGpu ? gpuData : cpuData;
  const secondaryData = hasGpu && hasCpu ? cpuData : undefined;
  const maxPoints = Math.max(primaryData.length, secondaryData?.length ?? 0);

  if (!hasGpu && !hasCpu) return null;

  const innerWidth = Math.max(
    140,
    (cardWidth ?? Math.max(180, windowWidth - 40)) - CARD_HORIZONTAL_CHROME,
  );
  const chartWidth = Math.max(100, innerWidth - Y_AXIS_LABEL_WIDTH);
  const pointSpacing =
    secondaryData && primaryData.length !== secondaryData.length
      ? chartWidth / Math.max(maxPoints - 1, 1)
      : undefined;

  const clockAt = (sample: FpsSample | undefined): string =>
    sample ? toClock(startMinutes + sample.offsetSeconds / 60) : '';

  const tooltipParts = (sample: FpsSample | undefined): string => {
    const parts: string[] = [];
    const gpu = formatTemp(sample?.gpuTemp ?? null);
    const cpu = formatTemp(sample?.cpuTemp ?? null);
    if (gpu) parts.push(`${t('legendGpu')} ${gpu}`);
    if (cpu) parts.push(`${t('legendCpu')} ${cpu}`);
    return parts.join(' · ');
  };

  return (
    <View
      onLayout={(event) => {
        const nextWidth = Math.floor(event.nativeEvent.layout.width);
        if (nextWidth > 0 && nextWidth !== cardWidth) {
          setCardWidth(nextWidth);
        }
      }}
      className="mt-3.5 rounded-2xl border border-hairline bg-surface px-4 pb-4 pt-4"
    >
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

      <View className="mt-4" style={{ width: innerWidth, overflow: 'hidden' }}>
        <LineChart
          data={primaryData}
          data2={secondaryData}
          parentWidth={innerWidth}
          width={chartWidth}
          height={height}
          adjustToWidth={pointSpacing === undefined}
          spacing={pointSpacing}
          initialSpacing={0}
          endSpacing={0}
          disableScroll
          curved
          curvature={0.15}
          thickness={2}
          color={hasGpu ? colors.accent : colors.muted}
          color2={hasGpu ? colors.muted : undefined}
          hideDataPoints={primaryData.length > 1}
          hideDataPoints2={(secondaryData?.length ?? 0) > 1}
          dataPointsRadius={3}
          dataPointsColor={hasGpu ? colors.accent : colors.muted}
          dataPointsColor2={hasGpu ? colors.muted : undefined}
          yAxisOffset={axis.min}
          maxValue={Math.max(axis.step * axis.sections, 1)}
          noOfSections={axis.sections}
          yAxisLabelWidth={Y_AXIS_LABEL_WIDTH}
          yAxisThickness={0}
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
              const sample = chartPoints[index];
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
});
