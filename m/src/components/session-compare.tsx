import { useEffect, useState } from 'react';
import { Modal, Pressable, ScrollView, Text, View } from 'react-native';
import { X } from 'lucide-react-native';

import { type Language, type TranslationKey } from '@/lib/i18n';
import { useI18n } from '@/lib/i18n-context';
import { formatFps, formatShortDate } from '@/lib/format';
import { getCachedSamples } from '@/hooks/use-session-samples';
import { fetchSessionSamples } from '@/lib/telemetry-api';
import {
  formatDisplayMode,
  formatGraphicsApi,
  formatPercent,
  formatResolution,
  formatTempC,
  gameSettingRows,
} from '@/lib/session-display';
import { computeSessionStats, diffColor, formatDiff, type SessionStats } from '@/lib/session-stats';
import { tabularNums, type ThemePalette } from '@/lib/theme';
import { useTheme } from '@/lib/theme-context';
import type { FpsSample, Game, GameSession } from '@/types/telemetry';

type Props = { game: Game; onClose: () => void };

type T = (key: TranslationKey) => string;

type CompareMetricRow = { label: string; a: string | null; b: string | null; diff: string | null; color: string | null };
type SettingsRowData = { label: string; a: string | null; b: string | null };

function CompareRow({ label, a, b, diff, color }: CompareMetricRow) {
  return (
    <View className="flex-row items-baseline gap-2 py-1">
      <View className="w-[100px]">
        <Text className="text-[11px] text-muted" style={tabularNums} numberOfLines={1}>
          {label}
        </Text>
      </View>
      <Text className="text-[12px] text-ink" style={tabularNums} numberOfLines={1}>
        {a ?? '—'}
      </Text>
      <Text className="w-[52px] text-right text-[12px] text-ink" style={tabularNums} numberOfLines={1}>
        {b ?? '—'}
      </Text>
      {diff !== null ? (
        <Text
          className="w-[72px] text-right text-[11px] font-semibold"
          style={color ? [tabularNums, { color }] : tabularNums}
          numberOfLines={1}
        >
          {diff}
        </Text>
      ) : null}
    </View>
  );
}

function SettingsRow({ label, a, b }: SettingsRowData) {
  return (
    <View className="flex-row items-baseline gap-2 py-1">
      <View className="w-[100px]">
        <Text className="text-[11px] text-muted">{label}</Text>
      </View>
      <Text className="flex-1 text-[12px] text-ink" numberOfLines={1}>
        {a ?? '—'}
      </Text>
      <Text className="w-[52px] text-right text-[12px] text-ink" numberOfLines={1}>
        {b ?? '—'}
      </Text>
    </View>
  );
}

function SessionRow({
  session,
  selectedA,
  selectedB,
  colors,
  onPress,
}: {
  session: GameSession;
  selectedA: boolean;
  selectedB: boolean;
  colors: ThemePalette;
  onPress: () => void;
}) {
  const { language } = useI18n();

  return (
    <Pressable
      onPress={onPress}
      accessibilityRole="button"
      className="mt-2 flex-row items-center gap-3 rounded-xl border border-hairline bg-surface px-4 py-3"
      style={selectedA || selectedB ? { borderColor: colors.accent } : undefined}
    >
      <View className="w-4 items-center justify-center">
        <Text
          className="text-[11px] font-bold"
          style={{ color: selectedA ? colors.accent : 'transparent' }}
        >
          A
        </Text>
        <Text
          className="text-[11px] font-bold"
          style={{ color: selectedB ? colors.danger : 'transparent' }}
        >
          B
        </Text>
      </View>
      <View className="flex-1">
        <Text className="text-[13px] font-semibold text-ink" numberOfLines={1}>
          {formatShortDate(session.date, language)}
          {session.startedAt ? ` · ${session.startedAt}` : ''}
        </Text>
        <Text className="mt-0.5 text-[11px] text-muted" style={tabularNums} numberOfLines={1}>
          {formatFps(session.avgFps, language)} FPS
        </Text>
      </View>
    </Pressable>
  );
}

