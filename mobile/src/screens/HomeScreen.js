import React from 'react';
import { Alert, Pressable, RefreshControl, StyleSheet, Text, View } from 'react-native';
import { LinearGradient } from 'expo-linear-gradient';
import Feather from '@expo/vector-icons/Feather';
import { useAuth } from '../auth/AuthContext';
import { PageBody, PageHeader } from '../components/AppShell';
import { colours } from '../theme';

const features = [
  { icon: 'Aa', label: 'Check text', colour: '#E5F3FA', ink: '#164D73', page: 'text' },
  { icon: 'URL', label: 'Check webpage\nlink', colour: '#E2F4F0', ink: '#008980', page: 'link' },
  { icon: 'IMG', label: 'Image + caption', colour: '#FFF3D7', ink: '#946100', locked: true },
  { icon: 'OCR', label: 'Read image text', colour: '#FFF3D7', ink: '#946100', locked: true },
  { icon: 'CTX', label: 'Check image\ncontext', colour: '#EEE9F9', ink: '#7952AE', locked: true },
  { icon: 'AI', label: 'Check AI image', colour: '#EEE9F9', ink: '#7952AE', locked: true },
];

export default function HomeScreen({ onNavigate }) {
  const { firebaseUser, profile, refreshProfile } = useAuth();
  const [refreshing, setRefreshing] = React.useState(false);
  const name = profile?.name || firebaseUser.displayName || 'there';
  const firstName = name.split(' ')[0];
  const initials = name.split(' ').slice(0, 2).map(part => part[0]).join('').toUpperCase();
  const remaining = profile?.allowance?.remaining_submissions;
  const premium = profile?.role === 'premium';
  const hour = new Date().getHours();
  const greeting = hour < 12 ? 'Good morning' : hour < 18 ? 'Good afternoon' : 'Good evening';
  async function refresh() {
    setRefreshing(true);
    try { await refreshProfile(); } catch (error) { Alert.alert('Could not refresh', error.message); }
    finally { setRefreshing(false); }
  }
  return <View style={{ flex: 1 }}>
    <PageHeader><View style={styles.account}>
      <Text style={styles.plan}>{profile?.role === 'premium' ? 'Premium' : 'Free'}</Text>
      <Pressable accessibilityRole="button" accessibilityLabel="Open profile" onPress={() => onNavigate('profile')} style={styles.avatar}><Text style={styles.initials}>{initials}</Text></Pressable>
    </View></PageHeader>
    <PageBody refreshControl={<RefreshControl refreshing={refreshing} onRefresh={refresh} />}>
      <View><Text style={styles.greeting}>{greeting}, {firstName}</Text><Text style={styles.subtitle}>What would you like to check?</Text></View>
      <LinearGradient colors={['#123D5C', '#176F9C']} start={{ x: 0, y: 0 }} end={{ x: 1, y: 1 }} style={styles.allowance}>
        <View style={{ flex: 1 }}><Text style={styles.allowanceLabel}>{premium ? "This month's allowance" : "Today's allowance"}</Text>
          <View style={styles.allowanceRow}><Text style={styles.number}>{remaining ?? '—'}</Text><Text style={styles.available}>{remaining === 1 ? 'check available' : 'checks available'}</Text></View>
          <View style={styles.track}><View style={[styles.fill, { width: `${Math.min(100, 100 * (remaining || 0) / (profile?.allowance?.submission_limit || 1))}%` }]} /></View>
        </View><Feather name={remaining === 0 ? 'clock' : 'check'} color="white" size={28} />
      </LinearGradient>
      {!profile && <Pressable onPress={refresh} accessibilityRole="button"><Text style={styles.notice}>Your allowance could not be loaded. Tap to retry.</Text></Pressable>}
      {remaining === 0 && <Text style={styles.subtitle}>Your allowance resets {profile?.allowance?.reset_at ? `${new Date(profile.allowance.reset_at).toLocaleString([], { timeZone: 'Asia/Singapore', month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' })} SGT` : 'at the next reset'}.</Text>}
      <View style={styles.grid}>{features.map(feature => <Pressable key={feature.icon} accessibilityRole="button"
        accessibilityLabel={`${feature.label.replace('\n', ' ')}${feature.locked ? premium ? ', coming soon' : ', premium feature' : ''}`}
        onPress={() => onNavigate(feature.locked ? 'premium' : feature.page)}
        style={({ pressed }) => [styles.tile, feature.locked && styles.locked, pressed && { opacity: 0.7 }]}>
        <View style={styles.tileTop}><View style={[styles.icon, { backgroundColor: feature.colour }]}><Text style={[styles.iconText, { color: feature.ink }]}>{feature.icon}</Text></View>
          {feature.locked && <Text style={styles.lock}>{premium ? 'SOON' : 'LOCK'}</Text>}</View>
        <Text style={[styles.tileLabel, feature.locked && { color: '#657A88' }]}>{feature.label}</Text>
      </Pressable>)}</View>
      <Pressable accessibilityRole="button" onPress={() => onNavigate('premium')} style={styles.upgrade}>
        <Text style={styles.upgradeText}>{premium ? <><Text style={{ fontWeight: '700' }}>Premium active</Text> · 60 checks each month. Image checks are coming soon.</> : <><Text style={{ fontWeight: '700' }}>Unlock image checks</Text> · Upgrade to Premium for SGD 20/month.</>}</Text>
      </Pressable>
    </PageBody>
  </View>;
}

