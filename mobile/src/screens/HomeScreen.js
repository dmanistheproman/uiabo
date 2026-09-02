import React from 'react';
import { Alert, Pressable, StyleSheet, Text, View } from 'react-native';

import { useAuth } from '../auth/AuthContext';
import Button from '../components/Button';
import Screen from '../components/Screen';
import { colours } from '../theme';

const features = [
  { description: 'Paste a message or article to check.', name: 'Check text', status: 'Coming next' },
  { description: 'Review checks saved to your account.', name: 'Result history', status: 'Coming next' },
  { description: 'Analyse a picture for misleading content.', locked: true, name: 'Check image', status: 'Premium' },
  { description: 'Analyse an audio recording.', locked: true, name: 'Check audio', status: 'Premium' },
];

export default function HomeScreen({ onOpenProfile }) {
  const { firebaseUser, logout, profile, refreshProfile } = useAuth();
  const [refreshing, setRefreshing] = React.useState(false);

  async function retryProfile() {
    setRefreshing(true);
    try {
      await refreshProfile();
    } catch (error) {
      Alert.alert('Profile unavailable', error.message);
    } finally {
      setRefreshing(false);
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
      <View style={styles.header}>
        <View style={styles.headerText}>
          <Text style={styles.brand}>UIABO</Text>
          <Text style={styles.greeting}>Hello, {profile?.name || firebaseUser.displayName || 'there'}</Text>
        </View>
        <Pressable accessibilityRole="button" onPress={onOpenProfile} style={styles.profileButton}>
          <Text style={styles.profileButtonText}>Profile</Text>
        </Pressable>
      </View>
      {!profile && (
        <View style={styles.warning}>
          <Text style={styles.warningText}>Your account is signed in, but the server profile could not be loaded.</Text>
          <Button loading={refreshing} onPress={retryProfile} secondary>Retry</Button>
        </View>
      )}
      <View style={styles.allowance}>
        <Text style={styles.allowanceTitle}>Free plan</Text>
        <Text style={styles.allowanceText}>{profile?.allowance?.remaining_submissions ?? 1} text check remaining today</Text>
      </View>
      <Text style={styles.sectionTitle}>What would you like to do?</Text>
      {features.map((feature) => (
        <View key={feature.name} style={[styles.feature, feature.locked && styles.locked]}>
          <View style={styles.featureText}>
            <Text style={[styles.featureName, feature.locked && styles.lockedText]}>
              {feature.locked ? '🔒 ' : ''}{feature.name}
            </Text>
            <Text style={[styles.description, feature.locked && styles.lockedText]}>{feature.description}</Text>
          </View>
          <Text style={[styles.status, feature.locked && styles.lockedText]}>{feature.status}</Text>
        </View>
      ))}
      <Button onPress={confirmLogout} secondary>Sign out</Button>
    </Screen>
  );
}

const styles = StyleSheet.create({
  allowance: { backgroundColor: '#E7F3FF', borderRadius: 12, marginBottom: 26, padding: 18 },
  allowanceText: { color: colours.ink, fontSize: 18, marginTop: 4 },
  allowanceTitle: { color: colours.blueDark, fontSize: 21, fontWeight: '700' },
  brand: { color: colours.blueDark, fontSize: 34, fontWeight: '800' },
  description: { color: colours.muted, fontSize: 16, lineHeight: 22, marginTop: 5 },
  feature: { alignItems: 'center', backgroundColor: colours.white, borderColor: colours.border, borderRadius: 12, borderWidth: 1, flexDirection: 'row', marginBottom: 14, minHeight: 96, padding: 17 },
  featureName: { color: colours.ink, fontSize: 21, fontWeight: '700' },
  featureText: { flex: 1 },
  greeting: { color: colours.ink, fontSize: 19, marginTop: 3 },
  header: { alignItems: 'center', flexDirection: 'row', justifyContent: 'space-between', marginBottom: 24 },
  headerText: { flex: 1 },
  locked: { backgroundColor: colours.locked },
  lockedText: { color: '#5C6268' },
  profileButton: { borderColor: colours.blue, borderRadius: 9, borderWidth: 2, paddingHorizontal: 16, paddingVertical: 12 },
  profileButtonText: { color: colours.blue, fontSize: 17, fontWeight: '700' },
  sectionTitle: { color: colours.ink, fontSize: 23, fontWeight: '700', marginBottom: 14 },
  status: { color: colours.blue, fontSize: 15, fontWeight: '700', marginLeft: 10 },
  warning: { backgroundColor: '#FFF4D6', borderRadius: 12, marginBottom: 18, padding: 16 },
  warningText: { color: colours.ink, fontSize: 17, lineHeight: 24, marginBottom: 12 },
});