function buildMetricsRows(
  t: T,
  colors: ThemePalette,
  language: Language,
  statsA: SessionStats,
  statsB: SessionStats,
): CompareMetricRow[] {
  const rows: CompareMetricRow[] = [];

  const add = (
    label: string,
    a: number | null,
    b: number | null,
    options: {
      percent?: boolean;
      unit?: string;
      better: 'up' | 'down';
      format: (value: number) => string;
    },
  ) => {
    const diff =
      a !== null && b !== null
        ? formatDiff(a, b, { percent: options.percent, unit: options.unit })
        : null;
    rows.push({
      label,
      a: a !== null ? options.format(a) : null,
      b: b !== null ? options.format(b) : null,
      diff,
      color:
        diff !== null && a !== null && b !== null
          ? diffColor(a, b, options.better, colors)
          : null,
    });
  };

  const fps = (value: number) => formatFps(value, language);
  const safeTemp = (value: number) => formatTempC(value) ?? '—';
  const safePercent = (value: number) => formatPercent(value) ?? '—';

  add(t('compareAvgFps'), statsA.avgFps, statsB.avgFps, {
    percent: true,
    better: 'up',
    format: fps,
  });
  add(t('compareLow1'), statsA.low1, statsB.low1, {
    percent: true,
    better: 'up',
    format: fps,
  });
  add(t('compareLow01'), statsA.low01, statsB.low01, {
    percent: true,
    better: 'up',
    format: fps,
  });
  add(t('compareFrameTime'), statsA.frameTimeMs, statsB.frameTimeMs, {
    unit: 'ms',
    better: 'down',
    format: (value) => `${value.toFixed(1)}`,
  });
  add(t('compareGpuTempAvg'), statsA.gpuTempAvg, statsB.gpuTempAvg, {
    unit: '°C',
    better: 'down',
    format: safeTemp,
  });
  add(t('compareGpuTempMax'), statsA.gpuTempMax, statsB.gpuTempMax, {
    unit: '°C',
    better: 'down',
    format: safeTemp,
  });
  add(t('compareGpuLoad'), statsA.gpuLoadAvg, statsB.gpuLoadAvg, {
    unit: '%',
    better: 'up',
    format: safePercent,
  });
  add(t('compareCpuTemp'), statsA.cpuTempAvg, statsB.cpuTempAvg, {
    unit: '°C',
    better: 'down',
    format: safeTemp,
  });
  add(t('compareCpuLoad'), statsA.cpuLoadAvg, statsB.cpuLoadAvg, {
    unit: '%',
    better: 'up',
    format: safePercent,
  });

  return rows;
}

function buildSettingsRows(
  t: T,
  sessionA: GameSession,
  sessionB: GameSession,
): SettingsRowData[] {
  const settingsA = gameSettingRows(sessionA);
  const settingsB = gameSettingRows(sessionB);

  const rows: SettingsRowData[] = [
    { label: t('badgeResolution'), a: formatResolution(sessionA.resolution), b: formatResolution(sessionB.resolution) },
    { label: t('badgeDisplayMode'), a: formatDisplayMode(sessionA.displayMode), b: formatDisplayMode(sessionB.displayMode) },
    { label: t('badgeGraphicsApi'), a: formatGraphicsApi(sessionA.graphicsApi), b: formatGraphicsApi(sessionB.graphicsApi) },
  ];

  const labelKeys = [...new Set([...settingsA, ...settingsB].map((row) => row.labelKey))];
  for (const labelKey of labelKeys) {
    const rowA = settingsA.find((row) => row.labelKey === labelKey);
    const rowB = settingsB.find((row) => row.labelKey === labelKey);
    rows.push({ label: t(labelKey), a: rowA?.value ?? null, b: rowB?.value ?? null });
  }

  rows.push({ label: t('noteLabel'), a: sessionA.note ?? null, b: sessionB.note ?? null });

  return rows;
}

/**
 * "Relace A vs. Relace B" comparison: two sessions can be selected from the
 * list; once both are chosen the metrics of A and B (with colored diffs) and
 * the compared settings are shown side by side.
 */
