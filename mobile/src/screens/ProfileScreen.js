import React from 'react';
import { Alert, Pressable, StyleSheet, Text, TextInput, View } from 'react-native';

import { useAuth } from '../auth/AuthContext';
import Button from '../components/Button';
import Screen from '../components/Screen';
import DeleteAccountPanel from '../components/DeleteAccountPanel';
import { submitFeedback } from '../services/api';
import { colours, sharedStyles, typography } from '../theme';

export default function ProfileScreen({ onBack, setWorking }) {
  const { firebaseUser, logout, profile, saveName } = useAuth();
  const [name, setName] = React.useState(profile?.name || firebaseUser.displayName || '');
  const [busy, setBusy] = React.useState(false);
  const [deleting, setDeleting] = React.useState(false);
  const [message, setMessage] = React.useState('');

  const [category, setCategory] = React.useState('general_feedback');
  const [rating, setRating] = React.useState(null);
  const [comments, setComments] = React.useState('');
  const [sending, setSending] = React.useState(false);
  const [feedbackMessage, setFeedbackMessage] = React.useState('');

  async function save() {
    if (!name.trim()) return setMessage('Enter your name.');
    setBusy(true);
    setMessage('');
    try {
      await saveName(name);
      setMessage('Your profile has been updated.');
    } catch (error) {
      setMessage(error.message);
    } finally {
      setBusy(false);
    }
  }

  async function sendFeedback() {
    if (rating == null && !comments.trim()) {
      return setFeedbackMessage('Choose a rating or write a comment first.');
    }
    setSending(true);
    setFeedbackMessage('');
    try {
      await submitFeedback(firebaseUser, category, rating, comments.trim() || null);
      setRating(null);
      setComments('');
      setFeedbackMessage('Thank you — your feedback has been sent for review.');
    } catch (error) {
      setFeedbackMessage(error.message);
    } finally {
      setSending(false);
    }
  }

  function confirmLogout() {
    Alert.alert('Sign out?', 'You will need your email and password to sign in again.', [
      { style: 'cancel', text: 'Cancel' },
      { onPress: logout, style: 'destructive', text: 'Sign out' },
    ]);
  }

  return (
    <Screen>
      <View style={styles.card}>
        <Text style={styles.title}>My profile</Text>
        <Text style={sharedStyles.label}>Name</Text>
        <TextInput autoCapitalize="words" onChangeText={setName} style={sharedStyles.field} value={name} />
        <Text style={sharedStyles.label}>Email address</Text>
        <View style={styles.readOnly}><Text style={styles.readOnlyText}>{firebaseUser.email}</Text></View>
        <Text style={sharedStyles.label}>Account type</Text>
        <View style={styles.readOnly}><Text style={styles.readOnlyText}>{profile?.role || 'free'}</Text></View>
        {!!message && <Text accessibilityRole="alert" style={styles.message}>{message}</Text>}
        <Button loading={busy} disabled={deleting} onPress={save}>Save name</Button>
        <Button disabled={busy || deleting} onPress={onBack} secondary>Back to home</Button>
        <Button disabled={busy || deleting} onPress={confirmLogout} secondary>Sign out</Button>
      </View>
      <View style={styles.card}>
        <Text style={styles.title}>Send feedback</Text>
        <Text style={sharedStyles.label}>What is your feedback about?</Text>
        <View style={styles.chipRow}>
          <Pressable
            accessibilityRole="button"
            accessibilityState={{ selected: category === 'general_feedback' }}
            onPress={() => setCategory('general_feedback')}
            style={[styles.chip, category === 'general_feedback' && styles.chipActive]}
          >
            <Text style={[styles.chipText, category === 'general_feedback' && styles.chipTextActive]}>The app in general</Text>
          </Pressable>
          <Pressable
            accessibilityRole="button"
            accessibilityState={{ selected: category === 'service_review' }}
            onPress={() => setCategory('service_review')}
            style={[styles.chip, category === 'service_review' && styles.chipActive]}
          >
            <Text style={[styles.chipText, category === 'service_review' && styles.chipTextActive]}>A check I made</Text>
          </Pressable>
        </View>
        <Text style={sharedStyles.label}>How would you rate UIABO?</Text>
        <View style={styles.chipRow}>
          {[1, 2, 3, 4, 5].map(value => (
            <Pressable
              accessibilityRole="button"
              accessibilityLabel={`${value} out of 5`}
              accessibilityState={{ selected: rating === value }}
              key={value}
              onPress={() => setRating(value)}
              style={[styles.rating, rating != null && rating >= value && styles.ratingActive]}
            >
              <Text style={[styles.ratingText, rating != null && rating >= value && styles.chipTextActive]}>{value}</Text>
            </Pressable>
          ))}
        </View>
        <Text style={sharedStyles.label}>Anything you want to tell us?</Text>
        <TextInput
          multiline
          numberOfLines={3}
          onChangeText={setComments}
          placeholder="Optional, but it helps us improve."
          placeholderTextColor={colours.muted}
          style={[sharedStyles.field, styles.comments]}
          value={comments}
        />
        {!!feedbackMessage && <Text accessibilityRole="alert" style={styles.message}>{feedbackMessage}</Text>}
        <Button loading={sending} disabled={deleting} onPress={sendFeedback}>Send feedback</Button>
      </View>
      <DeleteAccountPanel disabled={busy || sending} setWorking={value => { setDeleting(value); setWorking(value); }} />
    </Screen>
  );
}

const styles = StyleSheet.create({
  card: { backgroundColor: colours.white, borderRadius: 16, marginBottom: 16, padding: 22 },
  message: { ...typography.secondary, color: colours.blueDark, marginBottom: 16 },
  readOnly: { backgroundColor: colours.locked, borderRadius: 10, marginBottom: 16, minHeight: 56, padding: 16 },
  readOnlyText: { ...typography.body, color: colours.ink },
  title: { ...typography.title, color: colours.ink, marginBottom: 24 },
  chipRow: { flexDirection: 'row', flexWrap: 'wrap', gap: 12, marginBottom: 20 },
  chip: { borderRadius: 16, borderWidth: 2, borderColor: colours.blue, minHeight: 56, maxWidth: '100%', paddingHorizontal: 18, paddingVertical: 12, justifyContent: 'center' },
  chipActive: { backgroundColor: colours.blue, borderColor: colours.blue },
  chipText: { ...typography.secondary, color: colours.blue, fontWeight: '600', flexShrink: 1 },
  chipTextActive: { color: colours.white },
  rating: { alignItems: 'center', borderColor: colours.blue, borderRadius: 12, borderWidth: 2, minHeight: 56, justifyContent: 'center', minWidth: 56, padding: 12 },
  ratingActive: { backgroundColor: colours.blue },
  ratingText: { ...typography.button, color: colours.blue },
  comments: { minHeight: 140, textAlignVertical: 'top' },
});
