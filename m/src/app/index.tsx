import { useMemo, useState } from 'react';
import { router } from 'expo-router';
import {
  ActivityIndicator,
  FlatList,
  Pressable,
  RefreshControl,
  Text,
  TextInput,
  View,
} from 'react-native';
import { Plus, Search, Settings2, X } from 'lucide-react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import { GameCard } from '@/components/game-card';
import { GameFormModal, type GameFormValues } from '@/components/game-form-modal';
import { LanguageToggle } from '@/components/language-toggle';
import { LiveNowCard } from '@/components/live-now-card';
import { LiveSessionModal } from '@/components/live-session-modal';
import { OfflineBadge } from '@/components/offline-badge';
import { ThemeToggle } from '@/components/theme-toggle';
import { useGames } from '@/hooks/use-games';
import { useLiveStatus } from '@/hooks/use-live-status';
import { gamesCount } from '@/lib/i18n';
import { useI18n } from '@/lib/i18n-context';
import { createGame } from '@/lib/telemetry-api';
import { tabularNums } from '@/lib/theme';
import { useTheme } from '@/lib/theme-context';
import type { FpsSample } from '@/types/telemetry';

/** How many live samples the in-memory graph of the live modal keeps. */
const LIVE_GRAPH_SAMPLES = 120;

