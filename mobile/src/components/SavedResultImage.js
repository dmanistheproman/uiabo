import { colours, typography } from '../theme';
import React from 'react';
import { ActivityIndicator, Alert, Image, StyleSheet, Text, View } from 'react-native';
import { useAuth } from '../auth/AuthContext';
import { deleteSavedImage, savedImageSource } from '../services/api';
import Button from './Button';

export default function SavedResultImage({ result }) {
  const { firebaseUser } = useAuth();
  const [source, setSource] = React.useState(null);
  const [error, setError] = React.useState('');
  const [removed, setRemoved] = React.useState(false);
  const [busy, setBusy] = React.useState(false);
  const [attempt, setAttempt] = React.useState(0);

  React.useEffect(() => {
    let active = true;
    setSource(null); setError(''); setRemoved(false);
    if (result.saved_image && firebaseUser) {
      savedImageSource(firebaseUser, result.result_id).then(value => {
        if (active) setSource(value);
      }).catch(err => {
        if (active) setError(err.message || 'The saved image could not be loaded.');
      });
    }
    return () => { active = false; };
  }, [firebaseUser?.uid, result.result_id, result.saved_image, attempt]);

  async function remove() {
    setBusy(true); setError('');
    try {
      await deleteSavedImage(firebaseUser, result.result_id);
      setSource(null); setRemoved(true);
    } catch (err) {
      setError(err.message || 'The image could not be removed. Please retry.');
    } finally { setBusy(false); }
  }

  function confirmRemove() {
    Alert.alert('Remove saved image?', 'This removes the image from your history. Your assessment stays available.', [
      { text: 'Cancel', style: 'cancel' },
      { text: 'Remove image', style: 'destructive', onPress: remove },
    ]);
  }

  if (!result.saved_image || removed) return null;
  return <View style={styles.card}>
    <Text style={styles.heading}>Image you checked</Text>
    {source ? <Image key={attempt} source={source} resizeMode="contain"
      accessibilityLabel="Saved image for this assessment" style={styles.image}
      onLoad={() => setError('')}
      onError={() => setError('The saved image could not be loaded.')} />
      : !error && <ActivityIndicator color={colours.blueDark} />}
    {!!error && <><Text accessibilityRole="alert" style={styles.error}>{error}</Text>
      <Button secondary disabled={busy} onPress={() => setAttempt(value => value + 1)}>Reload image</Button></>}
    <Text style={styles.copy}>Saved privately with this result.</Text>
    <Button secondary loading={busy} onPress={confirmRemove}>Remove saved image</Button>
  </View>;
}

const styles = StyleSheet.create({
  card: { backgroundColor: colours.white, padding: 18, borderRadius: 14, gap: 16 },
  heading: { ...typography.heading, color: colours.ink },
  image: { width: '100%', height: 240, backgroundColor: colours.background },
  copy: { ...typography.secondary, color: colours.muted },
  error: { ...typography.secondary, color: colours.danger },
});
