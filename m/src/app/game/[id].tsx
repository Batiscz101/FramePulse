import { useCallback, useMemo, useState } from 'react';
import { useLocalSearchParams, router } from 'expo-router';
import { ChevronLeft, Pencil } from 'lucide-react-native';
import {
  ActivityIndicator,
  Pressable,
  RefreshControl,
  ScrollView,
  Text,
  View,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import { DayPill } from '@/components/day-pill';
import { FpsChart } from '@/components/fps-chart';
import { GameFormModal } from '@/components/game-form-modal';
import { OfflineBadge } from '@/components/offline-badge';
import { SessionCompareModal } from '@/components/session-compare';
import { SessionInfoBadges } from '@/components/session-info-badges';
import { SessionNoteEditor } from '@/components/session-note-editor';
import { SessionTelemetry } from '@/components/session-telemetry';
import { TemperatureChart } from '@/components/temperature-chart';
import { useGame } from '@/hooks/use-game';
import { useSessionSamples } from '@/hooks/use-session-samples';
import {
  formatDuration,
  formatFps,
  formatSignedFps,
  formatTimeRange,
  formatLongDate,
} from '@/lib/format';
import { daysCount, sessionsCount } from '@/lib/i18n';
import { useI18n } from '@/lib/i18n-context';
import { tabularNums } from '@/lib/theme';
import { useTheme } from '@/lib/theme-context';
import { durationMinutes } from '@/types/telemetry';

function Metric({ label, value }: { label: string; value: number }) {
  const { language } = useI18n();

  return (
    <View>
      <Text className="text-[9px] font-medium uppercase tracking-[1.2px] text-faint">
        {label}
      </Text>
      <View className="mt-1 flex-row items-baseline gap-1">
        <Text className="text-[19px] font-semibold leading-6 text-ink" style={tabularNums}>
          {formatFps(value, language)}
        </Text>
        <Text className="text-[9px] font-medium text-faint">FPS</Text>
      </View>
    </View>
  );
}

export default function GameDetailScreen() {
  const params = useLocalSearchParams<{ id: string }>();
  const gameId = Array.isArray(params.id) ? params.id[0] : params.id;

  const { language, t } = useI18n();
  const { colors } = useTheme();
  const {
    game,
    state,
    error,
    reload,
    rename,
    offline: gameOffline,
    lastSync: gameSyncedAt,
  } = useGame(gameId);
  const [selectedSessionId, setSelectedSessionId] = useState<string | null>(null);
  const [renameVisible, setRenameVisible] = useState(false);
  const [compareVisible, setCompareVisible] = useState(false);
  const [noteVisible, setNoteVisible] = useState(false);
  const [refreshing, setRefreshing] = useState(false);

  const sessions = useMemo(() => game?.sessions ?? [], [game]);

  const session = useMemo(
    () => sessions.find((item) => item.id === selectedSessionId) ?? sessions[0],
    [sessions, selectedSessionId],
  );

  const {
    samples,
    state: samplesState,
    error: samplesError,
    offline: samplesOffline,
    lastSync: samplesSyncedAt,
    reload: reloadSamples,
  } = useSessionSamples(session?.id);

  const refreshAll = useCallback(async () => {
    setRefreshing(true);
    reloadSamples();
    try {
      await reload();
    } finally {
      setRefreshing(false);
    }
  }, [reload, reloadSamples]);

  const olderSession = useMemo(() => {
    if (!session) return undefined;
    const index = sessions.findIndex((item) => item.id === session.id);
    return index >= 0 ? sessions[index + 1] : undefined;
  }, [sessions, session]);

  // Several sessions can happen on one day – show the start time so the pills
  // stay distinguishable.
  const sessionsPerDate = useMemo(() => {
    const counts = new Map<string, number>();
    for (const item of sessions) {
      counts.set(item.date, (counts.get(item.date) ?? 0) + 1);
    }
    return counts;
  }, [sessions]);

  const goBack = () => {
    if (router.canGoBack()) {
      router.back();
    } else {
      router.replace('/');
    }
  };

  const offline = gameOffline || samplesOffline;
  const lastSync = gameSyncedAt ?? samplesSyncedAt;

  if (state === 'loading' && !game) {
    return (
      <SafeAreaView edges={['top']} className="flex-1 bg-canvas">
        <View className="flex-1 items-center justify-center">
          <ActivityIndicator color={colors.muted} />
          <Text className="mt-3 text-[12px] text-muted">{t('loadingGame')}</Text>
        </View>
      </SafeAreaView>
    );
  }

  if (!game) {
    return (
      <SafeAreaView edges={['top']} className="flex-1 bg-canvas">
        <View className="flex-1 items-center justify-center px-6">
          <Text className="text-[15px] font-semibold text-ink">{t('gameNotFound')}</Text>
          <Text className="mt-1 text-center text-[12px] text-muted">
            {error ?? t('gameNotFoundBody')}
          </Text>
          <View className="mt-5 flex-row items-center gap-2.5">
            <Pressable
              onPress={reload}
              accessibilityRole="button"
              accessibilityLabel={t('retry')}
              className="rounded-full border border-hairline bg-raised px-4 py-2"
              style={({ pressed }) => ({ opacity: pressed ? 0.7 : 1 })}
            >
              <Text className="text-[12px] font-medium text-ink">{t('retry')}</Text>
            </Pressable>
            <Pressable
              onPress={goBack}
              accessibilityRole="button"
              accessibilityLabel={t('backToList')}
              className="rounded-full border border-hairline bg-surface px-4 py-2"
              style={({ pressed }) => ({ opacity: pressed ? 0.7 : 1 })}
            >
              <Text className="text-[12px] font-medium text-ink">{t('backToList')}</Text>
            </Pressable>
          </View>
        </View>
      </SafeAreaView>
    );
  }

  const delta = session && olderSession ? session.avgFps - olderSession.avgFps : undefined;

  return (
    <SafeAreaView edges={['top']} className="flex-1 bg-canvas">
      <ScrollView
        contentContainerStyle={{ paddingHorizontal: 20, paddingBottom: 48 }}
        showsVerticalScrollIndicator={false}
        refreshControl={
          <RefreshControl
            refreshing={refreshing}
            onRefresh={refreshAll}
            tintColor={colors.muted}
            colors={[colors.accent]}
            progressBackgroundColor={colors.surface}
          />
        }
      >
        <View className="mt-2 flex-row items-center gap-3">
          <Pressable
            onPress={goBack}
            hitSlop={8}
            accessibilityRole="button"
            accessibilityLabel={t('back')}
            className="h-9 w-9 items-center justify-center rounded-full border border-hairline bg-surface"
            style={({ pressed }) => ({ opacity: pressed ? 0.7 : 1 })}
          >
            <ChevronLeft size={18} color={colors.ink} strokeWidth={2} />
          </Pressable>
          <View className="flex-1">
            <Text className="text-[15px] font-semibold text-ink" numberOfLines={1}>
              {game.name}
            </Text>
            <Text className="mt-0.5 text-[11px] text-faint" numberOfLines={1}>
              {game.processName ?? t('manualGame')} · {sessionsCount(language, sessions.length)}
            </Text>
            {offline ? (
              <View className="mt-1.5">
                <OfflineBadge lastSync={lastSync} />
              </View>
            ) : null}
          </View>
          <Pressable
            onPress={() => setRenameVisible(true)}
            hitSlop={8}
            accessibilityRole="button"
            accessibilityLabel={t('renameGame')}
            className="h-9 w-9 items-center justify-center rounded-full border border-hairline bg-surface"
            style={({ pressed }) => ({ opacity: pressed ? 0.7 : 1 })}
          >
            <Pencil size={15} color={colors.muted} strokeWidth={2} />
          </Pressable>
        </View>

        {sessions.length === 0 ? (
          <View className="mt-6 items-center rounded-2xl border border-hairline bg-surface px-6 py-10">
            <Text className="text-[14px] font-medium text-ink">{t('noDataTitle')}</Text>
            <Text className="mt-1.5 text-center text-[12px] leading-4 text-muted">
              {t('noDataBody')}
            </Text>
          </View>
        ) : (
          <>
            <View className="mt-7 flex-row items-center justify-between">
              <Text className="text-[10px] font-medium uppercase tracking-[1.5px] text-faint">
                {t('playDays')}
              </Text>
              <Text className="text-[10px] text-faint" style={tabularNums}>
                {daysCount(language, sessionsPerDate.size)}
              </Text>
            </View>

            <ScrollView
              horizontal
              showsHorizontalScrollIndicator={false}
              contentContainerStyle={{ gap: 8, paddingRight: 4 }}
              className="mt-3"
            >
              {sessions.map((item) => (
                <DayPill
                  key={item.id}
                  date={item.date}
                  caption={
                    (sessionsPerDate.get(item.date) ?? 0) > 1 ? item.startedAt : undefined
                  }
                  selected={item.id === session?.id}
                  onPress={() => setSelectedSessionId(item.id)}
                />
              ))}
            </ScrollView>

            {sessions.length >= 2 ? (
              <Pressable
                onPress={() => setCompareVisible(true)}
                accessibilityRole="button"
                accessibilityLabel={t('compareSessions')}
                className="mt-4 self-start rounded-full border border-hairline bg-surface px-3.5 py-2"
                style={({ pressed }) => ({ opacity: pressed ? 0.7 : 1 })}
              >
                <Text className="text-[11px] font-medium text-ink">{t('compareSessions')}</Text>
              </Pressable>
            ) : null}

            {session ? (
              <>
                <View className="mt-5 rounded-2xl border border-hairline bg-surface p-5">
                  <Text className="text-[10px] font-medium uppercase tracking-[1.5px] text-faint">
                    {t('averageFps')}
                  </Text>

                  <View className="mt-2 flex-row">
                    <View className="flex-1 flex-row items-end self-center">
                      <Text
                        className="text-[62px] font-semibold leading-[66px] tracking-[-2px] text-ink"
                        style={tabularNums}
                        adjustsFontSizeToFit
                        numberOfLines={1}
                      >
                        {formatFps(session.avgFps, language)}
                      </Text>
                      <Text className="mb-2.5 ml-1.5 text-[12px] font-medium text-faint">FPS</Text>
                    </View>

                    <View className="w-px self-stretch bg-hairline" />

                    <View className="w-[100px] justify-between pl-4">
                      <Metric label={t('minLabel')} value={session.minFps} />
                      <View className="my-3 h-px bg-hairline" />
                      <Metric label={t('maxLabel')} value={session.maxFps} />
                    </View>
                  </View>

                  <View className="mt-4">
                    <Text className="text-[11px] text-muted" style={tabularNums}>
                      {formatLongDate(session.date, language)} ·{' '}
                      {formatTimeRange(session.startedAt, durationMinutes(session))}
                    </Text>
                    <Text className="mt-0.5 text-[11px] text-faint" style={tabularNums}>
                      {formatDuration(durationMinutes(session))}
                      {delta !== undefined
                        ? ` · ${formatSignedFps(delta, language)} ${t('previousSession')}`
                        : ''}
                    </Text>
                  </View>
                </View>

                <SessionInfoBadges session={session} />
                <SessionTelemetry session={session} />
                <Pressable
                  onPress={() => setNoteVisible(true)}
                  accessibilityRole="button"
                  accessibilityLabel={t('noteLabel')}
                  className="mt-4 self-start rounded-full border border-hairline bg-surface px-3.5 py-2"
                  style={({ pressed }) => ({ opacity: pressed ? 0.7 : 1 })}
                >
                  <Text className="text-[11px] font-medium text-ink">{t('noteLabel')}</Text>
                </Pressable>

                <View className="mt-3.5">
                  {samplesState === 'loading' ? (
                    <View className="items-center rounded-2xl border border-hairline bg-surface px-4 py-10">
                      <ActivityIndicator color={colors.muted} />
                      <Text className="mt-3 text-[11px] text-muted">{t('loadingChart')}</Text>
                    </View>
                  ) : samplesState === 'error' ? (
                    <View className="rounded-2xl border border-hairline bg-surface px-4 py-6">
                      <Text className="text-[12px] font-medium text-ink">
                        {t('chartLoadFailed')}
                      </Text>
                      <Text className="mt-1 text-[11px] leading-4 text-muted">{samplesError}</Text>
                    </View>
                  ) : samples.length === 0 ? (
                    <View className="items-center rounded-2xl border border-hairline bg-surface px-4 py-8">
                      <Text className="text-[12px] font-medium text-ink">
                        {t('noSamplesTitle')}
                      </Text>
                      <Text className="mt-1 text-center text-[11px] leading-4 text-muted">
                        {t('noSamplesBody')}
                      </Text>
                    </View>
                  ) : (
                    <FpsChart session={session} samples={samples} />
                  )}
                </View>

                <TemperatureChart samples={samples} startMinutes={session.startMinutes} />

                <Text className="mt-4 px-1 text-[10px] leading-4 text-faint">
                  {t('chartFootnote')}
                </Text>
              </>
            ) : null}
          </>
        )}
      </ScrollView>

      {renameVisible ? (
        <GameFormModal
          title={t('renameGame')}
          submitLabel={t('save')}
          initialName={game.name}
          onClose={() => setRenameVisible(false)}
          onSubmit={async (values) => {
            await rename(values.name);
          }}
        />
      ) : null}

      {compareVisible && game ? (
        <SessionCompareModal game={game} onClose={() => setCompareVisible(false)} />
      ) : null}

      {noteVisible && session ? (
        <SessionNoteEditor
          session={session}
          onClose={() => setNoteVisible(false)}
          onSaved={() => {
            void reload();
          }}
        />
      ) : null}
    </SafeAreaView>
  );
}
