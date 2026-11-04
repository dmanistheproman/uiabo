import React from 'react';
import { StyleSheet, Text, View } from 'react-native';

import { useAuth } from '../auth/AuthContext';
import Button from '../components/Button';
import Screen from '../components/Screen';
import { colours, typography } from '../theme';

export default function VerifyEmailScreen() {
  const { checkVerification, firebaseUser, logout, resendVerification } = useAuth();
  const [busy, setBusy] = React.useState(false);
  const [message, setMessage] = React.useState('');

  async function run(action, successMessage = '') {
    setBusy(true);
    setMessage('');
    try {
      const verified = await action();
      if (verified === false) {
        setMessage('Your email is not verified yet. Open the link in the email, then try again.');
      } else if (successMessage) setMessage(successMessage);
    } catch (error) {
      setMessage(error.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <Screen>
      <View style={styles.card}>
        <Text style={styles.icon}>✉</Text>
        <Text style={styles.title}>Verify your email</Text>
        <Text style={styles.body}>
          We sent a verification link to {firebaseUser.email}. Open the link before using UIABO.
        </Text>
        {!!message && <Text accessibilityRole="alert" style={styles.message}>{message}</Text>}
        <Button loading={busy} onPress={() => run(checkVerification)}>I have verified my email</Button>
        <Button disabled={busy} onPress={() => run(resendVerification, 'A new verification email has been sent.')} secondary>
          Send the email again
        </Button>
        <Button disabled={busy} onPress={logout} secondary>Use a different account</Button>
      </View>
    </Screen>
  );
}

const styles = StyleSheet.create({
  body: { ...typography.body, color: colours.text, marginBottom: 24 },
  card: { backgroundColor: colours.white, borderRadius: 16, padding: 24 },
  icon: { fontSize: 52, textAlign: 'center' },
  message: { ...typography.secondary, color: colours.blueDark, marginBottom: 16 },
  title: { ...typography.title, color: colours.ink, marginBottom: 16 },
});
