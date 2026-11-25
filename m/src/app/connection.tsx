import { useEffect, useState } from 'react';
import { ActivityIndicator, Pressable, ScrollView, Text, TextInput, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { ChevronLeft } from 'lucide-react-native';
import { router } from 'expo-router';

import { useI18n } from '@/lib/i18n-context';
import {
  NEON_AUTH_URL,
  NEON_DATA_API_URL,
  deriveNeonAuthUrl,
  isNeonAuthRequiredError,
  readConnectionSettings,
  saveConnectionSettings,
  testConnection,
} from '@/lib/supabase';
import { describeError } from '@/lib/telemetry-api';
import { useTheme } from '@/lib/theme-context';

type ConnectionFailure = { kind: 'save' } | { kind: 'api'; error: unknown };

/**
 * Connection settings for the PostgREST (Neon Data API) endpoint. Without a
 * static JWT key, an anonymous JWT is fetched from Neon Auth automatically.
 */
export default function ConnectionScreen() {
  const { language, t } = useI18n();
  const { colors } = useTheme();
  const [url, setUrl] = useState(NEON_DATA_API_URL);
  const [authUrl, setAuthUrl] = useState(NEON_AUTH_URL);
  const [apiKey, setApiKey] = useState('');
  const [saving, setSaving] = useState(false);
  const [failure, setFailure] = useState<ConnectionFailure | null>(null);

  useEffect(() => {
    let active = true;
    readConnectionSettings()
      .then(({ url: savedUrl, apiKey: savedKey, authUrl: savedAuthUrl }) => {
        if (!active) return;
        setUrl(savedUrl);
        setApiKey(savedKey);
        setAuthUrl(savedAuthUrl ?? '');
        return testConnection().catch((caught) => {
          if (active && isNeonAuthRequiredError(caught)) {
            setFailure({ kind: 'api', error: caught });
          }
        });
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
    setFailure(null);
    try {
      await saveConnectionSettings({
        url: url.trim(),
        apiKey: apiKey.trim(),
        authUrl: authUrl.trim(),
      });
    } catch {
      setSaving(false);
      setFailure({ kind: 'save' });
      return;
    }

    try {
      await testConnection();
      router.back();
    } catch (caught) {
      setSaving(false);
      setFailure({ kind: 'api', error: caught });
    }
  };

  const errorMessage = failure
    ? failure.kind === 'save'
      ? t('connectionSaveFailed')
      : describeError(failure.error, language)
    : null;
  const derivedAuthPlaceholder = deriveNeonAuthUrl(url) || t('connectionAuthUrlPlaceholder');

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
            {t('connectionAuthUrlLabel')}
          </Text>
          <TextInput
            value={authUrl}
            onChangeText={setAuthUrl}
            placeholder={derivedAuthPlaceholder}
            placeholderTextColor={colors.faint}
            autoCapitalize="none"
            autoCorrect={false}
            keyboardType="url"
            returnKeyType="done"
            accessibilityLabel={t('connectionAuthUrlLabel')}
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
          className="mt-5 flex-row items-center gap-2 self-start rounded-full border border-hairline bg-raised px-4 py-2"
          style={({ pressed }) => ({ opacity: pressed || saving ? 0.7 : 1 })}
        >
          {saving ? <ActivityIndicator size="small" color={colors.ink} /> : null}
          <Text className="text-[12px] font-medium text-ink">{t('connectionSave')}</Text>
        </Pressable>

        {errorMessage ? (
          <View className="mt-3 rounded-2xl border border-danger/30 bg-surface p-3.5">
            <Text className="text-[12px] leading-4 text-danger">{errorMessage}</Text>
          </View>
        ) : null}
      </ScrollView>
    </SafeAreaView>
  );
}

