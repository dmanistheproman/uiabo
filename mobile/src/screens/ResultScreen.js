import { useState } from 'react';
import { Alert, Linking, Pressable, Share, StyleSheet, Text, View } from 'react-native';
import Feather from '@expo/vector-icons/Feather';
import { PageBody, PageHeader } from '../components/AppShell';
import Button from '../components/Button';
import { ConcernBadge, concernColours } from './ResultsScreen';
import { assessmentLabel, comparisonAspects, comparisonFindings } from '../utils/assessment';

export default function ResultScreen({ result, onNavigate }) {
  const [expandedSources, setExpandedSources] = useState({});
  const failed = result.processing_status === 'failed';
  const label = failed ? 'Failed' : result.concern_label;
  const headline = assessmentLabel(result);
  const score = result.misinformation_risk_score;
  const colour = (concernColours[label] || concernColours['Not Enough Information'])[1];
  const assumedDate = result.date_context?.display_date;
  async function openSource(url) {
    if (!/^https?:\/\//i.test(url)) return;
    try { await Linking.openURL(url); } catch { Alert.alert('Could not open source', 'Please try again when you are connected.'); }
  }
  async function share() {
    try { await Share.share({ message: `UIABO result: ${headline}\n${result.extracted_claim || result.original_text}\n${assumedDate ? `\nAssumed date: ${assumedDate} (year not stated in the message).\n` : ''}\n${result.explanation}\n${result.recommended_action}\n\nSources:\n${(result.evidence || []).map(item => item.url).join('\n')}\n\nAn automated assessment, not proof.` }); }
    catch { Alert.alert('Could not share', 'Please try again.'); }
  }
  return <View style={{ flex: 1 }}>
    <PageHeader title="Analysis result" onBack={() => onNavigate('results')} badge="Saved" />
    <PageBody>
      <View style={styles.note}><Text style={styles.copy}>Review the evidence before sharing. Automated checks can make mistakes.</Text></View>
      {failed ? <View style={styles.card}><ConcernBadge label="Failed" /><Text style={styles.heading}>This check could not finish</Text><Text style={styles.copy}>{result.message}</Text><Text style={styles.copy}>Your allowance was not used.</Text><Button onPress={() => onNavigate('text')}>Start a new check</Button></View> : <>
        <View style={styles.card}><Text style={styles.heading}>{headline}</Text><ConcernBadge label={label} /><View style={styles.scoreRow}><View style={[styles.scoreCircle, { borderColor: colour }]}><Text style={[styles.score, { color: colour }]}>{score == null ? '—' : score}</Text></View><View style={{ flex: 1, gap: 8 }}><Text style={styles.heading}>{score == null ? 'No risk score' : 'Risk indicator'}</Text><Text style={styles.copy}>{result.assessment_outcome === 'unsupported' ? 'The policy checked does not establish the claim. This is not proof that an unconfirmed change is false.' : score == null ? 'There is not enough information to assign a score.' : 'Higher means greater concern, not mathematical proof.'}</Text></View></View></View>
        <View style={styles.card}><View style={styles.between}><Text style={styles.heading}>Uncertainty</Text><Text style={styles.uncertainty}>{result.uncertainty}</Text></View>{result.uncertainty_reasons?.map((reason, i) => <Text key={i} style={styles.copy}>{reason}</Text>)}</View>
      </>}
      <View style={styles.card}><Text style={styles.heading}>{result.extracted_claim ? 'Claim identified' : 'Submitted text'}</Text><Text selectable style={styles.copy}>{result.extracted_claim || result.original_text}</Text></View>
      {!failed && !!assumedDate && <View style={styles.note}>
        <Text style={styles.heading}>Assumed date: {assumedDate}</Text>
        <Text style={styles.copy}>The message does not specify a year, so this check used the current year when it was submitted. The original wording is unchanged.</Text>
        {!!result.date_context.is_future && <Text style={styles.copy}>This date was in the future when checked. An existing rule alone cannot disprove an unconfirmed change.</Text>}
        <Button secondary onPress={() => onNavigate('text', { draft: { text: result.original_text, correctYear: true } })}>Correct year</Button>
      </View>}
      {!failed && <View style={styles.card}><Text style={styles.heading}>What the evidence suggests</Text><Text style={styles.copy}>{result.explanation}</Text><View style={styles.action}><Text style={styles.label}>Recommended action</Text><Text style={styles.copy}>{result.recommended_action}</Text></View></View>}
      {!failed && !!result.claim_comparisons?.length && <>
        <Text style={styles.heading}>Claim vs published policy</Text>
        <Text style={styles.copy}>A difference from a published rule does not by itself disprove a change for another date or group.</Text>
        {result.claim_comparisons.map((part, index) => {
          const source = result.evidence?.find(item => item.evidence_id === part.evidence_id);
          const key = `comparison-${index}`;
          return <View key={key} style={styles.card}>
            <Text style={styles.heading}>{comparisonAspects[part.aspect] || 'Policy detail'}</Text>
            <Text selectable style={styles.copy}>Claim: {part.claim_text}</Text>
            <Text style={styles.label}>{comparisonFindings[part.finding] || 'Not established'}</Text>
            <Text style={styles.copy}>{part.explanation}</Text>
            {part.finding !== 'unresolved' && !part.applies_to_claim && <Text style={styles.copy}>Whether this rule applies to the claimed circumstances is unresolved.</Text>}
            {!!part.evidence_quote && <>
              <Pressable accessibilityRole="button" accessibilityState={{ expanded: !!expandedSources[key] }} onPress={() => setExpandedSources(current => ({ ...current, [key]: !current[key] }))} style={styles.sourceButton}><Text style={styles.sourceButtonText}>{expandedSources[key] ? 'Hide quoted policy' : 'Read quoted policy'}</Text></Pressable>
              {expandedSources[key] && <Text selectable style={styles.copy}>{part.evidence_quote}</Text>}
            </>}
            {!!source && <Pressable accessibilityRole="link" onPress={() => openSource(source.url)} style={styles.sourceButton}><Feather name="external-link" size={15} color="#126589" /><Text style={styles.sourceButtonText}>{source.publisher}</Text></Pressable>}
          </View>;
        })}
      </>}
      {!!result.evidence?.length && <Text style={styles.heading}>Evidence sources</Text>}
      {result.evidence?.map((item, index) => <View key={item.evidence_id} style={styles.card}>
        <View style={styles.between}><Text style={styles.publisher}>{index + 1}. {item.publisher}</Text><Text style={styles.stance}>{item.stance}</Text></View>
        <Pressable accessibilityRole="link" onPress={() => openSource(item.url)}><Text style={styles.sourceTitle}>{item.title} ↗</Text></Pressable>
        {!!item.assessment_reason && <Text style={styles.copy}>{item.assessment_reason}</Text>}
        {!!item.evidence_quote && <View style={styles.action}><Text style={styles.label}>Quoted evidence</Text><Text selectable style={styles.copy}>{item.evidence_quote}</Text></View>}
        {(!item.evidence_quote || expandedSources[item.evidence_id]) && <Text selectable style={styles.copy}>{item.passage}</Text>}
        {!!item.evidence_quote && <Pressable accessibilityRole="button" accessibilityState={{ expanded: !!expandedSources[item.evidence_id] }} onPress={() => setExpandedSources(current => ({ ...current, [item.evidence_id]: !current[item.evidence_id] }))} style={styles.sourceButton}><Text style={styles.sourceButtonText}>{expandedSources[item.evidence_id] ? 'Hide source context' : 'Read source context'}</Text></Pressable>}
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
