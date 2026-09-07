import { Alert, Linking, Pressable, Share, StyleSheet, Text, View } from 'react-native';
import Feather from '@expo/vector-icons/Feather';
import { PageBody, PageHeader } from '../components/AppShell';
import Button from '../components/Button';
import { ConcernBadge, concernColours } from './ResultsScreen';

export default function ResultScreen({ result, onNavigate }) {
  const failed = result.processing_status === 'failed';
  const label = failed ? 'Failed' : result.concern_label;
  const score = result.misinformation_risk_score;
  const colour = (concernColours[label] || concernColours['Not Enough Information'])[1];
  async function openSource(url) {
    if (!/^https?:\/\//i.test(url)) return;
    try { await Linking.openURL(url); } catch { Alert.alert('Could not open source', 'Please try again when you are connected.'); }
  }
  async function share() {
    try { await Share.share({ message: `UIABO result: ${label}\n${result.extracted_claim || result.original_text}\n\n${result.explanation}\n${result.recommended_action}\n\nSources:\n${(result.evidence || []).map(item => item.url).join('\n')}\n\nAn automated assessment, not proof.` }); }
    catch { Alert.alert('Could not share', 'Please try again.'); }
  }
  return <View style={{ flex: 1 }}>
    <PageHeader title="Analysis result" onBack={() => onNavigate('results')} badge="Saved" />
    <PageBody>
      <View style={styles.note}><Text style={styles.copy}>Review the evidence before sharing. Automated checks can make mistakes.</Text></View>
      {failed ? <View style={styles.card}><ConcernBadge label="Failed" /><Text style={styles.heading}>This check could not finish</Text><Text style={styles.copy}>{result.message}</Text><Text style={styles.copy}>Your allowance was not used.</Text><Button onPress={() => onNavigate('text')}>Start a new check</Button></View> : <>
        <View style={[styles.card, styles.scoreRow]}><View style={[styles.scoreCircle, { borderColor: colour }]}><Text style={[styles.score, { color: colour }]}>{score == null ? '—' : score}</Text></View><View style={{ flex: 1, gap: 8 }}><ConcernBadge label={label} /><Text style={styles.heading}>{score == null ? 'No risk score' : 'Risk indicator'}</Text><Text style={styles.copy}>{score == null ? 'There is not enough information to assign a score.' : 'Higher means greater concern, not mathematical proof.'}</Text></View></View>
        <View style={styles.card}><View style={styles.between}><Text style={styles.heading}>Uncertainty</Text><Text style={styles.uncertainty}>{result.uncertainty}</Text></View>{result.uncertainty_reasons?.map((reason, i) => <Text key={i} style={styles.copy}>{reason}</Text>)}</View>
      </>}
      <View style={styles.card}><Text style={styles.heading}>{result.extracted_claim ? 'Claim identified' : 'Submitted text'}</Text><Text selectable style={styles.copy}>{result.extracted_claim || result.original_text}</Text></View>
      {!failed && <View style={styles.card}><Text style={styles.heading}>What the evidence suggests</Text><Text style={styles.copy}>{result.explanation}</Text><View style={styles.action}><Text style={styles.label}>Recommended action</Text><Text style={styles.copy}>{result.recommended_action}</Text></View></View>}
      {!!result.evidence?.length && <Text style={styles.heading}>Evidence sources</Text>}
      {result.evidence?.map((item, index) => <View key={item.evidence_id} style={styles.card}>
        <View style={styles.between}><Text style={styles.publisher}>{index + 1}. {item.publisher}</Text><Text style={styles.stance}>{item.stance}</Text></View>
        <Pressable accessibilityRole="link" onPress={() => openSource(item.url)}><Text style={styles.sourceTitle}>{item.title} ↗</Text></Pressable>
        <Text selectable style={styles.copy}>{item.passage}</Text>
        <Text style={styles.date}>{item.published_at ? `Published ${item.published_at}` : 'Publication date unavailable'}</Text>
        <Pressable accessibilityRole="link" accessibilityLabel={`Open source ${index + 1}`} onPress={() => openSource(item.url)} style={styles.sourceButton}><Feather name="external-link" size={15} color="#126589" /><Text style={styles.sourceButtonText}>Open source</Text></Pressable>
      </View>)}
      {result.warnings?.map((warning, i) => <View key={i} style={styles.note}><Text style={styles.copy}>{warning}</Text></View>)}
      {!failed && <Button secondary onPress={share}>Share result</Button>}
      <Text style={styles.date}>Saved {new Date(result.created_at).toLocaleString()}</Text>
    </PageBody>
  </View>;
}
const styles = StyleSheet.create({
  card: { borderRadius: 20, backgroundColor: 'white', borderWidth: 1, borderColor: '#D7E3EA', padding: 18, gap: 10 },
  note: { borderRadius: 14, backgroundColor: '#FFF4D2', borderLeftWidth: 3, borderLeftColor: '#D49A00', padding: 15 },
  heading: { color: '#173447', fontWeight: '800', fontSize: 20 },
  label: { color: '#173447', fontWeight: '700', fontSize: 14 },
  copy: { color: '#48677C', fontSize: 14, lineHeight: 21 },
  scoreRow: { flexDirection: 'row', alignItems: 'center', gap: 16 },
  scoreCircle: { width: 90, height: 90, borderRadius: 45, borderWidth: 8, justifyContent: 'center', alignItems: 'center' },
  score: { fontSize: 29, fontWeight: '800' }, between: { flexDirection: 'row', justifyContent: 'space-between', gap: 10, alignItems: 'center' },
  uncertainty: { color: '#80600A', backgroundColor: '#FFF4D2', paddingHorizontal: 10, paddingVertical: 6, borderRadius: 14, fontWeight: '700', fontSize: 12 },
  action: { backgroundColor: '#E5F3FA', padding: 14, borderRadius: 13, borderLeftWidth: 3, borderLeftColor: '#1778A3', gap: 6 },
  publisher: { color: '#637F91', flex: 1, fontSize: 12, fontWeight: '600' },
  stance: { color: '#637F91', fontSize: 11, textTransform: 'capitalize' },
  sourceTitle: { color: '#126589', fontWeight: '700', fontSize: 16, lineHeight: 23 },
  date: { color: '#718797', fontSize: 11 },
  sourceButton: { flexDirection: 'row', alignItems: 'center', gap: 7, paddingVertical: 10 },
  sourceButtonText: { color: '#126589', fontWeight: '700', fontSize: 13 },
});
