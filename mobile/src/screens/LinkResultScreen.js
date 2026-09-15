import { StyleSheet, Text, View } from 'react-native';
import { PageBody, PageHeader } from '../components/AppShell';
import Button from '../components/Button';
import { assessmentLabel } from '../utils/assessment';

const threats = {
  MALWARE: ['Malware', 'The link may expose you to harmful software that steals information or affects your device.'],
  SOCIAL_ENGINEERING: ['Phishing or deceptive content', 'The link may trick you into revealing personal information, making a payment or taking an unsafe action.'],
  UNWANTED_SOFTWARE: ['Unwanted software', 'The link may offer software that behaves deceptively or changes your device without clear consent.'],
};

export default function LinkResultScreen({ result, onNavigate }) {
  const failed = result.processing_status === 'failed';
  const flagged = result.safety_status === 'threat_detected';
  return <View style={{ flex: 1 }}>
    <PageHeader title="Link safety result" onBack={() => onNavigate('results')} badge="Saved" />
    <PageBody>
      <View style={[styles.card, flagged && styles.danger]}>
        <Text accessibilityRole="header" style={[styles.heading, flagged && { color: '#A12020' }]}>{assessmentLabel(result)}</Text>
        <Text style={styles.copy}>{failed ? result.message : result.explanation}</Text>
        {failed ? <Text style={styles.copy}>Your allowance was not used. No safety verdict was produced.</Text> : <Text style={styles.copy}>{result.recommended_action}</Text>}
      </View>
      <View style={styles.card}><Text style={styles.heading}>Submitted link</Text>
        <Text selectable style={styles.copy}>{result.submitted_url}</Text>
        <Text style={styles.hint}>The submitted link is shown for reference and is not opened by this screen.</Text>
      </View>
      {!failed && <>
        {result.threat_types.map(type => <View key={type} style={styles.card}><Text style={styles.heading}>{threats[type]?.[0] || type}</Text><Text style={styles.copy}>{threats[type]?.[1]}</Text></View>)}
        <View style={styles.note}><Text style={styles.heading}>What this result means</Text><Text style={styles.copy}>{result.limitations}</Text></View>
        <View style={styles.card}><Text style={styles.label}>Checked using {result.provider}</Text>
          <Text style={styles.copy}>Threat information checked {new Date(result.checked_at).toLocaleString()}.</Text>
          <Text style={styles.copy}>This is a saved result from that time. A website's safety can change.</Text>
          {result.cached && <Text style={styles.hint}>A recent Google threat match was reused within its validity period.</Text>}
        </View>
      </>}
      <Button onPress={() => onNavigate('link')}>{failed ? 'Try another link check' : 'Check another link'}</Button>
      <Text style={styles.hint}>Saved {new Date(result.created_at).toLocaleString()}</Text>
    </PageBody>
  </View>;
}

const styles = StyleSheet.create({
  card: { borderRadius: 18, backgroundColor: 'white', borderWidth: 1, borderColor: '#D7E3EA', padding: 18, gap: 12 },
  danger: { backgroundColor: '#FBE9E7', borderColor: '#E7B5B0' },
  note: { borderRadius: 14, backgroundColor: '#FFF4D2', borderLeftWidth: 3, borderLeftColor: '#D49A00', padding: 16, gap: 10 },
  heading: { color: '#173447', fontSize: 21, fontWeight: '800' },
  label: { color: '#173447', fontSize: 15, fontWeight: '700' },
  copy: { color: '#48677C', fontSize: 15, lineHeight: 23 },
  hint: { color: '#617D90', fontSize: 12, lineHeight: 19 },
});
