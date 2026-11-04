import { colours, typography } from '../theme';
import { Pressable, StyleSheet, Text, View } from 'react-native';
import Feather from '@expo/vector-icons/Feather';

function SourceLink({ source, onOpenSource }) {
  return <Pressable accessibilityRole="link" accessibilityLabel={`Open source: ${source.title}`}
    onPress={() => onOpenSource(source.url)} style={({ pressed }) => [styles.link, pressed && styles.pressed]}>
    <View style={styles.flexText}>
      <Text style={styles.linkText}>{source.title}</Text>
      <Text style={styles.secondary}>{source.publisher}</Text>
    </View>
    <Feather name="external-link" size={22} color={colours.blueDark} accessible={false} />
  </Pressable>;
}

export default function ResearchAssessmentPanel({ research, onOpenSource }) {
  return <>
    <View style={styles.card}>
      <Text accessibilityRole="header" style={styles.heading}>Why this result?</Text>
      <Text selectable style={styles.copy}>{research.summary}</Text>
      {!!research.checkedOn && <Text style={styles.secondary}>Checked on {research.checkedOn} (Singapore date)</Text>}
      <Text style={styles.secondary}>This is an AI assessment of the cited information. Open the sources to check the original wording.</Text>
    </View>
    {!!research.findings.length && <View style={styles.card}>
      <Text accessibilityRole="header" style={styles.heading}>The parts we checked</Text>
      {research.findings.map((finding, index) => <View key={index} style={styles.section}>
        <Text selectable style={styles.label}>{index + 1}. {finding.claim}</Text>
        <Text style={styles.label}>{finding.label}</Text>
        <Text selectable style={styles.copy}>{finding.explanation}</Text>
        {finding.inference && <Text style={styles.secondary}>This finding is an inference from the available information.</Text>}
        {finding.sources.map(source => <SourceLink key={source.id} source={source} onOpenSource={onOpenSource} />)}
      </View>)}
    </View>}
    {!!research.limitations.length && <View style={styles.card}>
      <Text accessibilityRole="header" style={styles.heading}>What this check could not settle</Text>
      {research.limitations.map((limitation, index) => <Text key={index} style={styles.copy}>{limitation}</Text>)}
    </View>}
    <View style={styles.card}>
      <Text accessibilityRole="header" style={styles.heading}>Read the sources</Text>
      <Text style={styles.copy}>{research.sources.length
        ? 'These websites were cited during the web check. The explanations above are AI summaries, not quotations from these websites.'
        : 'No usable source links were saved. This does not prove that the claim is true or false.'}</Text>
      {research.sources.map(source => <SourceLink key={source.id} source={source} onOpenSource={onOpenSource} />)}
    </View>
  </>;
}

const styles = StyleSheet.create({
  card: { borderRadius: 16, backgroundColor: colours.white, borderWidth: 1, borderColor: colours.divider, padding: 18, gap: 16 },
  section: { borderTopWidth: 1, borderTopColor: colours.divider, paddingTop: 18, gap: 16 },
  heading: { ...typography.heading, color: colours.ink },
  label: { ...typography.label, color: colours.ink },
  copy: { ...typography.body, color: colours.text },
  secondary: { ...typography.secondary, color: colours.muted },
  link: { minHeight: 56, borderWidth: 2, borderColor: colours.blue, borderRadius: 12, paddingHorizontal: 16,
    paddingVertical: 14, flexDirection: 'row', gap: 12, alignItems: 'center' },
  linkText: { ...typography.label, color: colours.blueDark, textDecorationLine: 'underline' },
  flexText: { flex: 1, flexShrink: 1 },
  pressed: { backgroundColor: colours.infoBackground },
});
