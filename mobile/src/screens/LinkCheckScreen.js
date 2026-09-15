import React from 'react';
import { ActivityIndicator, Alert, Keyboard, StyleSheet, Text, TextInput, View } from 'react-native';
import { useAuth } from '../auth/AuthContext';
import { PageBody, PageHeader } from '../components/AppShell';
import Button from '../components/Button';
import { checkLink } from '../services/api';
import { colours } from '../theme';

export default function LinkCheckScreen({ onNavigate, onResult, setWorking }) {
  const { firebaseUser, profile, refreshProfile } = useAuth();
  const [url, setUrl] = React.useState('');
  const [busy, setBusy] = React.useState(false);
  const [error, setError] = React.useState('');
  const requestKey = React.useRef(null);
  const sending = React.useRef(false);
  const remaining = profile?.allowance?.remaining_submissions;

  async function submit() {
    if (sending.current) return;
    const value = url.trim();
    if (!/^https?:\/\/[^\s]+$/i.test(value)) {
      setError('Paste a full webpage URL starting with https:// or http://.');
      return;
    }
    sending.current = true;
    setBusy(true); setWorking(true); setError(''); Keyboard.dismiss();
    requestKey.current ||= `${Date.now().toString(36)}-${Math.random().toString(36).slice(2)}-${Math.random().toString(36).slice(2)}`;
    try {
      const result = await checkLink(firebaseUser, value, requestKey.current);
      await refreshProfile().catch(() => {});
      onResult(result);
    } catch (problem) {
      setError(problem.message);
      if (problem.code && !['ANALYSIS_IN_PROGRESS', 'RESULT_STORAGE_UNAVAILABLE'].includes(problem.code)) requestKey.current = null;
      await refreshProfile().catch(() => {});
    } finally {
      sending.current = false; setBusy(false); setWorking(false);
    }
  }

  return <View style={{ flex: 1 }}>
    <PageHeader title="Check link safety" onBack={() => !busy && onNavigate('home')} badge={remaining == null ? '— left' : `${remaining} left`} />
    <PageBody>
      <View><Text style={styles.title}>Check before you click</Text><Text style={styles.copy}>Look for known phishing, malware and unwanted software threats.</Text></View>
      <View><Text style={styles.label}>Webpage link</Text>
        <TextInput accessibilityLabel="Webpage link" value={url} editable={!busy} maxLength={4096}
          autoCapitalize="none" autoCorrect={false} keyboardType="url" placeholder="https://example.com/page"
          placeholderTextColor="#7D909E" style={styles.input}
          onChangeText={value => { setUrl(value); setError(''); requestKey.current = null; }} />
      </View>
      <View style={styles.info}><Text style={styles.label}>How your link is checked</Text>
        <Text style={styles.copy}>The full URL is sent to Google Web Risk and saved privately in your result history. Only submit public links. Do not submit password-reset links, private invitations or links containing access tokens.</Text>
        <Text style={styles.copy}>This checks for known security threats. To fact-check a webpage's message, copy its text into Check text.</Text>
      </View>
      {!!error && <Text accessibilityRole="alert" style={styles.error}>{error}</Text>}
      {busy ? <View accessibilityLiveRegion="polite" style={styles.progress}><ActivityIndicator size="large" color={colours.blue} /><Text style={styles.label}>Checking Google's threat lists…</Text></View> : <>
        <Button onPress={submit} disabled={remaining === 0 || remaining == null}>Check this link</Button>
        {remaining === 0 && <Text style={styles.error}>You've used your allowance. You can still view saved results.</Text>}
        {remaining == null && <Button secondary onPress={() => refreshProfile().catch(problem => Alert.alert('Could not refresh', problem.message))}>Refresh allowance</Button>}
        <Text style={styles.hint}>Text and link checks share your {profile?.role === 'premium' ? 'monthly' : 'daily'} allowance. Only completed checks use one check; service failures do not.</Text>
        {!!error && <Button secondary onPress={() => onNavigate('results')}>View saved results</Button>}
        <Button secondary onPress={() => onNavigate('text')}>Check copied text instead</Button>
      </>}
    </PageBody>
  </View>;
}

const styles = StyleSheet.create({
  title: { color: '#173447', fontSize: 25, fontWeight: '800', marginBottom: 6 },
  copy: { color: '#526F83', lineHeight: 22, fontSize: 14 },
  label: { color: '#173447', fontWeight: '700', fontSize: 15, marginBottom: 8 },
  input: { backgroundColor: 'white', borderColor: '#B8CDD9', borderWidth: 1, borderRadius: 14, padding: 16, color: '#173447', fontSize: 16, minHeight: 60 },
  info: { backgroundColor: '#E5F3FA', borderLeftWidth: 3, borderLeftColor: '#1778A3', padding: 16, borderRadius: 14, gap: 10 },
  error: { color: '#A12020', fontSize: 14, lineHeight: 21 },
  progress: { alignItems: 'center', padding: 18, gap: 14 },
  hint: { color: '#617D90', fontSize: 12, lineHeight: 19 },
});
