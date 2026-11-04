import React from 'react';
import { Alert, Pressable, RefreshControl, StyleSheet, Text, View, useWindowDimensions } from 'react-native';
import { LinearGradient } from 'expo-linear-gradient';
import Feather from '@expo/vector-icons/Feather';
import { useAuth } from '../auth/AuthContext';
import { PageBody, PageHeader } from '../components/AppShell';
import { colours, typography } from '../theme';

const features = [
  { icon: 'type', label: 'Check text', colour: colours.infoBackground, ink: colours.blueDark, page: 'text' },
  { icon: 'link', label: 'Check link safety', colour: colours.successBackground, ink: colours.teal, page: 'link' },
  { icon: 'file-text', label: 'Read image text', colour: colours.warningBackground, ink: colours.warning, page: 'ocr', premiumOnly: true },
  { icon: 'image', label: 'Check image context', colour: colours.infoBackground, ink: colours.blueDark, page: 'imageContext', premiumOnly: true },
  { icon: 'eye', label: 'Deepfake / AI image check', colour: colours.infoBackground, ink: colours.blueDark, page: 'deepfakeAI', premiumOnly: true },
];

export default function HomeScreen({ onNavigate }) {
  const { fontScale } = useWindowDimensions();
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
      <LinearGradient colors={[colours.blueDark, '#14577D']} start={{ x: 0, y: 0 }} end={{ x: 1, y: 1 }} style={styles.allowance}>
        <View style={{ flex: 1 }}><Text style={styles.allowanceLabel}>{premium ? "This month's allowance" : "Today's allowance"}</Text>
          <View style={styles.allowanceRow}><Text style={styles.available}>{remaining === 1 ? 'Check available:' : 'Checks available:'}</Text><Text style={styles.number}>{remaining ?? '—'}</Text></View>
          <View style={styles.track}><View style={[styles.fill, { width: `${Math.min(100, 100 * (remaining || 0) / (profile?.allowance?.submission_limit || 1))}%` }]} /></View>
        </View><Feather name={remaining === 0 ? 'clock' : 'check'} color="white" size={28} />
      </LinearGradient>
      {!profile && <Pressable onPress={refresh} accessibilityRole="button" style={styles.retry}><Text style={styles.notice}>Your allowance could not be loaded. Tap to retry.</Text></Pressable>}
      {remaining === 0 && <Text style={styles.subtitle}>Your allowance resets {profile?.allowance?.reset_at ? `${new Date(profile.allowance.reset_at).toLocaleString([], { timeZone: 'Asia/Singapore', month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' })} SGT` : 'at the next reset'}.</Text>}
      <View style={styles.grid}>{features.map(feature => <Pressable key={feature.icon} accessibilityRole="button"
        accessibilityLabel={`${feature.label.replace('\n', ' ')}${feature.locked ? premium ? ', coming soon' : ', premium feature' : feature.premiumOnly && !premium ? ', premium feature' : ''}`}
        onPress={() => onNavigate(feature.locked || (feature.premiumOnly && !premium && profile) ? 'premium' : feature.page)}
        style={({ pressed }) => [styles.tile, fontScale > 1.5 && styles.tileLarge, (feature.locked || (feature.premiumOnly && !premium)) && styles.locked, pressed && styles.tilePressed]}>
        <View style={[styles.icon, { backgroundColor: feature.colour }]}><Feather name={feature.icon} size={28} color={feature.ink} /></View>
        <View style={[styles.tileContent, fontScale > 1.5 && styles.tileContentLarge]}>
          <Text style={styles.tileLabel}>{feature.label}</Text>
          {feature.locked ? <Text style={styles.lock}>{premium ? 'Coming soon' : 'Premium'}</Text> : feature.premiumOnly && !premium && <Text style={styles.lock}>Premium</Text>}
        </View>
        {fontScale <= 1.5 && <Feather name="chevron-right" size={24} color={colours.blueDark} />}
      </Pressable>)}</View>
      <Pressable accessibilityRole="button" onPress={() => onNavigate('premium')} style={styles.upgrade}>
        <Text style={styles.upgradeText}>{premium ? <><Text style={{ fontWeight: '700' }}>Premium active</Text> · Read image text, check image context and check AI images.</> : <><Text style={{ fontWeight: '700' }}>Read image text with Premium</Text> · View plan details.</>}</Text>
      </Pressable>
    </PageBody>
  </View>;
}

const styles = StyleSheet.create({
  account: { flexDirection: 'row', alignItems: 'center', gap: 10, flexShrink: 1 },
  plan: { ...typography.small, backgroundColor: colours.infoBackground, color: colours.blueDark, borderRadius: 16, paddingHorizontal: 10, paddingVertical: 8, fontWeight: '700', flexShrink: 1 },
  avatar: { minWidth: 56, minHeight: 56, padding: 8, borderRadius: 12, borderWidth: 2, borderColor: colours.border, justifyContent: 'center', alignItems: 'center' },
  initials: { ...typography.secondary, color: colours.blueDark, fontWeight: '700' },
  greeting: { ...typography.title, color: colours.ink },
  subtitle: { ...typography.body, color: colours.muted, marginTop: 8 },
  allowance: { borderRadius: 18, minHeight: 120, padding: 20, flexDirection: 'row', alignItems: 'center', gap: 16 },
  allowanceLabel: { ...typography.secondary, color: colours.white },
  allowanceRow: { flexDirection: 'row', flexWrap: 'wrap', alignItems: 'baseline', gap: 8, marginVertical: 6 },
  number: { color: colours.white, fontSize: 32, lineHeight: 42, fontWeight: '700' },
  available: { ...typography.body, color: colours.white },
  track: { height: 5, backgroundColor: '#91B6C6', marginTop: 1, borderRadius: 5, overflow: 'hidden' },
  fill: { height: 5, backgroundColor: 'white' },
  grid: { gap: 12 },
  tile: { minHeight: 88, padding: 16, borderRadius: 16, borderWidth: 2, borderColor: colours.border, backgroundColor: colours.white, flexDirection: 'row', alignItems: 'center', gap: 14 },
  tileLarge: { flexDirection: 'column', alignItems: 'flex-start' },
  tileContent: { flex: 1, flexShrink: 1, gap: 8, alignSelf: 'stretch', justifyContent: 'center' },
  tileContentLarge: { flex: 0, flexShrink: 0 },
  icon: { width: 48, height: 48, borderRadius: 12, alignItems: 'center', justifyContent: 'center' },
  tileLabel: { ...typography.label, color: colours.ink },
  locked: { backgroundColor: colours.background },
  tilePressed: { backgroundColor: colours.infoBackground },
  lock: { ...typography.small, color: colours.warning, backgroundColor: colours.warningBackground, paddingHorizontal: 8, paddingVertical: 3, borderRadius: 7, alignSelf: 'flex-start' },
  upgrade: { backgroundColor: colours.warningBackground, borderLeftWidth: 3, borderLeftColor: colours.warning, borderRadius: 13, padding: 18, minHeight: 56 },
  upgradeText: { ...typography.secondary, color: colours.warning },
  retry: { minHeight: 56, justifyContent: 'center' },
  notice: { ...typography.secondary, color: colours.danger },
});
