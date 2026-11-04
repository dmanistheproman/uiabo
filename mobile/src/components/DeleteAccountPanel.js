import React from 'react';
import { Alert, StyleSheet, Text, TextInput, View } from 'react-native';
import Button from './Button';
import { useAuth } from '../auth/AuthContext';
import { requestAccountDeletion } from '../services/api';
import { deleteAfterVerification } from '../utils/inputFlows';
import { colours, sharedStyles, typography } from '../theme';

export default function DeleteAccountPanel({ setWorking = () => {}, disabled = false }) {
  const { firebaseUser, profile, verifyPassword, logout, markDeletionRequested } = useAuth();
  const [expanded, setExpanded] = React.useState(false);
  const [password, setPassword] = React.useState('');
  const [busy, setBusy] = React.useState(false);
  const [accepted, setAccepted] = React.useState(false);
  const [error, setError] = React.useState('');
  const sending = React.useRef(false);
  if (!['free', 'premium'].includes(profile?.role) || profile?.operational_roles?.length) return null;

  async function submit() {
    if (sending.current || disabled) return;
    sending.current = true;
    setBusy(true); setWorking(true); setError('');
    try {
      await deleteAfterVerification({ password, verify: verifyPassword,
        requestDeletion: () => requestAccountDeletion(firebaseUser), logout,
        onAccepted: () => {
          setAccepted(true);
          markDeletionRequested('Account deletion requested. Your account is unavailable while your saved data is removed. Cleanup may take several minutes.');
        },
      });
    } catch (problem) {
      setError(problem.message);
    } finally {
      setPassword(''); setBusy(false); sending.current = false;
      // An accepted deletion keeps this session locked until it signs out.
      // AuthProvider also presents a dedicated accepted-deletion screen.
      setWorking(false);
    }
  }

  function confirm() {
    if (sending.current || disabled) return;
    if (!password) return setError('Enter your current password to confirm it is you.');
    Alert.alert('Permanently delete your account?',
      'Your account, saved results, saved images, feedback and result reports will be removed. This cannot be undone.', [
        { text: 'Keep my account', style: 'cancel' },
        { text: 'Delete my account', style: 'destructive', onPress: submit },
      ]);
  }

  return <View style={styles.card}>
    <Text style={styles.heading}>Delete account</Text>
    {accepted ? <>
      <Text accessibilityRole="alert" style={styles.copy}>Deletion requested. Your account is unavailable while cleanup finishes.</Text>
      <Button secondary onPress={() => logout().catch(() => setError('Could not sign out. Please try again.'))}>Sign out</Button>
    </> : <>
      <Text style={styles.copy}>Permanently remove your account and saved data.</Text>
      {!expanded ? <Button secondary onPress={() => setExpanded(true)}>Delete my account</Button> : <>
        <Text style={styles.copy}>This removes your saved checks, images, feedback and incorrect-result reports. Once accepted, you will be signed out while deletion completes. This cannot be undone.</Text>
        <Text style={styles.label}>Current password</Text>
        <TextInput accessibilityLabel="Current password for account deletion" secureTextEntry autoCapitalize="none"
          autoCorrect={false} autoComplete="current-password" editable={!busy} value={password}
          onChangeText={value => { setPassword(value); setError(''); }} style={styles.input} />
        <Button loading={busy} disabled={disabled} onPress={confirm}>Continue to deletion confirmation</Button>
        <Button disabled={busy} secondary onPress={() => { setPassword(''); setError(''); setExpanded(false); }}>Keep my account</Button>
      </>}
    </>}
    {!!error && <Text accessibilityRole="alert" style={styles.error}>{error}</Text>}
  </View>;
}

const styles = StyleSheet.create({
  card: { backgroundColor: colours.white, borderColor: colours.danger, borderWidth: 1, borderRadius: 16, padding: 22, gap: 16, marginBottom: 16 },
  heading: { ...typography.heading, color: colours.danger },
  copy: { ...typography.body, color: colours.text },
  label: { ...typography.label, color: colours.ink },
  input: { ...sharedStyles.field, marginBottom: 0 },
  error: { ...typography.secondary, color: colours.danger },
});
