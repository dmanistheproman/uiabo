import React from 'react';
import { Pressable, StyleSheet, Text, TextInput, View } from 'react-native';

import { useAuth } from '../auth/AuthContext';
import Button from '../components/Button';
import Screen from '../components/Screen';
import { colours, sharedStyles } from '../theme';

export default function AuthScreen() {
  const { login, register, resetPassword } = useAuth();
  const [mode, setMode] = React.useState('login');
  const [name, setName] = React.useState('');
  const [email, setEmail] = React.useState('');
  const [password, setPassword] = React.useState('');
  const [confirmPassword, setConfirmPassword] = React.useState('');
  const [consent, setConsent] = React.useState(false);
  const [busy, setBusy] = React.useState(false);
  const [message, setMessage] = React.useState('');
  const [error, setError] = React.useState('');

  function changeMode(nextMode) {
    setMode(nextMode);
    setError('');
    setMessage('');
  }

  async function submit() {
    setError('');
    setMessage('');
    if (!email.trim()) return setError('Enter your email address.');
    if (mode === 'register') {
      if (!name.trim()) return setError('Enter your name.');
      if (password.length < 8) return setError('Use a password with at least 8 characters.');
      if (password !== confirmPassword) return setError('The passwords do not match.');
      if (!consent) return setError('Please agree to the privacy notice to create an account.');
    }

    setBusy(true);
    try {
      if (mode === 'login') await login(email, password);
      else if (mode === 'register') await register({ email, name, password });
      else {
        await resetPassword(email);
        setMessage('If an account uses that email, Firebase has sent reset instructions.');
      }
    } catch (caught) {
      setError(caught.message);
    } finally {
      setBusy(false);
    }
  }

  const title = mode === 'login' ? 'Sign in' : mode === 'register' ? 'Create free account' : 'Reset password';

  return (
    <Screen>
      <Text style={styles.brand}>UIABO</Text>
      <Text style={styles.subtitle}>Check information before you share it.</Text>
      <View style={styles.card}>
        <Text style={styles.title}>{title}</Text>
        {mode === 'register' && (
          <>
            <Text style={sharedStyles.label}>Name</Text>
            <TextInput autoCapitalize="words" onChangeText={setName} style={sharedStyles.field} value={name} />
          </>
        )}
        <Text style={sharedStyles.label}>Email address</Text>
        <TextInput autoCapitalize="none" autoComplete="email" inputMode="email" onChangeText={setEmail} style={sharedStyles.field} value={email} />
        {mode !== 'reset' && (
          <>
            <Text style={sharedStyles.label}>Password</Text>
            <TextInput
              autoCapitalize="none"
              autoComplete={mode === 'login' ? 'current-password' : 'new-password'}
              onChangeText={setPassword}
              secureTextEntry
              style={sharedStyles.field}
              value={password}
            />
          </>
        )}
        {mode === 'register' && (
          <>
            <Text style={sharedStyles.label}>Confirm password</Text>
            <TextInput autoCapitalize="none" autoComplete="new-password" onChangeText={setConfirmPassword} secureTextEntry style={sharedStyles.field} value={confirmPassword} />
            <Pressable
              accessibilityRole="checkbox"
              accessibilityState={{ checked: consent }}
              onPress={() => setConsent((current) => !current)}
              style={styles.consentRow}
            >
              <View style={[styles.checkbox, consent && styles.checkboxChecked]}>
                <Text style={styles.checkmark}>{consent ? '✓' : ''}</Text>
              </View>
              <Text style={styles.consentText}>
                I agree that UIABO may store my account and submitted content as explained in the privacy notice.
              </Text>
            </Pressable>
          </>
        )}
        {!!error && <Text accessibilityRole="alert" style={styles.error}>{error}</Text>}
        {!!message && <Text accessibilityRole="alert" style={styles.success}>{message}</Text>}
        <Button loading={busy} onPress={submit}>
          {mode === 'login' ? 'Sign in' : mode === 'register' ? 'Create account' : 'Send reset email'}
        </Button>
        {mode === 'login' ? (
          <>
            <Button onPress={() => changeMode('register')} secondary>Create a free account</Button>
            <Pressable onPress={() => changeMode('reset')}><Text style={styles.link}>Forgot password?</Text></Pressable>
          </>
        ) : (
          <Button onPress={() => changeMode('login')} secondary>Back to sign in</Button>
        )}
      </View>
    </Screen>
  );
}

const styles = StyleSheet.create({
  brand: { color: colours.blueDark, fontSize: 40, fontWeight: '800', textAlign: 'center' },
  card: { backgroundColor: colours.white, borderColor: colours.border, borderRadius: 16, borderWidth: 1, marginTop: 24, padding: 20 },
  checkbox: { alignItems: 'center', borderColor: colours.blue, borderRadius: 4, borderWidth: 2, height: 28, justifyContent: 'center', marginRight: 12, width: 28 },
  checkboxChecked: { backgroundColor: colours.blue },
  checkmark: { color: colours.white, fontSize: 19, fontWeight: '800' },
  consentRow: { flexDirection: 'row', marginBottom: 18 },
  consentText: { color: colours.ink, flex: 1, fontSize: 16, lineHeight: 23 },
  error: { color: colours.danger, fontSize: 17, marginBottom: 14 },
  link: { color: colours.blue, fontSize: 17, padding: 12, textAlign: 'center' },
  subtitle: { color: colours.muted, fontSize: 19, marginTop: 6, textAlign: 'center' },
  success: { color: colours.success, fontSize: 17, marginBottom: 14 },
  title: { color: colours.ink, fontSize: 28, fontWeight: '700', marginBottom: 22 },
});