const styles = StyleSheet.create({
  account: { flexDirection: 'row', alignItems: 'center', gap: 10 },
  plan: { backgroundColor: '#E5F3FA', color: colours.blueDark, borderRadius: 16, paddingHorizontal: 11, paddingVertical: 6, fontSize: 12, fontWeight: '700' },
  avatar: { width: 42, height: 42, borderRadius: 12, borderWidth: 1, borderColor: '#DCE5EB', justifyContent: 'center', alignItems: 'center' },
  initials: { color: colours.blueDark, fontSize: 15, fontWeight: '800' },
  greeting: { color: '#173447', fontSize: 24, fontWeight: '800', letterSpacing: -0.5 },
  subtitle: { color: '#667F90', fontSize: 13, lineHeight: 19, marginTop: 3 },
  allowance: { borderRadius: 18, minHeight: 106, padding: 18, flexDirection: 'row', alignItems: 'center', gap: 18 },
  allowanceLabel: { color: '#DAEAF3', fontSize: 12, fontWeight: '500' },
  allowanceRow: { flexDirection: 'row', alignItems: 'baseline', gap: 7 },
  number: { color: 'white', fontSize: 32, fontWeight: '800' },
  available: { color: 'white', fontSize: 13 },
  track: { height: 5, backgroundColor: '#91B6C6', marginTop: 1, borderRadius: 5, overflow: 'hidden' },
  fill: { height: 5, backgroundColor: 'white' },
  grid: { flexDirection: 'row', flexWrap: 'wrap', gap: 10 },
  tile: { width: '48.4%', flexGrow: 1, minHeight: 115, padding: 14, borderRadius: 16, borderWidth: 1, borderColor: '#D9E4EA', backgroundColor: 'white', justifyContent: 'space-between', gap: 12 },
  tileTop: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'flex-start' },
  icon: { width: 42, height: 42, borderRadius: 11, alignItems: 'center', justifyContent: 'center' },
  iconText: { fontWeight: '900', fontSize: 14 },
  tileLabel: { color: '#173447', fontSize: 14, fontWeight: '800', lineHeight: 18 },
  locked: { backgroundColor: '#EFF3F4' },
  lock: { fontSize: 7, color: '#9A750B', backgroundColor: '#FFF6D8', padding: 5, borderRadius: 7 },
  upgrade: { backgroundColor: '#FFF4D2', borderLeftWidth: 3, borderLeftColor: '#D49A00', borderRadius: 13, padding: 14 },
  upgradeText: { color: '#80600A', lineHeight: 18, fontSize: 12 },
  notice: { color: colours.danger, fontSize: 14 },
});
