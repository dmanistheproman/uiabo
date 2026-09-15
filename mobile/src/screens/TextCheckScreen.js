import React from 'react';
import { ActivityIndicator, Alert, Keyboard, StyleSheet, Text, TextInput, View } from 'react-native';
import { useAuth } from '../auth/AuthContext';
import { PageBody, PageHeader } from '../components/AppShell';
import Button from '../components/Button';
import { checkText } from '../services/api';
import { colours } from '../theme';

export default function TextCheckScreen({ onNavigate, onResult, setWorking, initialDraft = null }) {
  const { firebaseUser, profile, refreshProfile } = useAuth();
  const [text, setText] = React.useState(initialDraft?.text || '');
  const [busy, setBusy] = React.useState(false);
  const [error, setError] = React.useState('');
  const requestKey = React.useRef(null);
  const sending = React.useRef(false);
  const remaining = profile?.allowance?.remaining_submissions;
  async function submit() {
    if (sending.current) return;
    if (!text.trim()) return setError('Paste a message to check.');
    sending.current = true;
    setBusy(true); setWorking(true); setError(''); Keyboard.dismiss();
    requestKey.current ||= `${Date.now().toString(36)}-${Math.random().toString(36).slice(2)}-${Math.random().toString(36).slice(2)}`;
    try {
      const result = await checkText(firebaseUser, text, requestKey.current);
      await refreshProfile().catch(() => {});
      onResult(result);
    } catch (problem) {
      setError(problem.message);
      // Preserve the key for uncertain network outcomes to recover a saved
      // result without charging twice. Definite failures can start a new run.
      if (problem.code && !['ANALYSIS_IN_PROGRESS', 'RESULT_STORAGE_UNAVAILABLE'].includes(problem.code)) requestKey.current = null;
      await refreshProfile().catch(() => {});
    } finally {
      sending.current = false; setBusy(false); setWorking(false);
    }
  }
  return <View style={{ flex: 1 }}>
    <PageHeader title="Check text" onBack={() => !busy && onNavigate('home')} badge={remaining == null ? '— left' : `${remaining} left`} />
    <PageBody>
        <View><Text style={styles.eyebrow}>TEXT ANALYSIS</Text><Text style={styles.title}>Paste the message to check</Text><Text style={styles.copy}>Use short English text for the clearest result.</Text></View>
        {!!initialDraft?.correctYear && <View style={styles.info}><Text style={styles.label}>Correct the year</Text><Text style={styles.copy}>Add the intended year next to the date in your message, then check it again. This creates a new saved result and uses your allowance if the check completes.</Text></View>}
        <View><Text style={styles.label}>Message or caption</Text>
          <TextInput accessibilityLabel="Message or caption" multiline textAlignVertical="top" editable={!busy} maxLength={5000}
            placeholder="Paste a message, claim or caption…" placeholderTextColor="#7D909E" style={styles.input} value={text}
            onChangeText={value => { setText(value); setError(''); requestKey.current = null; }} />
          <View style={styles.caption}><Text style={styles.hint}>Do not include passwords or private information.</Text><Text style={styles.hint}>{text.length.toLocaleString()} / 5,000</Text></View>
        </View>
        <View style={styles.info}><Text style={styles.label}>What happens next?</Text><Text style={styles.copy}>UIABO identifies a checkable claim, searches for evidence and explains any uncertainty.</Text></View>
        {!!error && <Text accessibilityRole="alert" style={styles.error}>{error}</Text>}
        {busy ? <View accessibilityLiveRegion="polite" style={styles.progress}><ActivityIndicator size="large" color={colours.blue} /><Text style={styles.label}>Checking the claim and its sources…</Text><Text style={styles.copy}>This may take a couple of minutes. Keep this screen open.</Text></View> : <>
          <Button onPress={submit} disabled={remaining === 0 || remaining == null}>Check this text</Button>
          {remaining === 0 && <Text style={styles.error}>You've used your allowance. You can still view your saved results.</Text>}
          {remaining == null && <Button secondary onPress={() => refreshProfile().catch(problem => Alert.alert('Could not refresh', problem.message))}>Refresh allowance</Button>}
          <Text style={[styles.hint, { textAlign: 'center' }]}>Only successful checks use your {profile?.role === 'premium' ? 'monthly' : 'daily'} allowance.</Text>
          {!!error && <Button secondary onPress={() => onNavigate('results')}>View saved results</Button>}
        </>}
    </PageBody>
  </View>;
}

const styles = StyleSheet.create({
  eyebrow: { color: '#008B89', fontWeight: '800', fontSize: 12, letterSpacing: 1, marginBottom: 8 },
  title: { color: '#173447', fontSize: 25, fontWeight: '800', marginBottom: 5 },
  copy: { color: '#526F83', lineHeight: 21, fontSize: 14 },
  label: { color: '#173447', fontWeight: '700', fontSize: 14, marginBottom: 7 },
  input: { backgroundColor: 'white', minHeight: 180, borderColor: '#B8CDD9', borderWidth: 1, borderRadius: 14, padding: 15, color: '#173447', fontSize: 16, lineHeight: 24 },
  caption: { flexDirection: 'row', justifyContent: 'space-between', marginTop: 9, gap: 14 },
  hint: { color: '#617D90', fontSize: 11, lineHeight: 17, flexShrink: 1 },
  info: { backgroundColor: '#E5F3FA', borderLeftWidth: 3, borderLeftColor: '#1778A3', padding: 16, borderRadius: 14 },
  error: { color: '#A12020', fontSize: 14, lineHeight: 21 },
  progress: { alignItems: 'center', padding: 12, gap: 12 },
});
