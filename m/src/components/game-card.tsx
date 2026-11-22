import { Link } from 'expo-router';
import { Pressable, Text, View } from 'react-native';

import { formatFps, formatShortDate } from '@/lib/format';
import { useI18n } from '@/lib/i18n-context';
import { tabularNums } from '@/lib/theme';
import { useTheme } from '@/lib/theme-context';
import { accentFor, type Game } from '@/types/telemetry';

type GameCardProps = {
  game: Game;
};

export function GameCard({ game }: GameCardProps) {
  const { language, t } = useI18n();
  const { mode } = useTheme();
  const session = game.sessions[0];
  const source = game.processName ?? 'PC';

  return (
    <Link href={{ pathname: '/game/[id]', params: { id: game.id } }} asChild>
      <Pressable
        accessibilityRole="button"
        accessibilityLabel={
          session
            ? t('cardAverageA11y', {
                name: game.name,
                fps: formatFps(session.avgFps, language),
              })
            : t('cardNoDataA11y', { name: game.name })
        }
        className="flex-row items-center gap-3.5 rounded-2xl border border-hairline bg-surface px-4 py-3.5"
        style={({ pressed }) => ({ opacity: pressed ? 0.72 : 1 })}
      >
        <View className="h-11 w-11 items-center justify-center rounded-xl border border-hairline bg-raised">
          <Text
            className="text-[13px] font-semibold tracking-wide"
            style={{ color: accentFor(game.id, mode) }}
          >
            {game.shortName}
          </Text>
        </View>

        <View className="flex-1">
          <Text className="text-[15px] font-semibold text-ink" numberOfLines={1}>
            {game.name}
          </Text>
          <Text className="mt-1 text-[12px] text-muted" numberOfLines={1}>
            {session
              ? `${source} · ${t('lastPlayed', {
                  date: formatShortDate(session.date, language),
                })}`
              : `${source} · ${t('noDataYet')}`}
          </Text>
        </View>

        <View className="items-end">
          <Text className="text-[24px] font-semibold leading-7 text-ink" style={tabularNums}>
            {session ? formatFps(session.avgFps, language) : '—'}
          </Text>
          <Text className="mt-0.5 text-[9px] font-medium uppercase tracking-[1.5px] text-faint">
            FPS
          </Text>
        </View>
      </Pressable>
    </Link>
  );
}
