import { useState } from 'react';
import {
  ActivityIndicator,
  KeyboardAvoidingView,
  Modal,
  Platform,
  Pressable,
  Text,
  TextInput,
  View,
} from 'react-native';

import { useI18n } from '@/lib/i18n-context';
import { describeError } from '@/lib/telemetry-api';
import { themeVariables } from '@/lib/theme';
import { useTheme } from '@/lib/theme-context';

export type GameFormValues = {
  name: string;
  processName: string | null;
};

type GameFormModalProps = {
  title: string;
  submitLabel: string;
  initialName?: string;
  initialProcessName?: string;
  /** Shows the optional process name field (used when adding a game). */
  withProcessName?: boolean;
  onClose: () => void;
  onSubmit: (values: GameFormValues) => Promise<void>;
};

/**
 * Mounts fresh every time it opens (the parent renders it conditionally), so the
 * fields always start from `initialName` / `initialProcessName`.
 */
export function GameFormModal({
  title,
  submitLabel,
  initialName = '',
  initialProcessName = '',
  withProcessName = false,
  onClose,
  onSubmit,
}: GameFormModalProps) {
  const { language, t } = useI18n();
  const { mode, colors } = useTheme();
  const variables = themeVariables(mode);
  const [name, setName] = useState(initialName);
  const [processName, setProcessName] = useState(initialProcessName);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const canSubmit = name.trim().length > 0 && !busy;

  const handleSubmit = async () => {
    if (!canSubmit) return;

    setBusy(true);
    setError(null);

    try {
      await onSubmit({
        name: name.trim(),
        processName: processName.trim().length > 0 ? processName.trim() : null,
      });
      onClose();
    } catch (caught) {
      setError(describeError(caught, language));
    } finally {
      setBusy(false);
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
      <KeyboardAvoidingView
        behavior={Platform.OS === 'ios' ? 'padding' : undefined}
        className={`flex-1 justify-center px-5 ${mode === 'dark' ? 'bg-black/70' : 'bg-black/30'}`}
        style={variables}
      >
        <Pressable
          className="absolute inset-0"
          onPress={onClose}
          accessibilityRole="button"
          accessibilityLabel={t('close')}
        />

        <View className="rounded-3xl border border-hairline bg-surface p-5">
          <Text className="text-[16px] font-semibold text-ink">{title}</Text>
          <Text className="mt-1 text-[12px] leading-4 text-muted">
            {withProcessName ? t('addGameHint') : t('renameGameHint')}
          </Text>

          <Text className="mt-5 text-[9px] font-medium uppercase tracking-[1.2px] text-faint">
            {t('gameName')}
          </Text>
          <TextInput
            value={name}
            onChangeText={setName}
            placeholder={t('gameNamePlaceholder')}
            placeholderTextColor={colors.faint}
            selectionColor={colors.accent}
            autoFocus
            autoCapitalize="words"
            autoCorrect={false}
            returnKeyType="done"
            onSubmitEditing={handleSubmit}
            accessibilityLabel={t('gameName')}
            className="mt-1.5 h-11 rounded-xl border border-hairline bg-raised px-3.5 text-[14px] text-ink"
          />

          {withProcessName ? (
            <>
              <Text className="mt-4 text-[9px] font-medium uppercase tracking-[1.2px] text-faint">
                {t('processOptional')}
              </Text>
              <TextInput
                value={processName}
                onChangeText={setProcessName}
                placeholder={t('processPlaceholder')}
                placeholderTextColor={colors.faint}
                selectionColor={colors.accent}
                autoCapitalize="none"
                autoCorrect={false}
                returnKeyType="done"
                onSubmitEditing={handleSubmit}
                accessibilityLabel={t('processName')}
                className="mt-1.5 h-11 rounded-xl border border-hairline bg-raised px-3.5 text-[13px] text-ink"
              />
            </>
          ) : null}

          {error ? (
            <Text
              className="mt-4 text-[11px] leading-4 text-danger"
              accessibilityLiveRegion="polite"
            >
              {error}
            </Text>
          ) : null}

          <View className="mt-5 flex-row items-center gap-2.5">
            <Pressable
              onPress={onClose}
              disabled={busy}
              accessibilityRole="button"
              accessibilityLabel={t('cancel')}
              className="h-11 flex-1 items-center justify-center rounded-xl border border-hairline bg-raised"
              style={({ pressed }) => ({ opacity: pressed || busy ? 0.6 : 1 })}
            >
              <Text className="text-[13px] font-medium text-ink">{t('cancel')}</Text>
            </Pressable>

            <Pressable
              onPress={handleSubmit}
              disabled={!canSubmit}
              accessibilityRole="button"
              accessibilityLabel={submitLabel}
              accessibilityState={{ disabled: !canSubmit, busy }}
              className="h-11 flex-1 items-center justify-center rounded-xl bg-ink"
              style={({ pressed }) => ({ opacity: !canSubmit ? 0.4 : pressed ? 0.8 : 1 })}
            >
              {busy ? (
                <ActivityIndicator size="small" color={colors.canvas} />
              ) : (
                <Text className="text-[13px] font-semibold text-canvas">{submitLabel}</Text>
              )}
            </Pressable>
          </View>
        </View>
      </KeyboardAvoidingView>
    </Modal>
  );
}