export default function GamesScreen() {
  const { language, t } = useI18n();
  const { colors } = useTheme();
  const { games, state, error, refreshing, refresh, offline, lastSync } = useGames();
  const live = useLiveStatus();
  const [query, setQuery] = useState('');
  const [addVisible, setAddVisible] = useState(false);
  const [lastLive, setLastLive] = useState(live);
  const [liveSamples, setLiveSamples] = useState<FpsSample[]>([]);
  const [liveModalVisible, setLiveModalVisible] = useState(false);

  // The 6 s `useLiveStatus` poll returns a new `live` object each time;
  // while the game keeps playing every poll reports `isPlaying: true`. The
  // modal is closed only when the data says the game has stopped – a poll
  // mid-session never closes or resets an open modal.
  if (!live.isPlaying && liveModalVisible) {
    setLiveModalVisible(false);
  }

  // Append one sample per `useLiveStatus` poll: the hook returns a new `live`
  // object every poll, so adjusting the samples during render appends exactly
  // once per update (React's adjust-state-during-render pattern).
  if (live !== lastLive) {
    setLastLive(live);
    if (!live.isPlaying) {
      setLiveSamples([]);
    } else {
      const startedAtMs = live.startedAt ? Date.parse(live.startedAt) : Number.NaN;
      setLiveSamples((previous) => [
        ...previous.slice(-(LIVE_GRAPH_SAMPLES - 1)),
        {
          offsetSeconds: Number.isFinite(startedAtMs)
            ? Math.max(0, Math.round((Date.now() - startedAtMs) / 1000))
            : 0,
          fps: live.currentFps ?? 0,
          gpuTemp: live.gpuTemp,
          cpuTemp: live.cpuTemp,
          gpuLoad: live.gpuLoad,
          cpuLoad: live.cpuLoad,
        },
      ]);
    }
  }

  /** The live game already in the library (matched by process name or name). */
  const historyGame = useMemo(() => {
    if (!live.isPlaying) return null;
    const processName = live.processName?.trim().toLowerCase() ?? '';
    const gameName = live.gameName?.trim().toLowerCase() ?? '';
    const byProcess = processName
      ? games.find((game) => game.processName?.trim().toLowerCase() === processName)
      : undefined;
    if (byProcess) return byProcess;
    if (!gameName) return null;
    return games.find((game) => game.name.toLowerCase() === gameName) ?? null;
  }, [games, live]);

  const filteredGames = useMemo(() => {
    const needle = query.trim().toLowerCase();
    if (!needle) return games;
    return games.filter((game) => game.name.toLowerCase().includes(needle));
  }, [games, query]);

  const handleCreate = async ({ name, processName }: GameFormValues) => {
    const created = await createGame({ name, processName });
    setQuery('');
    refresh();
    router.push({ pathname: '/game/[id]', params: { id: created.id } });
  };

  const loading = state === 'loading' && games.length === 0;

  return (
    <SafeAreaView edges={['top']} className="flex-1 bg-canvas">
      <FlatList
        data={filteredGames}
        keyExtractor={(game) => game.id}
        renderItem={({ item }) => <GameCard game={item} />}
        ItemSeparatorComponent={() => <View className="h-2.5" />}
        contentContainerStyle={{ paddingHorizontal: 20, paddingBottom: 40 }}
        showsVerticalScrollIndicator={false}
        keyboardShouldPersistTaps="handled"
        keyboardDismissMode="on-drag"
        refreshControl={
          <RefreshControl
            refreshing={refreshing}
            onRefresh={refresh}
            tintColor={colors.muted}
            colors={[colors.accent]}
            progressBackgroundColor={colors.surface}
          />
        }
        ListHeaderComponent={
          <>
            <LiveNowCard
              status={live}
              onOpenModal={() => setLiveModalVisible(true)}
            />
            <View className="pb-5 pt-6">
            <View className="flex-row items-start justify-between">
              <View className="flex-1">
                <Text className="text-[10px] font-semibold uppercase tracking-[2.5px] text-faint">
                  FramePulse
                </Text>
                <Text className="mt-2 text-[32px] font-semibold tracking-[-0.8px] text-ink">
                  {t('gamesTitle')}
                </Text>
                <Text className="mt-1.5 text-[13px] text-muted">
                  {gamesCount(language, games.length)} · {t('pcTelemetry')}
                </Text>
                {offline ? (
                  <View className="mt-2">
                    <OfflineBadge lastSync={lastSync} />
                  </View>
                ) : null}
              </View>

              <View className="mt-1 flex-row items-center gap-2">
                {offline ? (
                <Pressable
                  onPress={() => router.push({ pathname: '/connection' })}
                  hitSlop={8}
                  accessibilityRole="button"
                  accessibilityLabel={t('connectionTitle')}
                  className="h-9 w-9 items-center justify-center rounded-full border border-hairline bg-surface"
                  style={({ pressed }) => ({ opacity: pressed ? 0.7 : 1 })}
                >
                  <Settings2 size={15} color={colors.muted} strokeWidth={2} />
                </Pressable>
              ) : null}
                <LanguageToggle />
                <ThemeToggle />

                <Pressable
                  onPress={() => setAddVisible(true)}
                  hitSlop={8}
                  accessibilityRole="button"
                  accessibilityLabel={t('addGame')}
                  className="h-9 w-9 items-center justify-center rounded-full border border-hairline bg-surface"
                  style={({ pressed }) => ({ opacity: pressed ? 0.7 : 1 })}
                >
                  <Plus size={18} color={colors.ink} strokeWidth={2} />
                </Pressable>
              </View>
            </View>

            <View className="mt-5 h-11 flex-row items-center gap-2.5 rounded-2xl border border-hairline bg-surface px-3.5">
              <Search size={16} color={colors.faint} strokeWidth={2} />
              <TextInput
                value={query}
                onChangeText={setQuery}
                placeholder={t('searchGames')}
                placeholderTextColor={colors.faint}
                selectionColor={colors.accent}
                autoCapitalize="none"
                autoCorrect={false}
                returnKeyType="search"
                accessibilityLabel={t('searchGames')}
                className="flex-1 text-[14px] text-ink"
              />
              {query.length > 0 ? (
                <Pressable
                  onPress={() => setQuery('')}
                  hitSlop={10}
                  accessibilityRole="button"
                  accessibilityLabel={t('clearSearch')}
                >
                  <X size={14} color={colors.muted} strokeWidth={2} />
                </Pressable>
              ) : null}
            </View>

            <View className="mt-5 flex-row items-center justify-between">
              <Text className="text-[10px] font-medium uppercase tracking-[1.5px] text-faint">
                {t('recentlyPlayed')}
              </Text>
              <Text className="text-[10px] text-faint" style={tabularNums}>
                {filteredGames.length} / {games.length}
              </Text>
            </View>
          </View>
          </>
        }
        ListEmptyComponent={
          loading ? (
            <View className="mt-2 items-center rounded-2xl border border-hairline bg-surface px-6 py-10">
              <ActivityIndicator color={colors.muted} />
              <Text className="mt-3 text-[12px] text-muted">{t('loadingTelemetry')}</Text>
            </View>
          ) : state === 'error' ? (
            <View className="mt-2 rounded-2xl border border-hairline bg-surface px-6 py-8">
              <Text className="text-[14px] font-medium text-ink">{t('loadFailed')}</Text>
              <Text className="mt-1.5 text-[12px] leading-4 text-muted">{error}</Text>
              <Pressable
                onPress={refresh}
                accessibilityRole="button"
                accessibilityLabel={t('retry')}
                className="mt-4 self-start rounded-full border border-hairline bg-raised px-4 py-2"
                style={({ pressed }) => ({ opacity: pressed ? 0.7 : 1 })}
              >
                <Text className="text-[12px] font-medium text-ink">{t('retry')}</Text>
              </Pressable>
            </View>
          ) : games.length === 0 ? (
            <View className="mt-2 items-center rounded-2xl border border-hairline bg-surface px-6 py-10">
              <Text className="text-[14px] font-medium text-ink">{t('noGamesTitle')}</Text>
              <Text className="mt-1.5 text-center text-[12px] leading-4 text-muted">
                {t('noGamesBody')}
              </Text>
              <Pressable
                onPress={() => setAddVisible(true)}
                accessibilityRole="button"
                accessibilityLabel={t('addGame')}
                className="mt-4 flex-row items-center gap-1.5 rounded-full bg-ink px-4 py-2"
                style={({ pressed }) => ({ opacity: pressed ? 0.8 : 1 })}
              >
                <Plus size={14} color={colors.canvas} strokeWidth={2.4} />
                <Text className="text-[12px] font-semibold text-canvas">{t('addGame')}</Text>
              </Pressable>
            </View>
          ) : (
            <View className="mt-2 items-center rounded-2xl border border-hairline bg-surface px-6 py-10">
              <Search size={20} color={colors.faint} strokeWidth={1.8} />
              <Text className="mt-3 text-[14px] font-medium text-ink">
                {t('nothingFoundTitle')}
              </Text>
              <Text className="mt-1 text-center text-[12px] text-muted">
                {t('nothingFoundBody')}
              </Text>
            </View>
          )
        }
      />

      {liveModalVisible ? (
        <LiveSessionModal
          status={live}
          liveSamples={liveSamples}
          historyGameId={historyGame?.id ?? null}
          onClose={() => setLiveModalVisible(false)}
        />
      ) : null}

      {addVisible ? (
        <GameFormModal
          title={t('addGame')}
          submitLabel={t('addGameSubmit')}
          withProcessName
          onClose={() => setAddVisible(false)}
          onSubmit={handleCreate}
        />
      ) : null}
    </SafeAreaView>
  );
}
