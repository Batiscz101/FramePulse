import { useEffect, useState } from 'react';
import { Pressable, ScrollView, Text, TextInput, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { ChevronLeft } from 'lucide-react-native';
import { router } from 'expo-router';

import { useI18n } from '@/lib/i18n-context';
import {
  NEON_DATA_API_URL,
  readConnectionSettings,
  saveConnectionSettings,
} from '@/lib/supabase';
import { useTheme } from '@/lib/theme-context';

/**
 * Connection settings for the PostgREST (Neon Data API) endpoint. The API key
 * is optional – the public endpoint serves the `anonymous` role.
 */
export default function ConnectionScreen() {
  const { t } = useI18n();
  const { colors } = useTheme();
  const [url, setUrl] = useState(NEON_DATA_API_URL);
  const [apiKey, setApiKey] = useState('');
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    readConnectionSettings()
      .then(({ url: savedUrl, apiKey: savedKey }) => {
        if (!active) return;
        setUrl(savedUrl);
        setApiKey(savedKey);
      })
      .catch(() => {
        // Keep the defaults when the saved settings cannot be read.
      });
    return () => {
      active = false;
    };
  }, []);

  const handleSave = async () => {
    setSaving(true);
    setError(null);
    try {
      await saveConnectionSettings({ url: url.trim(), apiKey: apiKey.trim() });
      router.back();
    } catch {
      setSaving(false);
      setError(t('connectionSaveFailed'));
    }
  };

  return (
    <SafeAreaView edges={['top']} className="flex-1 bg-canvas">
      <ScrollView
        contentContainerStyle={{ paddingHorizontal: 20, paddingTop: 12, paddingBottom: 40 }}
        keyboardShouldPersistTaps="handled"
      >
        <View className="flex-row items-center gap-3">
          <Pressable
            onPress={() => router.back()}
            hitSlop={8}
            accessibilityRole="button"
            accessibilityLabel={t('back')}
            className="h-9 w-9 items-center justify-center rounded-full border border-hairline bg-surface"
            style={({ pressed }) => ({ opacity: pressed ? 0.7 : 1 })}
          >
            <ChevronLeft size={18} color={colors.ink} strokeWidth={2} />
          </Pressable>
          <Text className="text-[15px] font-semibold text-ink">{t('connectionTitle')}</Text>
        </View>

        <View className="mt-6 rounded-2xl border border-hairline bg-surface p-4">
          <Text className="text-[10px] font-medium uppercase tracking-[1.2px] text-faint">
            {t('connectionUrlLabel')}
          </Text>
          <TextInput
            value={url}
            onChangeText={setUrl}
            placeholder={t('connectionUrlPlaceholder')}
            placeholderTextColor={colors.faint}
            autoCapitalize="none"
            autoCorrect={false}
            keyboardType="url"
            returnKeyType="done"
            accessibilityLabel={t('connectionUrlLabel')}
            className="mt-1.5 text-[14px] text-ink"
          />
        </View>

        <View className="mt-3 rounded-2xl border border-hairline bg-surface p-4">
          <Text className="text-[10px] font-medium uppercase tracking-[1.2px] text-faint">
            {t('connectionApiKeyLabel')}
          </Text>
          <TextInput
            value={apiKey}
            onChangeText={setApiKey}
            placeholder={t('connectionApiKeyPlaceholder')}
            placeholderTextColor={colors.faint}
            autoCapitalize="none"
            autoCorrect={false}
            secureTextEntry
            accessibilityLabel={t('connectionApiKeyLabel')}
            className="mt-1.5 text-[14px] text-ink"
          />
          <Text className="mt-1.5 text-[11px] leading-4 text-faint">{t('connectionHint')}</Text>
        </View>

        <Pressable
          onPress={() => {
            void handleSave();
          }}
          disabled={saving}
          accessibilityRole="button"
          accessibilityLabel={t('connectionSave')}
          className="mt-5 self-start rounded-full border border-hairline bg-raised px-4 py-2"
          style={({ pressed }) => ({ opacity: pressed ? 0.7 : 1 })}
        >
          <Text className="text-[12px] font-medium text-ink">{t('connectionSave')}</Text>
        </Pressable>

        {error ? <Text className="mt-3 text-[12px] text-danger">{error}</Text> : null}
      </ScrollView>
    </SafeAreaView>
  );
}

