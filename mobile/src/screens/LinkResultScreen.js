import { colours, typography } from '../theme';
import ReportResultPanel from '../components/ReportResultPanel';
import { StyleSheet, Text, View } from 'react-native';
import { PageBody, PageHeader } from '../components/AppShell';
import Button from '../components/Button';
import FeatureExplanation from '../components/FeatureExplanation';
import { assessmentLabel } from '../utils/assessment';

const threats = {
  MALWARE: ['Malware', 'The link may expose you to harmful software that steals information or affects your device.'],
  SOCIAL_ENGINEERING: ['Phishing or deceptive content', 'The link may trick you into revealing personal information, making a payment or taking an unsafe action.'],
  UNWANTED_SOFTWARE: ['Unwanted software', 'The link may offer software that behaves deceptively or changes your device without clear consent.'],
};

const completedSummaries = {
  threat_detected: 'This link was flagged as potentially dangerous.',
  no_known_threats: 'This link was not found on the threat lists checked.',
};
const standardLimitations = "This checks Google's known threat lists, not whether the webpage's claims are true. "
  + 'New threats and redirect destinations may not be detected. '
  + 'No known threats found does not guarantee safety; warnings can also be mistaken.';
const conciseLimitations = 'Checks known threats, not the truth of webpage claims. New threats and redirects may be missed. '
  + 'No known threats found does not guarantee safety; warnings may be mistaken.';

export default function LinkResultScreen({ result, onNavigate }) {
  const failed = result.processing_status === 'failed';
  const flagged = result.safety_status === 'threat_detected';
  const knownCompletedResult = result.processing_status === 'completed'
    && ['threat_detected', 'no_known_threats'].includes(result.safety_status);
  const explanation = knownCompletedResult ? completedSummaries[result.safety_status] : result.explanation;
  const limitations = result.limitations === standardLimitations ? conciseLimitations : result.limitations;
  return <View style={{ flex: 1 }}>
    <PageHeader title="Link safety result" onBack={() => onNavigate('results')} badge="Saved" />
    <PageBody>
      <View style={[styles.card, flagged && styles.danger]}>
        <Text accessibilityRole="header" style={[styles.heading, flagged && { color: colours.danger }]}>{assessmentLabel(result)}</Text>
        <Text style={styles.copy}>{failed ? result.message : explanation}</Text>
        {failed ? <Text style={styles.copy}>Your allowance was not used. No safety verdict was produced.</Text> : <Text style={styles.copy}>{result.recommended_action}</Text>}
      </View>
      <View style={styles.card}><Text style={styles.heading}>Submitted link</Text>
        <Text selectable style={styles.copy}>{result.submitted_url}</Text>
        <Text style={styles.hint}>The submitted link is shown for reference and is not opened by this screen.</Text>
      </View>
      {!failed && <>
        {result.threat_types.map(type => <View key={type} style={styles.card}><Text style={styles.heading}>{threats[type]?.[0] || type}</Text><Text style={styles.copy}>{threats[type]?.[1]}</Text></View>)}
        <FeatureExplanation title="About this check">
          <Text style={styles.copy}>{limitations}</Text>
          <Text style={styles.copy}>Checked {new Date(result.checked_at).toLocaleString()}. A website's safety can change.</Text>
          {result.cached && <Text style={styles.hint}>A recent threat match was reused while still valid.</Text>}
        </FeatureExplanation>
      </>}
      <Button onPress={() => onNavigate('link')}>{failed ? 'Try another link check' : 'Check another link'}</Button>
      <Text style={styles.hint}>Saved {new Date(result.created_at).toLocaleString()}</Text>
      <ReportResultPanel result={result} />
    </PageBody>
  </View>;
}

const styles = StyleSheet.create({
  card: { borderRadius: 18, backgroundColor: colours.white, borderWidth: 1, borderColor: colours.divider, padding: 18, gap: 16 },
  danger: { backgroundColor: colours.dangerBackground, borderColor: colours.danger, borderWidth: 2 },
  heading: { ...typography.heading, color: colours.ink },
  copy: { ...typography.body, color: colours.text },
  hint: { ...typography.secondary, color: colours.muted },
});
