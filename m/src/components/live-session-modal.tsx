import { useEffect, useState } from 'react';
import { Modal, Pressable, Text, View } from 'react-native';
import { router } from 'expo-router';
import { X } from 'lucide-react-native';

import { TemperatureChart } from '@/components/temperature-chart';
import type { LiveStatus } from '@/hooks/use-live-status';
import { formatPercent, formatTempC } from '@/lib/session-display';
import { useI18n } from '@/lib/i18n-context';
import { formatFps } from '@/lib/format';
import { tabularNums, themeVariables } from '@/lib/theme';
import { useTheme } from '@/lib/theme-context';
import type { FpsSample } from '@/types/telemetry';

function formatElapsedSeconds(total: number): string {
  const safe = Math.max(0, total);
  const hours = Math.floor(safe / 3600);
  const minutes = Math.floor((safe % 3600) / 60);
  const seconds = Math.round(safe % 60);

  if (hours > 0) {
    return `${hours}:${String(minutes).padStart(2, '0')}:${String(seconds).padStart(2, '0')}`;
  }
  return `${minutes}:${String(seconds).padStart(2, '0')}`;
}

function LiveInfoRow({ label, value }: { label: string; value: string | null }) {
  return (
    <View className="flex-1 flex-row items-center justify-between py-1">
      <Text className="text-[11px] text-muted">{label}</Text>
      <Text className="text-[13px] text-ink" style={tabularNums} numberOfLines={1}>
        {value ?? '—'}
      </Text>
    </View>
  );
}

type LiveSessionModalProps = {
  status: LiveStatus;
  /** In-memory samples appended on every `useLiveStatus` poll while playing. */
  liveSamples: FpsSample[];
  /** Id of the matching `games` record, when the live game is already in the library. */
  historyGameId: string | null;
  onClose: () => void;
};

/**
 * Live telemetry modal ("Živá telemetrie"): big current FPS, live play
 * duration, resolution, graphics API and GPU/CPU temperatures, plus a live
 * mini-graph of the recent values. When the live game exists in the games
 * library, a "View Game History" button opens its detail screen.
 */
export function LiveSessionModal({ status, liveSamples, historyGameId, onClose }: LiveSessionModalProps) {
  const { language, t } = useI18n();
  const { mode, colors } = useTheme();
  const variables = themeVariables(mode);

  const startedAtMs = status.startedAt ? Date.parse(status.startedAt) : Number.NaN;
  const startedAtDate = Number.isFinite(startedAtMs) ? new Date(startedAtMs) : null;
  const startMinutes = startedAtDate ? startedAtDate.getHours() * 60 + startedAtDate.getMinutes() : 0;

  const [elapsedSeconds, setElapsedSeconds] = useState(() =>
    Number.isFinite(startedAtMs) ? Math.max(0, Math.round((Date.now() - startedAtMs) / 1000)) : 0,
  );

  useEffect(() => {
    if (!Number.isFinite(startedAtMs)) return undefined;
    const id = setInterval(() => {
      setElapsedSeconds(Math.max(0, Math.round((Date.now() - startedAtMs) / 1000)));
    }, 1000);
    return () => clearInterval(id);
  }, [startedAtMs]);

  if (!status.isPlaying) return null;

  const goToHistory = () => {
    if (historyGameId) {
      router.push({ pathname: '/game/[id]', params: { id: historyGameId } });
    }
  };

  return (
    <Modal
      visible
      transparent
      animationType="fade"
      statusBarTranslucent
      onRequestClose={onClose}
    >
      <View className={`flex-1 justify-center px-5 ${mode === 'dark' ? 'bg-black/70' : 'bg-black/30'}`} style={variables}>
        <Pressable
          className="absolute inset-0"
          onPress={onClose}
          accessibilityRole="button"
          accessibilityLabel={t('close')}
        />

        <View className="mx-auto rounded-3xl border border-hairline bg-surface p-5">
          <View className="flex-row items-center justify-between">
            <Text className="text-[15px] font-semibold text-ink">{t('liveSessionTitle')}</Text>
            <Pressable
              onPress={onClose}
              hitSlop={10}
              accessibilityRole="button"
              accessibilityLabel={t('close')}
            >
              <X size={20} color={colors.ink} strokeWidth={2} />
            </Pressable>
          </View>

          <Text className="mt-1 text-[30px] font-bold leading-[34px] tracking-[-1px] text-ink" style={tabularNums}>
            {status.currentFps !== null ? formatFps(status.currentFps, language) : '—'}
          </Text>
          <Text className="mt-0.5 text-[11px] font-medium uppercase tracking-[1.5px] text-faint">FPS</Text>

          <Text className="mt-3 text-[13px] font-medium text-muted" style={tabularNums}>
            {formatElapsedSeconds(elapsedSeconds)}
          </Text>
          <Text className="mt-0.5 text-[10px] font-medium uppercase tracking-[1.2px] text-faint">
            {t('liveSessionDuration')}
          </Text>

          <View className="mt-4 flex-row">
            <LiveInfoRow label={t('badgeResolution')} value={status.resolution} />
            <LiveInfoRow label={t('temperatureGpu')} value={formatTempC(status.gpuTemp)} />
          </View>
          <View className="mt-2 flex-row">
            <LiveInfoRow label={t('badgeGraphicsApi')} value={status.graphicsApi} />
            <LiveInfoRow label={t('temperatureCpu')} value={formatTempC(status.cpuTemp)} />
          </View>
          <View className="mt-2 flex-row">
            <LiveInfoRow label={t('telemetryGpuLoad')} value={formatPercent(status.gpuLoad)} />
            <LiveInfoRow label={t('telemetryCpuLoad')} value={formatPercent(status.cpuLoad)} />
          </View>

          <TemperatureChart samples={liveSamples} startMinutes={startMinutes} height={150} />

          {historyGameId ? (
            <Pressable
              onPress={goToHistory}
              accessibilityRole="button"
              accessibilityLabel={t('viewGameHistory')}
              className="mt-4 self-start rounded-full border border-hairline bg-surface px-3.5 py-2"
              style={({ pressed }) => ({ opacity: pressed ? 0.7 : 1 })}
            >
              <Text className="text-[11px] font-medium text-ink">{t('viewGameHistory')}</Text>
            </Pressable>
          ) : null}
        </View>
      </View>
    </Modal>
  );
}
