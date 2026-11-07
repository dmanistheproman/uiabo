import React from 'react';
import { ActivityIndicator, Image, Keyboard, StyleSheet, Text, TextInput, View } from 'react-native';
import { useAuth } from '../auth/AuthContext';
import { PageBody, PageHeader } from '../components/AppShell';
import Button from '../components/Button';
import FeatureExplanation from '../components/FeatureExplanation';
import { checkImageContext } from '../services/api';
import { chooseImageFor } from '../services/imagePicker';
import { confirmedImageFailure, imageInputError } from '../utils/inputFlows';
import { colours, typography } from '../theme';

export default function ImageContextScreen({ onNavigate, onResult, setWorking, initialSelection = null }) {
  const { firebaseUser, profile, refreshProfile } = useAuth();
  const [selectedImage, setSelectedImage] = React.useState(null);
  const [caption, setCaption] = React.useState('');
  const [busy, setBusy] = React.useState('');
  const [error, setError] = React.useState('');
  const sending = React.useRef(false);
  const requestKey = React.useRef(null);
  const premium = profile?.role === 'premium';
  const remaining = profile?.allowance?.remaining_submissions;

  function acceptSelection(selection) {
    if (!selection || selection.canceled) return;
    const asset = selection.assets?.[0];
    const problem = selection.code ? 'The selected image could not be opened. Please choose it again.' : imageInputError(asset);
    if (problem) { setError(problem); return; }
    setSelectedImage(asset); setError(''); requestKey.current = null;
  }

  React.useEffect(() => { acceptSelection(initialSelection); }, [initialSelection]);

  async function chooseImage() {
    if (sending.current) return;
    sending.current = true; setBusy('selecting'); setWorking(true); setError('');
    try {
      acceptSelection(await chooseImageFor(firebaseUser.uid, 'imageContext', {
        mediaTypes: ['images'], allowsMultipleSelection: false, allowsEditing: false, quality: 1,
      }));
    } catch { setError('Could not open your images. Please try again.'); }
    finally { sending.current = false; setBusy(''); setWorking(false); }
  }

  async function analyseImage() {
    if (sending.current || !selectedImage || !premium) return;
    if (caption.length > 5000) return setError('Keep the caption within 5,000 characters.');
    sending.current = true; setBusy('analysing'); setWorking(true); setError(''); Keyboard.dismiss();
    requestKey.current ||= `${Date.now()}-${Math.random().toString(36).slice(2)}`;
    try {
      const result = await checkImageContext(firebaseUser, selectedImage, requestKey.current, caption);
      requestKey.current = null;
      await refreshProfile().catch(() => {});
      onResult(result);
    } catch (problem) {
      setError(problem.message);
      if (confirmedImageFailure(problem.code)) requestKey.current = null;
      await refreshProfile().catch(() => {});
    } finally { sending.current = false; setBusy(''); setWorking(false); }
  }

  return <View style={{ flex: 1 }}>
    <PageHeader title="Check image context" onBack={() => !busy && onNavigate('home')}
      badge={premium ? `${remaining ?? '—'} left` : 'Premium'} />
    <PageBody>
      {!premium ? <View style={styles.card}>
        <Text style={styles.heading}>{profile ? 'A Premium feature' : 'Load your account'}</Text>
        <Text style={styles.copy}>Check an image together with its caption, or read the caption from a screenshot.</Text>
        <Button secondary onPress={() => profile ? onNavigate('premium') : refreshProfile().catch(problem => setError(problem.message))}>
          {profile ? 'View Premium' : 'Refresh account'}
        </Button>
      </View> : <>
        <Text style={styles.heading}>Check the image and its message</Text>
        <Text style={styles.copy}>Choose a photo and add its caption, or select a screenshot with the caption already visible.</Text>
        <Text style={styles.hint}>PNG or JPEG, up to 10 MB and 25 megapixels.</Text>
        {selectedImage && <View style={styles.card}>
          <Image accessibilityLabel="Selected image preview" source={{ uri: selectedImage.uri }} resizeMode="contain" style={styles.preview} />
          <Text style={styles.copy}>{selectedImage.fileName || 'Selected image'}</Text>
        </View>}
        <Button secondary disabled={Boolean(busy)} onPress={chooseImage}>{selectedImage ? 'Choose another image' : 'Choose image'}</Button>
        {selectedImage && <Button secondary disabled={Boolean(busy)} onPress={() => { setSelectedImage(null); requestKey.current = null; }}>Remove image</Button>}
        <Text style={styles.label}>Caption or message (optional)</Text>
        <TextInput accessibilityLabel="Caption or message for this image" multiline textAlignVertical="top" editable={!busy} maxLength={5000}
          style={styles.input} value={caption} placeholder="What does the post say about this image?" placeholderTextColor={colours.muted}
          onChangeText={value => { setCaption(value); setError(''); requestKey.current = null; }} />
        <Text style={styles.hint}>{caption.length.toLocaleString()} / 5,000 characters</Text>
        <Text style={styles.copy}>Leave blank to read the caption from your screenshot.</Text>
        <Button loading={busy === 'analysing'} disabled={!selectedImage || Boolean(busy) || remaining == null || remaining === 0} onPress={analyseImage}>Check image and caption</Button>
        <FeatureExplanation>
          <Text style={styles.copy}>Checks the image and its message against published evidence. It cannot prove the original date, location or whether the image was AI-generated.</Text>
          <Text style={styles.copy}>Results are saved privately. If image saving is enabled, your image is saved too and can be removed from the result. Avoid private images.</Text>
        </FeatureExplanation>
        {remaining === 0 && <Text style={styles.error}>You have used your allowance. You can still view saved results.</Text>}
        {remaining == null && <Button secondary disabled={Boolean(busy)} onPress={() => refreshProfile().catch(problem => setError(problem.message))}>Refresh allowance</Button>}
        {!!busy && <View accessibilityLiveRegion="polite" style={styles.progress}><ActivityIndicator /><Text style={styles.copy}>{busy === 'selecting' ? 'Opening your images…' : 'Checking the image and message. This may take a few minutes.'}</Text></View>}
        <Text style={styles.hint}>Only completed checks use your allowance. Failed checks do not.</Text>
      </>}
      {!!error && <Text accessibilityRole="alert" style={styles.error}>{error}</Text>}
      {!!error && !busy && <Button secondary onPress={() => onNavigate('results')}>View saved results</Button>}
    </PageBody>
  </View>;
}

const styles = StyleSheet.create({
  heading: { ...typography.title, color: colours.ink },
  label: { ...typography.label, color: colours.ink },
  copy: { ...typography.body, color: colours.text },
  hint: { ...typography.secondary, color: colours.muted },
  input: { ...typography.body, minHeight: 160, backgroundColor: colours.white, borderColor: colours.border, borderWidth: 2, borderRadius: 14, padding: 16, color: colours.ink },
  card: { backgroundColor: colours.white, borderRadius: 16, padding: 18, gap: 12 },
  preview: { width: '100%', height: 240, backgroundColor: colours.infoBackground, borderRadius: 12 },
  error: { ...typography.secondary, color: colours.danger },
  progress: { gap: 12, alignItems: 'center' },
});
