import React from 'react';
import { Pressable, StyleSheet, Text, TextInput, View } from 'react-native';

import { useAuth } from '../auth/AuthContext';
import Button from '../components/Button';
import Screen from '../components/Screen';
import { colours, sharedStyles, typography } from '../theme';

export default function AuthScreen() {
  const { login, register, resetPassword, sessionNotice } = useAuth();
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
      {!!sessionNotice && <Text accessibilityRole="alert" style={styles.subtitle}>{sessionNotice}</Text>}
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
            <Pressable accessibilityRole="button" onPress={() => changeMode('reset')} style={styles.linkButton}><Text style={styles.link}>Forgot password?</Text></Pressable>
          </>
        ) : (
          <Button onPress={() => changeMode('login')} secondary>Back to sign in</Button>
        )}
      </View>
    </Screen>
  );
}

const styles = StyleSheet.create({
  brand: { color: colours.blueDark, fontSize: 40, lineHeight: 50, fontWeight: '800', textAlign: 'center' },
  card: { backgroundColor: colours.white, borderColor: colours.divider, borderRadius: 16, borderWidth: 1, marginTop: 24, padding: 20 },
  checkbox: { alignItems: 'center', alignSelf: 'flex-start', borderColor: colours.blue, borderRadius: 4, borderWidth: 2, minHeight: 32, justifyContent: 'center', marginRight: 12, minWidth: 32, padding: 2 },
  checkboxChecked: { backgroundColor: colours.blue },
  checkmark: { ...typography.label, color: colours.white },
  consentRow: { flexDirection: 'row', minHeight: 56, marginBottom: 20, paddingVertical: 8 },
  consentText: { ...typography.secondary, color: colours.ink, flex: 1 },
  error: { ...typography.secondary, color: colours.danger, marginBottom: 16 },
  linkButton: { minHeight: 56, padding: 12, justifyContent: 'center' },
  link: { ...typography.secondary, color: colours.blue, textAlign: 'center', textDecorationLine: 'underline' },
  subtitle: { ...typography.body, color: colours.muted, marginTop: 8, textAlign: 'center' },
  success: { ...typography.secondary, color: colours.success, marginBottom: 16 },
  title: { ...typography.title, color: colours.ink, marginBottom: 24 },
});
