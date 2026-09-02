import React from 'react';
import { Alert, StyleSheet, Text, TextInput, View } from 'react-native';

import { useAuth } from '../auth/AuthContext';
import Button from '../components/Button';
import Screen from '../components/Screen';
import { colours, sharedStyles } from '../theme';

export default function ProfileScreen({ onBack }) {
  const { firebaseUser, logout, profile, saveName } = useAuth();
  const [name, setName] = React.useState(profile?.name || firebaseUser.displayName || '');
  const [busy, setBusy] = React.useState(false);
  const [message, setMessage] = React.useState('');

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
    </Screen>
  );
}

const styles = StyleSheet.create({
  card: { backgroundColor: colours.white, borderRadius: 16, padding: 22 },
  message: { color: colours.blueDark, fontSize: 17, marginBottom: 15 },
  readOnly: { backgroundColor: colours.locked, borderRadius: 10, marginBottom: 16, minHeight: 56, padding: 16 },
  readOnlyText: { color: colours.ink, fontSize: 18, textTransform: 'capitalize' },
  title: { color: colours.ink, fontSize: 29, fontWeight: '700', marginBottom: 22 },
});
