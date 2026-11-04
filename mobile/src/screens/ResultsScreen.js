import React from 'react';
import { ActivityIndicator, Pressable, RefreshControl, StyleSheet, Text, View } from 'react-native';
import Feather from '@expo/vector-icons/Feather';
import { useAuth } from '../auth/AuthContext';
import { PageBody, PageHeader } from '../components/AppShell';
import Button from '../components/Button';
import { getResults, getResult } from '../services/api';
import { colours, typography } from '../theme';
import { assessmentLabel } from '../utils/assessment';

export const concernColours = { 'High Concern': [colours.dangerBackground, colours.danger], 'Needs Caution': [colours.warningBackground, colours.warning], 'Low Concern': [colours.successBackground, colours.success], 'Not Enough Information': [colours.infoBackground, colours.blueDark], Failed: [colours.dangerBackground, colours.danger] };

export function ConcernBadge({ label, concern = label }) {
  const [backgroundColor, color] = concernColours[concern] || concernColours['Not Enough Information'];
  return <Text style={[styles.badge, { backgroundColor, color }]}>{label}</Text>;
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
      <View><Text style={styles.heading}>Your saved checks</Text><Text style={styles.copy}>Open a result to review its findings and when it was checked.</Text></View>
      {!!error && <><Text accessibilityRole="alert" style={styles.error}>{error}</Text><Button secondary onPress={() => load()}>Retry</Button></>}
      {busy && items.length === 0 && <ActivityIndicator color={colours.blue} size="large" />}
      {!busy && !error && items.length === 0 && <View style={styles.empty}><Feather name="file-text" size={35} color={colours.muted} /><Text style={styles.heading}>Your first check starts here</Text><Text style={styles.copy}>Your completed checks will be saved to your account.</Text><Button onPress={() => onNavigate('text')}>Check some text</Button></View>}
      {items.length > 0 && <View style={styles.list}>{items.map((item, index) => <Pressable key={item.result_id} disabled={!!opening} accessibilityRole="button"
        accessibilityLabel={`Open result: ${item.submitted_url || item.extracted_claim || item.original_text}`}
        onPress={() => open(item)} style={[styles.row, index > 0 && styles.divider]}>
        <View style={styles.icon}><Text style={styles.letters}>{item.input_type === 'deepfake_ai' ? 'IMG' : item.input_type === 'image_context'? 'CTX': item.input_type === 'link_safety' ? 'URL' : item.input_source === 'ocr' ? 'OCR' : item.input_source === 'webpage' ? 'WEB' : 'Aa'}</Text></View>
        <View style={{ flex: 1, gap: 7 }}><Text style={styles.claim}>{item.input_type === 'deepfake_ai' ? `Deepfake / AI image check${item.label ? ` — Predicted: ${item.label}` : ''}` : item.input_type === 'image_context' ? item.extracted_caption || item.image_filename || 'Image context check' : item.submitted_url || item.extracted_claim || item.original_text}</Text>
        <Text style={styles.date}>
          {item.input_type === 'deepfake_ai'
            ? 'Image'
            : item.input_type === 'image_context'
              ? 'Image context'
              : item.input_type === 'link_safety'
                ? 'Link'
                : item.input_source === 'webpage' ? 'Webpage text' : 'Text'}
          {' · '}
          {new Date(item.created_at).toLocaleString([], {
            month: 'short',
            day: 'numeric',
            hour: 'numeric',
            minute: '2-digit',
          })}
        </Text>
          {item.input_type === 'deepfake_ai' ? (
            <ConcernBadge
              label={
                item.processing_status === 'failed'
                ? 'Failed'
                : item.label || 'Result available'
              }
              concern={
                item.processing_status === 'failed'
                ? 'Failed'
                : item.label === 'Real'
                  ? 'Low Concern'
                    : item.label === 'Fake'
                      ? 'High Concern'
                      : 'Not Enough Information'
              }
            />
          ) : item.input_type === 'image_context' ? (
            <ConcernBadge
              label={
                item.processing_status === 'failed'
                  ? 'Failed'
                  : item.concern_label || 'Not Enough Information'
              }
              concern={
                item.processing_status === 'failed'
                  ? 'Failed'
                  : item.concern_label || 'Not Enough Information'
              }
            />
          ) :(
            <ConcernBadge
              label={assessmentLabel(item)}
              concern={
                item.processing_status === 'failed'
                  ? 'Failed'
                  : item.input_type === 'link_safety'
                    ? (item.safety_status === 'threat_detected'
                      ? 'High Concern'
                      : 'Not Enough Information')
                    : item.concern_label
                }
              />
            )}
          </View>
        {opening === item.result_id ? <ActivityIndicator color={colours.blue} /> : <Feather name="chevron-right" color={colours.muted} size={24} />}
      </Pressable>)}</View>}
      {!!cursor && <Button loading={busy} secondary onPress={() => load(true)}>Load more results</Button>}
    </PageBody>
  </View>;
}
const styles = StyleSheet.create({
  heading: { ...typography.heading, color: colours.ink, marginBottom: 8 },
  copy: { ...typography.body, color: colours.muted },
  badge: { ...typography.small, paddingHorizontal: 12, paddingVertical: 8, borderRadius: 12, fontWeight: '700', alignSelf: 'flex-start', flexShrink: 1 },
  list: { backgroundColor: colours.white, borderRadius: 18, borderWidth: 1, borderColor: colours.divider, paddingHorizontal: 16 },
  row: { flexDirection: 'row', paddingVertical: 20, alignItems: 'flex-start', gap: 12, minHeight: 56 },
  divider: { borderTopWidth: 1, borderTopColor: colours.divider },
  icon: { minWidth: 44, minHeight: 48, paddingHorizontal: 6, paddingVertical: 8, borderRadius: 11, backgroundColor: colours.infoBackground, alignItems: 'center', justifyContent: 'center' },
  letters: { ...typography.small, color: colours.blueDark, fontWeight: '700' },
  claim: { ...typography.label, color: colours.ink },
  date: { ...typography.small, color: colours.muted },
  empty: { backgroundColor: colours.white, padding: 22, borderRadius: 18, gap: 16 },
  error: { ...typography.secondary, color: colours.danger },
});
