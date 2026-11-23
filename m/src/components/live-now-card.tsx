import { useEffect, useState } from 'react';
import { Animated, Pressable, Text, View } from 'react-native';
import { ChevronRight } from 'lucide-react-native';

import { LiveSessionModal } from '@/components/live-session-modal';
import type { LiveStatus } from '@/hooks/use-live-status';
import { formatFps } from '@/lib/format';
import { useI18n } from '@/lib/i18n-context';
import { tabularNums } from '@/lib/theme';
import { useTheme } from '@/lib/theme-context';
import type { FpsSample } from '@/types/telemetry';

function formatTempC(value: number | null): string | null {
  return value === null ? null : `${Math.round(value)}°C`;
}

type LiveNowCardProps = {
  status: LiveStatus;
  /** In-memory samples appended on every `useLiveStatus` poll while playing. */
  liveSamples: FpsSample[];
  /** Id of the matching `games` record, when the live game is already in the library. */
  historyGameId: string | null;
};

/**
 * Minimalist "Právě hraji" card rendered at the very top of the main screen:
 * a pulsing green indicator, the game name, the current FPS and a line with
 * the live resolution, graphics API and GPU/CPU temperatures. Pressing it
 * opens the full-screen "Live Telemetry" modal.
 */
export function LiveNowCard({ status, liveSamples, historyGameId }: LiveNowCardProps) {
  const { language, t } = useI18n();
  const { colors } = useTheme();
  const [pulse] = useState(() => new Animated.Value(0));
  const [modalVisible, setModalVisible] = useState(false);

  useEffect(() => {
    const animation = Animated.loop(
      Animated.sequence([
        Animated.timing(pulse, { toValue: 1, duration: 900, useNativeDriver: true }),
        Animated.timing(pulse, { toValue: 0, duration: 900, useNativeDriver: true }),
      ]),
    );
    animation.start();
    return () => animation.stop();
  }, [pulse]);

  if (!status.isPlaying) return null;

  const detailParts = [
    status.resolution,
    status.graphicsApi,
    formatTempC(status.gpuTemp),
    formatTempC(status.cpuTemp),
  ].filter((part): part is string => part !== null);

  return (
    <View className="mt-2 mb-5">
      <Pressable
        onPress={() => setModalVisible(true)}
        accessibilityRole="button"
        accessibilityLabel={t('liveNow')}
        className="rounded-2xl border border-hairline bg-surface px-4 py-3.5"
        style={({ pressed }) => ({ opacity: pressed ? 0.85 : 1 })}
      >
        <View className="flex-row items-center gap-2">
          <Animated.View
            className="h-2.5 w-2.5 rounded-full"
            style={[
              { backgroundColor: colors.accent },
              {
                opacity: pulse.interpolate({
                  inputRange: [0, 0.5, 1],
                  outputRange: [0.45, 1, 0.45],
                }),
                transform: [
                  {
                    translateY: pulse.interpolate({
                      inputRange: [0, 0.5, 1],
                      outputRange: [0, -3, 0],
                    }),
                  },
                ],
              },
            ]}
          />
          <Text
            className="text-[10px] font-medium uppercase tracking-[1.5px]"
            style={{ color: colors.accent }}
          >
            {t('liveNow')}
          </Text>
          <View className="flex-1" />
          <ChevronRight size={16} color={colors.faint} strokeWidth={2} />
        </View>

        <Text className="mt-1.5 text-[15px] font-semibold text-ink" numberOfLines={1}>
          {status.gameName ?? '—'}
        </Text>

        <Text className="mt-0.5 text-[28px] font-bold leading-[32px] tracking-[-1px] text-ink" style={tabularNums}>
          {status.currentFps !== null ? formatFps(status.currentFps, language) : '—'}
        </Text>

        {detailParts.length > 0 ? (
          <Text className="mt-1 text-[11px] text-muted" style={tabularNums} numberOfLines={2}>
            {detailParts.join(' · ')}
          </Text>
        ) : null}
      </Pressable>

      {modalVisible ? (
        <LiveSessionModal
          status={status}
          liveSamples={liveSamples}
          historyGameId={historyGameId}
          onClose={() => setModalVisible(false)}
        />
      ) : null}
    </View>
  );
}
