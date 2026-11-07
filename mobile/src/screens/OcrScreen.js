import React from 'react';
import { ActivityIndicator, Alert, Image, Keyboard, StyleSheet, Text, TextInput, View } from 'react-native';
import { chooseImageFor } from '../services/imagePicker';
import { useAuth } from '../auth/AuthContext';
import { PageBody, PageHeader } from '../components/AppShell';
import Button from '../components/Button';
import FeatureExplanation from '../components/FeatureExplanation';
import { checkText, readImageText } from '../services/api';
import { colours, typography } from '../theme';

const MAX_BASE64_LENGTH = 4 * Math.ceil(8 * 1024 * 1024 / 3);

export default function OcrScreen({ initialSelection = null, onNavigate, onResult, setWorking }) {
  const { firebaseUser, profile, refreshProfile } = useAuth();
  const [asset, setAsset] = React.useState(null);
  const [text, setText] = React.useState('');
  const [extracted, setExtracted] = React.useState(false);
  const [warnings, setWarnings] = React.useState([]);
  const [busy, setBusy] = React.useState('');
  const [error, setError] = React.useState('');
  const sending = React.useRef(false);
  const requestKey = React.useRef(null);
  const premium = profile?.role === 'premium';
  const remaining = profile?.allowance?.remaining_submissions;

  function acceptSelection(selection) {
    if (!selection || selection.canceled) return;
    if (selection.code) { setError('The selected image could not be opened. Please select it again.'); return; }
    const selected = selection.assets?.[0];
    if (!selected?.base64) { setError('The selected image could not be read. Choose a JPEG or PNG screenshot.'); return; }
    if (selected.base64.length > MAX_BASE64_LENGTH) { setError('Choose an image smaller than 8 MB.'); return; }
    setAsset(selected); setText(''); setExtracted(false); setWarnings([]); setError(''); requestKey.current = null;
  }

  React.useEffect(() => {
    if (initialSelection) acceptSelection(initialSelection);
  }, [initialSelection]);

  async function chooseImage() {
    if (sending.current) return;
    sending.current = true; setBusy('selecting'); setWorking(true); setError('');
    try {
      acceptSelection(await chooseImageFor(firebaseUser.uid, 'ocr', {
        mediaTypes: ['images'], allowsMultipleSelection: false, allowsEditing: false,
        quality: 1, base64: true, exif: false,
      }));
    } catch { setError('The photo picker could not open. Please try again.'); }
    finally { sending.current = false; setBusy(''); setWorking(false); }
  }

  async function extract() {
    if (sending.current || !asset) return;
    sending.current = true; setBusy('reading'); setWorking(true); setError(''); Keyboard.dismiss();
    try {
      const result = await readImageText(firebaseUser, asset.base64);
      setText(result.text); setWarnings(result.warnings || []); setExtracted(true); requestKey.current = null;
    } catch (problem) { setError(problem.message); }
    finally { sending.current = false; setBusy(''); setWorking(false); }
  }

  async function submit() {
    if (sending.current) return;
    if (!text.trim()) { setError('Keep some text from the image to check.'); return; }
    if (text.length > 5000) { setError('Shorten the text to 5,000 characters before checking.'); return; }
    sending.current = true; setBusy('checking'); setWorking(true); setError(''); Keyboard.dismiss();
    requestKey.current ||= `${Date.now().toString(36)}-${Math.random().toString(36).slice(2)}-${Math.random().toString(36).slice(2)}`;
    try {
      const result = await checkText(firebaseUser, text, requestKey.current, 'ocr');
      await refreshProfile().catch(() => {});
      onResult(result);
    } catch (problem) {
      setError(problem.message);
      if (problem.code && !['ANALYSIS_IN_PROGRESS', 'RESULT_STORAGE_UNAVAILABLE'].includes(problem.code)) requestKey.current = null;
      await refreshProfile().catch(() => {});
    } finally { sending.current = false; setBusy(''); setWorking(false); }
  }

  return <View style={{ flex: 1 }}>
    <PageHeader title="Read image text" onBack={() => !busy && onNavigate('home')} badge={premium ? `${remaining ?? '—'} left` : 'Premium'} />
    <PageBody>
      {!premium ? <View style={styles.card}><Text style={styles.heading}>{profile ? 'A Premium feature' : 'Loading your account'}</Text><Text style={styles.copy}>Premium accounts can extract text from screenshots and photos, review it and check the message.</Text><Button secondary onPress={() => profile ? onNavigate('premium') : refreshProfile().catch(problem => setError(problem.message))}>{profile ? 'View Premium' : 'Refresh account'}</Button>{!!error && <Text style={styles.error}>{error}</Text>}</View> : <>
        <View><Text style={styles.heading}>{extracted ? 'Review the words before checking' : 'Start with a clear screenshot'}</Text><Text style={styles.copy}>Choose a short English message. Review the extracted words before checking.</Text></View>
        {!!asset && <Image accessibilityLabel="Selected image for comparison with extracted text" source={{ uri: asset.uri }} style={styles.preview} resizeMode="contain" />}
        {!busy && <Button secondary onPress={chooseImage}>{asset ? 'Choose a different image' : 'Choose image'}</Button>}
        {!!asset && !extracted && !busy && <Button onPress={extract}>Read text from image</Button>}
        {extracted && <>
          {!!warnings.length && <View style={styles.info}>{warnings.map((warning, index) => <Text key={index} style={styles.copy}>{warning}</Text>)}</View>}
          <View><Text style={styles.label}>Review and edit extracted text</Text>
            <TextInput accessibilityLabel="Review and edit extracted text" value={text} multiline textAlignVertical="top" editable={!busy}
              style={styles.input} onChangeText={value => { setText(value); setError(''); requestKey.current = null; }} />
            <Text style={[styles.hint, text.length > 5000 && styles.error]}>{text.length.toLocaleString()} / 5,000 characters for fact-checking</Text>
          </View>
          {!busy && <>
            <Button onPress={submit} disabled={remaining == null || remaining === 0 || !text.trim() || text.length > 5000}>Check this text</Button>
            {remaining === 0 && <Text style={styles.error}>You've used your allowance. You can still review the extracted text.</Text>}
            {remaining == null && <Button secondary onPress={() => refreshProfile().catch(problem => setError(problem.message))}>Refresh allowance</Button>}
            <Text style={styles.hint}>Your reviewed text and completed assessment will be saved in Results. Only completed fact-checks use your allowance.</Text>
          </>}
        </>}
        {!!busy && <View accessibilityLiveRegion="polite" style={styles.progress}><ActivityIndicator size="large" color={colours.blue} /><Text style={styles.label}>{busy === 'checking' ? 'Checking the claim and its sources…' : busy === 'reading' ? 'Reading the image…' : 'Opening your photos…'}</Text><Text style={styles.copy}>{busy === 'checking' ? 'This may take a couple of minutes. Keep this screen open.' : 'Keep this screen open while the request finishes.'}</Text></View>}
        {!!error && <Text accessibilityRole="alert" style={styles.error}>{error}</Text>}
        {!!error && extracted && !busy && <Button secondary onPress={() => onNavigate('results')}>View saved results</Button>}
        <FeatureExplanation>
          <Text style={styles.copy}>Read the words, correct any mistakes, then check the message. Reading text uses no checks; a completed fact-check uses one.</Text>
          <Text style={styles.copy}>The image is not saved. Your reviewed text and result are saved after a completed check. Avoid images containing private information.</Text>
        </FeatureExplanation>
      </>}
    </PageBody>
  </View>;
}

const styles = StyleSheet.create({
  heading: { ...typography.title, color: colours.ink, marginBottom: 8 },
  copy: { ...typography.body, color: colours.text },
  label: { ...typography.label, color: colours.ink, marginBottom: 8 },
  preview: { width: '100%', height: 240, backgroundColor: colours.infoBackground, borderRadius: 14 },
  card: { backgroundColor: colours.white, padding: 20, borderRadius: 16, gap: 16 },
  info: { backgroundColor: colours.infoBackground, borderLeftWidth: 3, borderLeftColor: colours.blue, borderRadius: 14, padding: 18, gap: 12 },
  input: { ...typography.body, backgroundColor: colours.white, minHeight: 240, borderColor: colours.border, borderWidth: 2, borderRadius: 14, padding: 16, color: colours.ink },
  hint: { ...typography.secondary, color: colours.muted, marginTop: 8 },
  error: { ...typography.secondary, color: colours.danger },
  progress: { alignItems: 'center', gap: 12, padding: 14 },
});