export function SessionCompareModal({ game, onClose }: Props) {
  const { language, t } = useI18n();
  const { colors } = useTheme();
  const [selectedA, setSelectedA] = useState<string | null>(null);
  const [selectedB, setSelectedB] = useState<string | null>(null);
  const [samplesAState, setSamplesA] = useState<FpsSample[] | null>(null);
  const [samplesBState, setSamplesB] = useState<FpsSample[] | null>(null);

  const sessionA = game.sessions.find((item) => item.id === selectedA) ?? null;
  const sessionB = game.sessions.find((item) => item.id === selectedB) ?? null;
  const comparing = sessionA !== null && sessionB !== null;

  // Sessions already viewed on this screen appear instantly (no chart flash).
  const samplesA = samplesAState ?? (sessionA ? getCachedSamples(sessionA.id) : null);
  const samplesB = samplesBState ?? (sessionB ? getCachedSamples(sessionB.id) : null);

  useEffect(() => {
    if (!comparing) return;

    let active = true;
    const load = async () => {
      try {
        const [nextA, nextB] = await Promise.all([
          fetchSessionSamples(sessionA.id),
          fetchSessionSamples(sessionB.id),
        ]);
        if (!active) return;
        setSamplesA(nextA);
        setSamplesB(nextB);
      } catch {
        if (!active) return;
        setSamplesA((current) => current ?? []);
        setSamplesB((current) => current ?? []);
      }
    };
    void load();

    return () => {
      active = false;
    };
  }, [comparing, sessionA?.id, sessionB?.id]);

  const toggle = (session: GameSession) => {
    if (session.id === selectedA) {
      setSelectedA(null);
      return;
    }
    if (session.id === selectedB) {
      setSelectedB(null);
      return;
    }
    if (selectedA === null) {
      setSelectedA(session.id);
      return;
    }
    if (selectedB === null) {
      setSelectedB(session.id);
    }
  };

  const statsA = sessionA ? computeSessionStats(sessionA, samplesA) : null;
  const statsB = sessionB ? computeSessionStats(sessionB, samplesB) : null;
  const metrics =
    comparing && statsA && statsB ? buildMetricsRows(t, colors, language, statsA, statsB) : [];
  const settingsRows = comparing ? buildSettingsRows(t, sessionA, sessionB) : [];

  return (
    <Modal visible transparent animationType="fade" statusBarTranslucent onRequestClose={onClose}>
      <Pressable
        className="absolute inset-0"
        onPress={onClose}
        accessibilityRole="button"
        accessibilityLabel={t('close')}
      />

      <View className="flex-1 justify-center px-5">
        <ScrollView
          className="rounded-3xl border border-hairline bg-surface p-5"
          showsVerticalScrollIndicator={false}
        >
          <View className="flex-row items-center justify-between">
            <Text className="text-[16px] font-semibold text-ink">{t('compareSessions')}</Text>
            <Pressable
              onPress={onClose}
              accessibilityRole="button"
              accessibilityLabel={t('compareClose')}
            >
              <X size={18} color={colors.muted} strokeWidth={2} />
            </Pressable>
          </View>

          {comparing && sessionA && sessionB ? (
            <>
              <Text className="mt-1 text-[12px] font-semibold text-ink">{t('compareTitle')}</Text>
              <Text className="mt-1 text-[11px] text-muted">
                {formatShortDate(sessionA.date, language)} ·{' '}
                {formatShortDate(sessionB.date, language)}
              </Text>

              <View className="mt-4">
                {metrics.map((row) => (
                  <CompareRow key={row.label} {...row} />
                ))}
              </View>

              <View className="mt-6 rounded-2xl border border-hairline bg-raised p-4">
                <Text className="text-[10px] font-medium uppercase tracking-[1.2px] text-faint">
                  {t('compareSettings')}
                </Text>
                {settingsRows.map((row) => <SettingsRow key={row.label} {...row} />)}
              </View>
            </>
          ) : (
            <>
              <Text className="mt-2 text-[11px] text-muted">
                {t('comparePickA')} · {t('comparePickB')}
              </Text>
              {game.sessions.map((session) => (
                <SessionRow
                  key={session.id}
                  session={session}
                  selectedA={selectedA === session.id}
                  selectedB={selectedB === session.id}
                  colors={colors}
                  onPress={() => toggle(session)}
                />
              ))}
            </>
          )}
        </ScrollView>
      </View>
    </Modal>
  );
}
