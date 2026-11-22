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
import { describeError, updateSessionNote } from '@/lib/telemetry-api';
import { tabularNums, themeVariables } from '@/lib/theme';
import { useTheme } from '@/lib/theme-context';
import type { GameSession } from '@/types/telemetry';

type SessionNoteEditorProps = {
  session: GameSession;
  onClose: () => void;
  onSaved: () => void;
};

/** Modal with a text field for the user's own note on the session. */
export function SessionNoteEditor({ session, onClose, onSaved }: SessionNoteEditorProps) {
  const { language, t } = useI18n();
  const { mode, colors } = useTheme();
  const variables = themeVariables(mode);
  const [text, setText] = useState(session.note ?? '');
  const [saving, setSaving] = useState(false);
  const [savedAt, setSavedAt] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);

  const handleSave = async () => {
    setSaving(true);
    setError(null);
    setSavedAt(null);

    try {
      await updateSessionNote(session.id, text.trim());
      setSavedAt(Date.now());
      setTimeout(() => setSavedAt(null), 2500);
      onSaved();
    } catch (caught) {
      setError(describeError(caught, language));
    } finally {
      setSaving(false);
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
          <Text className="text-[16px] font-semibold text-ink">{t('noteLabel')}</Text>

          <TextInput
            value={text}
            onChangeText={setText}
            placeholder={t('notePlaceholder')}
            placeholderTextColor={colors.faint}
            selectionColor={colors.accent}
            autoFocus
            autoCapitalize="sentences"
            autoCorrect
            returnKeyType="done"
            onSubmitEditing={handleSave}
            accessibilityLabel={t('noteLabel')}
            className="mt-4 h-24 rounded-xl border border-hairline bg-raised px-3.5 text-[14px] text-ink"
          />

          {savedAt !== null ? (
            <Text className="mt-4 text-[11px] text-muted" style={tabularNums}>
              {t('noteSaved')}
            </Text>
          ) : null}

          {error ? (
            <Text className="mt-4 text-[11px] leading-4 text-danger" accessibilityLiveRegion="polite">
              {error}
            </Text>
          ) : null}

          <View className="mt-5 flex-row items-center gap-2.5">
            <Pressable
              onPress={onClose}
              disabled={saving}
              accessibilityRole="button"
              accessibilityLabel={t('cancel')}
              className="h-11 flex-1 items-center justify-center rounded-xl border border-hairline bg-raised"
              style={({ pressed }) => ({ opacity: pressed || saving ? 0.6 : 1 })}
            >
              <Text className="text-[13px] font-medium text-ink">{t('cancel')}</Text>
            </Pressable>

            <Pressable
              onPress={handleSave}
              disabled={saving}
              accessibilityRole="button"
              accessibilityLabel={t('save')}
              accessibilityState={{ disabled: saving }}
              className="h-11 flex-1 items-center justify-center rounded-xl bg-ink"
              style={({ pressed }) => ({ opacity: !saving && !pressed ? 0.8 : pressed ? 1 : 1 })}
            >
              {saving ? (
                <ActivityIndicator size="small" color={colors.canvas} />
              ) : (
                <Text className="text-[13px] font-semibold text-canvas">{t('save')}</Text>
              )}
            </Pressable>
          </View>
        </View>
      </KeyboardAvoidingView>
    </Modal>
  );
}
