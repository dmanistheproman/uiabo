import React from 'react';
import { ActivityIndicator, Pressable, RefreshControl, StyleSheet, Text, View } from 'react-native';
import Feather from '@expo/vector-icons/Feather';
import { useAuth } from '../auth/AuthContext';
import { PageBody, PageHeader } from '../components/AppShell';
import Button from '../components/Button';
import { getResults, getResult } from '../services/api';
import { colours } from '../theme';
import { assessmentLabel } from '../utils/assessment';

export const concernColours = { 'High Concern': ['#FBE9E7', '#AA2825'], 'Needs Caution': ['#FFF4D2', '#896306'], 'Low Concern': ['#E4F4EC', '#197551'], 'Not Enough Information': ['#E5F3FA', '#285B7D'], Failed: ['#F3ECEB', '#8D4840'] };

export function ConcernBadge({ label, concern = label }) {
  const [backgroundColor, color] = concernColours[concern] || concernColours['Not Enough Information'];
  return <Text style={{ backgroundColor, color, paddingHorizontal: 11, paddingVertical: 6, borderRadius: 18, fontSize: 11, fontWeight: '700', alignSelf: 'flex-start' }}>{label}</Text>;
}

export default function ResultsScreen({ onResult, onNavigate }) {
  const { firebaseUser } = useAuth();
  const [items, setItems] = React.useState([]);
  const [cursor, setCursor] = React.useState(null);
  const [busy, setBusy] = React.useState(true);
  const [opening, setOpening] = React.useState(null);
  const [error, setError] = React.useState('');
  async function load(more = false) {
    setBusy(true); setError('');
    try {
      const data = await getResults(firebaseUser, more ? cursor : null);
      setItems(current => more ? [...current, ...data.results.filter(item => !current.some(old => old.result_id === item.result_id))] : data.results);
      setCursor(data.next_cursor);
    } catch (problem) { setError(problem.message); }
    finally { setBusy(false); }
  }
  React.useEffect(() => { load(); }, [firebaseUser.uid]);
  async function open(item) {
    if (opening) return;
    setOpening(item.result_id); setError('');
    try { onResult(await getResult(firebaseUser, item.result_id)); }
    catch (problem) { setError(problem.message); }
    finally { setOpening(null); }
  }
  return <View style={{ flex: 1 }}>
    <PageHeader title="Result history" onBack={() => onNavigate('home')} />
    <PageBody refreshControl={<RefreshControl refreshing={busy} onRefresh={() => load()} />}>
      <View><Text style={styles.heading}>Your saved checks</Text><Text style={styles.copy}>Open a result to review its explanation and sources.</Text></View>
      {!!error && <><Text accessibilityRole="alert" style={styles.error}>{error}</Text><Button secondary onPress={() => load()}>Retry</Button></>}
      {busy && items.length === 0 && <ActivityIndicator color={colours.blue} size="large" />}
      {!busy && !error && items.length === 0 && <View style={styles.empty}><Feather name="file-text" size={35} color="#637F91" /><Text style={styles.heading}>Your first check starts here</Text><Text style={styles.copy}>Your completed checks will be saved to your account.</Text><Button onPress={() => onNavigate('text')}>Check some text</Button></View>}
      {items.length > 0 && <View style={styles.list}>{items.map((item, index) => <Pressable key={item.result_id} disabled={!!opening} accessibilityRole="button"
        accessibilityLabel={`Open result: ${item.extracted_claim || item.original_text}`}
        onPress={() => open(item)} style={[styles.row, index > 0 && styles.divider]}>
        <View style={styles.icon}><Text style={styles.letters}>Aa</Text></View>
        <View style={{ flex: 1, gap: 7 }}><Text numberOfLines={2} style={styles.claim}>{item.extracted_claim || item.original_text}</Text><Text style={styles.date}>Text · {new Date(item.created_at).toLocaleString([], { month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' })}</Text>
          <ConcernBadge label={assessmentLabel(item)} concern={item.processing_status === 'failed' ? 'Failed' : item.concern_label} /></View>
        {opening === item.result_id ? <ActivityIndicator color={colours.blue} /> : <Feather name="chevron-right" color="#78909F" size={18} />}
      </Pressable>)}</View>}
      {!!cursor && <Button loading={busy} secondary onPress={() => load(true)}>Load more results</Button>}
    </PageBody>
  </View>;
}
const styles = StyleSheet.create({
  heading: { color: '#173447', fontSize: 22, fontWeight: '800', marginBottom: 5 },
  copy: { color: '#637F91', fontSize: 14, lineHeight: 21 },
  list: { backgroundColor: 'white', borderRadius: 18, borderWidth: 1, borderColor: '#D7E3EA', paddingHorizontal: 16 },
  row: { flexDirection: 'row', paddingVertical: 19, alignItems: 'center', gap: 12 },
  divider: { borderTopWidth: 1, borderTopColor: '#E1E9EE' },
  icon: { width: 40, height: 44, borderRadius: 11, backgroundColor: '#E5F3FA', alignItems: 'center', justifyContent: 'center' },
  letters: { color: '#174968', fontSize: 17, fontWeight: '800' },
  claim: { color: '#173447', fontSize: 15, fontWeight: '700', lineHeight: 21 },
  date: { color: '#637F91', fontSize: 11 },
  empty: { backgroundColor: 'white', padding: 22, borderRadius: 18, gap: 15 },
  error: { color: colours.danger, lineHeight: 22 },
});
