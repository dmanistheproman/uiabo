import { useState } from 'react';
import { Alert, Linking, Pressable, Share, StyleSheet, Text, View } from 'react-native';
import Feather from '@expo/vector-icons/Feather';
import { PageBody, PageHeader } from '../components/AppShell';
import Button from '../components/Button';
import { scoreDescription, isProvisionalScore, comparisonAspects, comparisonFindings, changeVerificationLabel } from '../utils/assessment';
import { resultPresentation, plainSourceStance, datePresentation } from '../utils/resultPresentation';

function Details({ title, children }) {
  const [open, setOpen] = useState(false);
  return <View style={styles.card}>
    <Pressable accessibilityRole="button" accessibilityLabel={`${open ? 'Hide' : 'Show'} ${title}`}
      accessibilityState={{ expanded: open }} onPress={() => setOpen(value => !value)}
      style={({ pressed }) => [styles.toggle, pressed && styles.pressed]}>
      <Text style={[styles.heading, styles.flexText]}>{title}</Text>
      <Feather name={open ? 'chevron-up' : 'chevron-down'} size={24} color="#174E72" accessible={false} />
    </Pressable>
    {open && <View style={styles.detailBody}>{children}</View>}
  </View>;
}

function WebsiteButton({ source, onPress }) {
  return <Pressable accessibilityRole="link" accessibilityLabel={`Open ${source.publisher} website`}
    onPress={() => onPress(source.forecast?.reader_url || source.url)} style={({ pressed }) => [styles.websiteButton, pressed && styles.pressed]}>
    <Text style={[styles.linkText, styles.flexText]}>{source.forecast?.reader_url ? 'Open latest forecast' : 'Open website'}</Text>
    <Feather name="external-link" size={22} color="#174E72" accessible={false} />
  </Pressable>;
}

