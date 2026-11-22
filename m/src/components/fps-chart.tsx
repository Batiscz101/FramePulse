import { useMemo } from 'react';
import { Text, useWindowDimensions, View } from 'react-native';
import { LineChart } from 'react-native-gifted-charts';

import { formatTimeRange, toClock } from '@/lib/format';
import { useI18n } from '@/lib/i18n-context';
import { pointsCount } from '@/lib/i18n';
import { tabularNums } from '@/lib/theme';
import { useTheme } from '@/lib/theme-context';
import { durationMinutes, type FpsSample, type GameSession } from '@/types/telemetry';

type FpsChartProps = {
  session: GameSession;
  samples: FpsSample[];
};

type Axis = {
  min: number;
  step: number;
  sections: number;
};

/** Picks a readable axis range that starts just below the session minimum. */
function buildAxis(samples: FpsSample[]): Axis {
  if (samples.length === 0) {
    return { min: 0, step: 30, sections: 4 };
  }

  const values = samples.map((sample) => sample.fps);
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

export function FpsChart({ session, samples }: FpsChartProps) {
  const { language, t } = useI18n();
  const { colors } = useTheme();
  const { width: windowWidth } = useWindowDimensions();

  const axis = useMemo(() => buildAxis(samples), [samples]);
  const data = useMemo(() => samples.map((sample) => ({ value: sample.fps })), [samples]);

  // Page padding (20 × 2) + card padding (16 × 2) + y-axis labels (32).
  const chartWidth = Math.max(180, windowWidth - 104);

  const midSample = samples[Math.floor(samples.length / 2)];
  const endSample = samples[samples.length - 1];

  const clockAt = (sample: FpsSample | undefined): string =>
    sample ? toClock(session.startMinutes + sample.offsetSeconds / 60) : '';

  return (
    <View className="rounded-2xl border border-hairline bg-surface px-4 pb-4 pt-4">
      <View className="flex-row items-center justify-between">
        <Text className="text-[13px] font-semibold text-ink">{t('chartTitle')}</Text>
        <Text className="text-[11px] text-faint">{t('chartHint')}</Text>
      </View>

      <View className="mt-4" style={{ marginLeft: -4 }}>
        <LineChart
          data={data}
          width={chartWidth}
          height={168}
          adjustToWidth
          initialSpacing={0}
          endSpacing={0}
          disableScroll
          curved
          curvature={0.15}
          thickness={2}
          color={colors.accent}
          hideDataPoints
          areaChart
          startFillColor={colors.accent}
          endFillColor={colors.accent}
          startOpacity={0.2}
          endOpacity={0}
          yAxisOffset={axis.min}
          maxValue={axis.step * axis.sections}
          noOfSections={axis.sections}
          yAxisLabelWidth={32}
          yAxisLabelSuffix=""
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
            pointerStripHeight: 168,
            pointerColor: colors.ink,
            radius: 4,
            pointerLabelWidth: 92,
            pointerLabelHeight: 46,
            autoAdjustPointerLabelPosition: true,
            pointerLabelComponent: (
              items: { value?: number }[],
              _secondary: unknown,
              index: number,
            ) => {
              const sample = samples[index];
              const fps = items?.[0]?.value ?? sample?.fps ?? 0;
              return (
                <View className="items-center rounded-lg border border-tooltip-border bg-tooltip px-2.5 py-1.5">
                  <Text className="text-[9px] font-medium uppercase tracking-[1px] text-faint">
                    {clockAt(sample) || '—'}
                  </Text>
                  <Text
                    className="mt-0.5 text-[13px] font-semibold text-ink"
                    style={tabularNums}
                  >
                    {Math.round(fps)} FPS
                  </Text>
                </View>
              );
            },
          }}
        />
      </View>

      <View className="mt-2 flex-row items-center justify-between pl-8">
        <Text className="text-[9px] text-faint" style={tabularNums}>
          {toClock(session.startMinutes)}
        </Text>
        <Text className="text-[9px] text-faint" style={tabularNums}>
          {clockAt(midSample)}
        </Text>
        <Text className="text-[9px] text-faint" style={tabularNums}>
          {clockAt(endSample)}
        </Text>
      </View>

      <View className="mt-3 flex-row items-center justify-between border-t border-hairline pt-3">
        <View className="flex-row items-center gap-1.5">
          <View className="h-1.5 w-1.5 rounded-full bg-accent" />
          <Text className="text-[10px] text-muted">FPS</Text>
        </View>
        <Text className="text-[10px] text-faint" style={tabularNums}>
          {formatTimeRange(session.startedAt, durationMinutes(session))} ·{' '}
          {pointsCount(language, samples.length)}
        </Text>
      </View>
    </View>
  );
}
