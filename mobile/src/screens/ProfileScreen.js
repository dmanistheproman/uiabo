import React from 'react';
import { Alert, Pressable, StyleSheet, Text, TextInput, View } from 'react-native';

import { useAuth } from '../auth/AuthContext';
import Button from '../components/Button';
import Screen from '../components/Screen';
import { submitFeedback } from '../services/api';
import { colours, sharedStyles } from '../theme';

export default function ProfileScreen({ onBack }) {
  const { firebaseUser, logout, profile, saveName } = useAuth();
  const [name, setName] = React.useState(profile?.name || firebaseUser.displayName || '');
  const [busy, setBusy] = React.useState(false);
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
        <Button loading={busy} onPress={save}>Save name</Button>
        <Button disabled={busy} onPress={onBack} secondary>Back to home</Button>
        <Button disabled={busy} onPress={confirmLogout} secondary>Sign out</Button>
      </View>
      <View style={styles.card}>
        <Text style={styles.title}>Send feedback</Text>
        <Text style={sharedStyles.label}>What is your feedback about?</Text>
        <View style={styles.chipRow}>
          <Pressable
            accessibilityRole="button"
            onPress={() => setCategory('general_feedback')}
            style={[styles.chip, category === 'general_feedback' && styles.chipActive]}
          >
            <Text style={[styles.chipText, category === 'general_feedback' && styles.chipTextActive]}>The app in general</Text>
          </Pressable>
          <Pressable
            accessibilityRole="button"
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
          style={[sharedStyles.field, styles.comments]}
          value={comments}
        />
        {!!feedbackMessage && <Text accessibilityRole="alert" style={styles.message}>{feedbackMessage}</Text>}
        <Button loading={sending} onPress={sendFeedback}>Send feedback</Button>
      </View>
    </Screen>
  );
}

const styles = StyleSheet.create({
  card: { backgroundColor: colours.white, borderRadius: 16, marginBottom: 16, padding: 22 },
  message: { color: colours.blueDark, fontSize: 17, marginBottom: 15 },
  readOnly: { backgroundColor: colours.locked, borderRadius: 10, marginBottom: 16, minHeight: 56, padding: 16 },
  readOnlyText: { color: colours.ink, fontSize: 18, textTransform: 'capitalize' },
  title: { color: colours.ink, fontSize: 29, fontWeight: '700', marginBottom: 22 },
  chipRow: { flexDirection: 'row', flexWrap: 'wrap', gap: 10, marginBottom: 16 },
  chip: { borderRadius: 999, borderWidth: 1.5, borderColor: colours.blue, minHeight: 48, paddingHorizontal: 18, justifyContent: 'center' },
  chipActive: { backgroundColor: colours.blue, borderColor: colours.blue },
  chipText: { color: colours.blue, fontSize: 17, fontWeight: '600' },
  chipTextActive: { color: colours.white },
  rating: { alignItems: 'center', borderColor: colours.blue, borderRadius: 12, borderWidth: 1.5, height: 48, justifyContent: 'center', width: 48 },
  ratingActive: { backgroundColor: colours.blue },
  ratingText: { color: colours.blue, fontSize: 18, fontWeight: '700' },
  comments: { height: 110, textAlignVertical: 'top' },
});