export default function ResultScreen({ result, onNavigate }) {
  const summary = resultPresentation(result);
  const failed = result.processing_status === 'failed';
  const score = result.misinformation_risk_score;
  const provisional = isProvisionalScore(result);
  const timing = datePresentation(result.date_context);
  const forecast = result.forecast_context;
  const sources = result.evidence || [];
  const limitations = (result.uncertainty_reasons || []).filter(reason =>
    !reason.startsWith('The risk indicator uses prototype rules;') && !reason.startsWith('Assumed date:'));

  async function openSource(url) {
    if (!/^https?:\/\//i.test(url)) return;
    try { await Linking.openURL(url); }
    catch { Alert.alert('Could not open website', 'Please try again when you are connected.'); }
  }
  async function share() {
    try {
      const scoreText = score == null ? '' : `\nMisinformation risk score: ${score}/100${provisional ? ' — Unverified (provisional)' : ''}.\n${scoreDescription(result)}\n`;
      await Share.share({ message: `UIABO result: ${summary.title}\n${result.extracted_claim || result.original_text}\n\n${summary.meaning}\n${scoreText}${timing ? `\n${timing.explanation}\n${timing.caution}\n` : ''}\n${result.explanation}\n\n${summary.action}\n\nSources:\n${sources.map(item => item.url).join('\n')}\n\nAutomated checks can make mistakes.` });
    } catch { Alert.alert('Could not share', 'Please try again.'); }
  }

  return <View style={{ flex: 1 }}>
    <PageHeader title="Your result" onBack={() => onNavigate('results')} />
    <PageBody>
      <View style={[styles.summary, { backgroundColor: summary.background, borderColor: summary.color }]}>
        <Feather name={summary.icon} size={32} color={summary.color} accessible={false} />
        <Text accessibilityRole="header" style={[styles.title, { color: summary.color }]}>{summary.title}</Text>
        <Text style={styles.copy}>{summary.meaning}</Text>
        {!failed && <View style={styles.riskScore}>
          <Text accessibilityRole="header" style={styles.heading}>Misinformation risk score:</Text>
          {score == null ? <>
            <Text style={styles.heading}>{summary.outcome === 'not_checkable' ? 'No factual claim to score' : 'Not enough information to give a score'}</Text>
            <Text style={styles.secondary}>No score does not mean zero risk.</Text>
            {result.checkable !== false && summary.outcome !== 'not_checkable' && <Text style={styles.secondary}>This saved check has no score. Check the message again to use the updated scoring.</Text>}
          </> : <>
            <Text accessibilityLabel={`Risk score: ${score} out of 100${provisional ? ', unverified, provisional score' : ''}`} style={styles.scoreValue}>
              {score}<Text style={styles.scoreTotal}> / 100</Text>
            </Text>
            {provisional ? <>
              <Text style={styles.label}>Unverified — provisional score</Text>
              <Text style={styles.secondary}>{scoreDescription(result)}</Text>
            </> : <Text style={styles.secondary}>Lower means less concern. Higher means more concern. This is not a percentage chance that the claim is false.</Text>}
            {!result.scoring && <Text style={styles.secondary}>This saved score uses older rules. Check the message again for an updated score.</Text>}
          </>}
        </View>}
        <View style={styles.action}>
          <Text accessibilityRole="header" style={styles.heading}>What you should do</Text>
          <Text style={styles.copy}>{summary.action}</Text>
        </View>
      </View>

      <View style={styles.card}>
        <Text accessibilityRole="header" style={styles.heading}>{failed ? 'Your message' : 'The claim we checked'}</Text>
        <Text selectable style={styles.copy}>{result.extracted_claim || result.original_text}</Text>
      </View>

      {!failed && !!timing && <View style={styles.card}>
        <Text accessibilityRole="header" style={styles.heading}>{timing.title}</Text>
        <Text style={styles.copy}>{timing.explanation}</Text>
        <Text style={styles.copy}>{timing.caution}</Text>
        <Button secondary onPress={() => onNavigate('text', { draft: { text: result.original_text,
          correctYear: result.date_context.basis === 'assumed_current_year' || !result.date_context.basis,
          correctDate: true } })}>{timing.action}</Button>
      </View>}

      {!failed && !!forecast && <View style={styles.card}>
        <Text accessibilityRole="header" style={styles.heading}>What the forecast says</Text>
        <Text style={styles.copy}>{forecast.explanation}</Text>
        {!!forecast.issued_at && <Text style={styles.secondary}>Forecast issued {new Date(forecast.issued_at).toLocaleString()}</Text>}
        {forecast.limitations?.map((reason, index) => <Text key={index} style={styles.secondary}>{reason}</Text>)}
      </View>}

      {!failed && !!result.claim_context?.assumptions?.length && <Details title="How we read your message">
        {result.claim_context.assumptions.map((reason, index) => <Text key={index} style={styles.copy}>{reason}</Text>)}
      </Details>}

      {failed ? <>
        <Details title="What went wrong?">
          <Text style={styles.copy}>{result.message}</Text>
        </Details>
        <Button onPress={() => onNavigate('text')}>Try another check</Button>
      </> : <>
        <Details title="Why this result?">
          <Text style={styles.copy}>{result.explanation}</Text>
          {!!result.policy_context && <View style={styles.section}>
            <Text accessibilityRole="header" style={styles.heading}>{result.policy_context.policy_scope === 'comparable_policy' ? 'What the official information says' : 'Related official information'}</Text>
            <Text selectable style={styles.copy}>{result.policy_context.published_policy_summary}</Text>
            <Text style={styles.label}>The reported change: {changeVerificationLabel(result.policy_context.change_status)}</Text>
            <Text style={styles.copy}>{result.policy_context.change_summary}</Text>
          </View>}
          {!!limitations.length && <View style={styles.section}>
            <Text accessibilityRole="header" style={styles.heading}>What this check could not settle</Text>
            {limitations.map((reason, index) => <Text key={index} style={styles.copy}>{reason}</Text>)}
          </View>}
          {result.warnings?.map((warning, index) => <Text key={`warning-${index}`} style={styles.copy}>{warning}</Text>)}
          {!!result.recommended_action && <Text style={styles.copy}>{result.recommended_action}</Text>}
        </Details>

        <Text accessibilityRole="header" style={styles.heading}>Read the sources</Text>
        <Text style={styles.copy}>{sources.length ? 'See where the information came from. You can read it here or open the original website.' : 'No sources were saved with this result. This does not mean the claim is false.'}</Text>
        {sources.map((source, index) => <View key={source.evidence_id} style={styles.source}>
          <Text style={styles.label}>{index + 1}. {source.publisher}</Text>
          <Text accessibilityRole="header" style={styles.heading}>{source.title}</Text>
          <Text style={styles.secondary}>{plainSourceStance(source.stance)}</Text>
          <Details title="Read source details">
            {!!source.assessment_reason && <Text style={styles.copy}>{source.assessment_reason}</Text>}
            <Text style={styles.label}>{source.forecast ? 'Values from the official forecast' : source.evidence_quote ? 'Words from this source' : 'Source passage'}</Text>
            <Text selectable style={styles.quote}>{source.evidence_quote || source.passage}</Text>
            {!!source.evidence_quote && source.evidence_quote !== source.passage && <Details title="Read the surrounding text">
              <Text selectable style={styles.copy}>{source.passage}</Text>
            </Details>}
            <Text style={styles.secondary}>{source.published_at ? `Published ${source.published_at}` : 'Publication date not available'}</Text>
          </Details>
          <WebsiteButton source={source} onPress={openSource} />
        </View>)}

        {!!result.claim_comparisons?.length && <Details title="Compare the details">
          <Text style={styles.copy}>A different rule does not always prove a message wrong. Check who the rule applies to and when it starts.</Text>
          {result.claim_comparisons.map((part, index) => {
            const source = sources.find(item => item.evidence_id === part.evidence_id);
            return <View key={index} style={styles.section}>
              <Text accessibilityRole="header" style={styles.heading}>{comparisonAspects[part.aspect] || 'Rule detail'}</Text>
              <Text selectable style={styles.copy}>The message says: {part.claim_text}</Text>
              <Text style={styles.label}>{comparisonFindings[part.finding] || 'Not confirmed'}</Text>
              <Text style={styles.copy}>{part.explanation}</Text>
              {!!part.scope_limitation && <Text style={styles.copy}>{part.scope_limitation}</Text>}
              {part.finding !== 'unresolved' && !part.applies_to_claim && <Text style={styles.copy}>We could not confirm that this rule applies to the circumstances in the message.</Text>}
              {!!part.evidence_quote && <Text selectable style={styles.quote}>{part.evidence_quote}</Text>}
              {!!source && <><Text style={styles.label}>{source.publisher}</Text><WebsiteButton source={source} onPress={openSource} /></>}
            </View>;
          })}
        </Details>}

        <Details title="About the score">
          <Text style={styles.copy}>{scoreDescription(result)}</Text>
          <Text style={styles.copy}>Use the explanation and sources to decide what to do. A number alone cannot tell you whether to trust a message.</Text>
        </Details>
        <Text style={styles.secondary}>Automated checks can make mistakes. Read the sources before you share.</Text>
        <Button secondary onPress={share}>Share this result</Button>
      </>}
      <Button secondary onPress={() => onNavigate('results')}>Back to saved results</Button>
      <Text style={styles.secondary}>Saved {new Date(result.created_at).toLocaleString()}</Text>
    </PageBody>
  </View>;
}

const styles = StyleSheet.create({
  summary: { borderRadius: 18, borderWidth: 2, padding: 20, gap: 14 },
  title: { fontWeight: '800', fontSize: 27, lineHeight: 35 },
  riskScore: { backgroundColor: 'white', borderRadius: 12, padding: 16, gap: 10 },
  scoreValue: { color: '#173447', fontWeight: '800', fontSize: 46, lineHeight: 58 },
  scoreTotal: { fontWeight: '600', fontSize: 24 },
  card: { borderRadius: 16, backgroundColor: 'white', borderWidth: 1, borderColor: '#CCDCE5', padding: 16, gap: 14 },
  source: { borderRadius: 16, backgroundColor: 'white', borderWidth: 1, borderColor: '#CCDCE5', padding: 16, gap: 14 },
  heading: { color: '#173447', fontWeight: '700', fontSize: 21, lineHeight: 29 },
  label: { color: '#173447', fontWeight: '700', fontSize: 18, lineHeight: 27 },
  copy: { color: '#243E50', fontSize: 18, lineHeight: 28 },
  secondary: { color: '#465D6B', fontSize: 16, lineHeight: 25 },
  bold: { fontWeight: '700' },
  action: { borderTopWidth: 1, borderTopColor: '#B8C9C6', paddingTop: 16, gap: 10 },
  toggle: { minHeight: 56, flexDirection: 'row', alignItems: 'center', gap: 12, paddingVertical: 6 },
  flexText: { flex: 1, flexShrink: 1 },
  pressed: { opacity: 0.7 },
  detailBody: { gap: 16 },
  section: { borderTopWidth: 1, borderTopColor: '#D5E1E8', paddingTop: 18, gap: 14 },
  quote: { color: '#243E50', fontSize: 18, lineHeight: 28, borderLeftWidth: 3, borderLeftColor: '#427494', paddingLeft: 14 },
  websiteButton: { minHeight: 56, borderWidth: 2, borderColor: '#24628D', borderRadius: 12, paddingHorizontal: 16, paddingVertical: 14, flexDirection: 'row', gap: 12, alignItems: 'center' },
  linkText: { color: '#174E72', fontWeight: '700', fontSize: 18, lineHeight: 27 },
});
