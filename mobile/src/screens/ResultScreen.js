import { colours, typography } from '../theme';
import { useState } from 'react';
import { Alert, Linking, Pressable, Share, StyleSheet, Text, View } from 'react-native';
import Feather from '@expo/vector-icons/Feather';
import { PageBody, PageHeader } from '../components/AppShell';
import Button from '../components/Button';
import { credibilityDetails, componentDetails, comparisonAspects, comparisonFindings, changeVerificationLabel } from '../utils/assessment';
import ReportResultPanel from '../components/ReportResultPanel';
import { resultPresentation, plainSourceStance, datePresentation } from '../utils/resultPresentation';
import { controlFindings } from '../utils/controlInterpretations';
import EvidenceText from '../components/EvidenceText';
import { pdfSeriesTable } from '../utils/pdfEvidence';
import { evidencePresentation } from '../utils/evidencePresentation';
import { evidencePlainText } from '../utils/evidenceMarkdown';
import { webResearchDetails, researchShareText } from '../utils/webResearch';
import ResearchAssessmentPanel from '../components/ResearchAssessmentPanel';

function Details({ title, children }) {
  const [open, setOpen] = useState(false);
  return <View style={styles.card}>
    <Pressable accessibilityRole="button" accessibilityLabel={`${open ? 'Hide' : 'Show'} ${title}`}
      accessibilityState={{ expanded: open }} onPress={() => setOpen(value => !value)}
      style={({ pressed }) => [styles.toggle, pressed && styles.pressed]}>
      <Text style={[styles.heading, styles.flexText]}>{title}</Text>
      <Feather name={open ? 'chevron-up' : 'chevron-down'} size={24} color={colours.blueDark} accessible={false} />
    </Pressable>
    {open && <View style={styles.detailBody}>{children}</View>}
  </View>;
}

function WebsiteButton({ source, onPress }) {
  return <Pressable accessibilityRole="link" accessibilityLabel={`Open ${source.publisher} website`}
    onPress={() => onPress(source.forecast?.reader_url || source.url)} style={({ pressed }) => [styles.websiteButton, pressed && styles.pressed]}>
    <Text style={[styles.linkText, styles.flexText]}>{source.forecast?.reader_url ? 'Open latest forecast' : 'Open website'}</Text>
    <Feather name="external-link" size={22} color={colours.blueDark} accessible={false} />
  </Pressable>;
}

export default function ResultScreen({ result, onNavigate }) {
  const summary = resultPresentation(result);
  const failed = result.processing_status === 'failed';
  const research = webResearchDetails(result);
  const timing = datePresentation(result.date_context);
  const forecast = result.forecast_context;
  const sources = result.evidence || [];
  const components = componentDetails(result);
  const reading = evidencePresentation(result);
  const limitations = (result.uncertainty_reasons || []).filter(reason =>
    !reason.startsWith('The risk indicator uses prototype rules;') && !reason.startsWith('Assumed date:'));

  async function openSource(url) {
    if (!/^https?:\/\//i.test(url)) return;
    try { await Linking.openURL(url); }
    catch { Alert.alert('Could not open website', 'Please try again when you are connected.'); }
  }
  async function share() {
    try {
      if (research) {
        await Share.share({ message: researchShareText(result) });
        return;
      }
      await Share.share({ message: `UIABO result: ${summary.title}\n${result.extracted_claim || result.original_text}\n\n${summary.meaning}\n${timing ? `\n${timing.explanation}\n${timing.caution}\n` : ''}\nWhy this result?\n${evidencePlainText(reading.explanation)}\n\n${credibilityDetails(result)}\n\n${summary.action}\n\nSources:\n${sources.map(item => item.url).join('\n')}\n\nAutomated checks can make mistakes.` });
    } catch { Alert.alert('Could not share', 'Please try again.'); }
  }

  return <View style={{ flex: 1 }}>
    <PageHeader title="Your result" onBack={() => onNavigate('results')} />
    <PageBody>
      <View style={[styles.summary, { backgroundColor: summary.background, borderColor: summary.color }]}>
        <Feather name={summary.icon} size={32} color={summary.color} accessible={false} />
        <Text accessibilityRole="header" style={[styles.title, { color: summary.color }]}>{summary.title}</Text>
        <Text style={styles.copy}>{summary.meaning}</Text>
        <View style={styles.action}>
          <Text accessibilityRole="header" style={styles.heading}>What you should do</Text>
          <Text style={styles.copy}>{summary.action}</Text>
        </View>
      </View>

      <View style={styles.card}>
        <Text accessibilityRole="header" style={styles.heading}>{failed ? 'Your message' : 'The claim we checked'}</Text>
        <Text selectable style={styles.copy}>{result.extracted_claim || result.original_text}</Text>
        {result.input_source === 'ocr' && <Text style={styles.secondary}>This checks the words you reviewed from the image. It does not check whether the image is real.</Text>}
      </View>

      {controlFindings(result).map(finding => <View key={finding.key} style={styles.card}>
        <Text accessibilityRole="header" style={styles.heading}>{finding.title}</Text>
        <Text style={styles.label}>{finding.status}</Text>
        <Text style={styles.copy}>{finding.explanation}</Text>
        {!!finding.citations.length && <Details title="Evidence for this meaning">
          {finding.citations.map((citation, index) => {
            const source = result.evidence?.find(item => item.evidence_id === citation.evidence_id);
            return <View key={index} style={styles.section}>
              <EvidenceText quoted baseURL={source?.url}>{citation.quote}</EvidenceText>
              {!!source && <Text style={styles.secondary}>{source.publisher} — {source.title}</Text>}
            </View>;
          })}
        </Details>}
      </View>)}

      {!failed && !!timing && <View style={styles.card}>
        <Text accessibilityRole="header" style={styles.heading}>{timing.title}</Text>
        <Text style={styles.copy}>{timing.explanation}</Text>
        <Text style={styles.copy}>{timing.caution}</Text>
        <Button secondary onPress={() => onNavigate('text', { draft: { text: result.original_text,
          correctYear: result.date_context.basis === 'assumed_current_year' || !result.date_context.basis,
          correctDate: true, inputSource: result.input_source } })}>{timing.action}</Button>
      </View>}

      {!failed && !!result.plausibility_context && <View style={styles.card}>
        <Text accessibilityRole="header" style={styles.heading}>Why this prediction is unlikely</Text>
        <Text style={styles.copy}>{result.plausibility_context.explanation}</Text>
        {result.plausibility_context.limitations.map((reason, index) => <Text key={index} style={styles.secondary}>{reason}</Text>)}
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
      {!failed && !!result.inference_context && <Details title="Official announcement checks">
        <Text style={styles.copy}>We checked {result.inference_context.subject}.</Text>
        {result.inference_context.limitations.map((reason, index) => <Text key={index} style={styles.secondary}>{reason}</Text>)}
      </Details>}

      {failed ? <>
        <Details title="What went wrong?">
          <Text style={styles.copy}>{result.message}</Text>
        </Details>
        <Button onPress={() => onNavigate(result.input_source === 'ocr' ? 'ocr' : 'text')}>Try another check</Button>
      </> : <>
        {research ? <ResearchAssessmentPanel research={research} onOpenSource={openSource} /> : <>
        <Details title="Why this result?">
          <EvidenceText>{reading.explanation}</EvidenceText>
          <Text style={styles.secondary}>{credibilityDetails(result)}</Text>
          {!!reading.quote && <Details title="Read the evidence">
            <Text style={styles.label}>{reading.source.publisher}</Text>
            <Text style={styles.secondary}>{reading.source.title}</Text>
            <EvidenceText baseURL={reading.source.url}>{reading.quote}</EvidenceText>
            <WebsiteButton source={reading.source} onPress={openSource} />
          </Details>}
          {!!components.length && <View style={styles.section}>
            <Text accessibilityRole="header" style={styles.heading}>The parts we checked</Text>
            <Text style={styles.copy}>We checked the factual parts of your message separately. Read what the evidence establishes for each part.</Text>
            {components.map((part, index) => <View key={part.id || index} style={styles.section}>
              <Text selectable style={styles.label}>{index + 1}. {part.text}</Text>
              <Text style={styles.label}>{part.status}</Text>
              <EvidenceText>{part.explanation}</EvidenceText>
              {!!part.findings.length && <Details title="Read the evidence for this part">
                {part.findings.map((finding, findingIndex) => <View key={findingIndex} style={findingIndex ? styles.section : styles.detailBody}>
                  <Text style={styles.label}>{finding.status}</Text>
                  <EvidenceText>{finding.explanation}</EvidenceText>
                  {!!finding.basis && <Text style={styles.secondary}>{finding.basis}</Text>}
                  {!!finding.limitation && <Text style={styles.secondary}>{finding.limitation}</Text>}
                  {finding.quotes.map((item, quoteIndex) => <View key={`${item.evidence_id}-${quoteIndex}`} style={styles.detailBody}>
                    <EvidenceText quoted baseURL={item.source.url}>{item.quote}</EvidenceText>
                    <Text style={styles.secondary}>{item.source.publisher}</Text>
                    <WebsiteButton source={item.source} onPress={openSource} />
                  </View>)}
                </View>)}
              </Details>}
            </View>)}
          </View>}
          {!!result.policy_context && <View style={styles.section}>
            <Text accessibilityRole="header" style={styles.heading}>{result.policy_context.policy_scope === 'comparable_policy' ? 'What the official information says' : 'Related official information'}</Text>
            <EvidenceText>{result.policy_context.published_policy_summary}</EvidenceText>
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
            {!!source.assessment_reason && <EvidenceText>{source.assessment_reason}</EvidenceText>}
            {!!source.pdf_reading?.document?.series?.length && <Details title="Figures read from the PDF">
              <Text style={styles.copy}>AI read these charts and tables. The numbers were checked against PDF text, but their dates and chart groupings may still be misread. Open the original PDF to check them.</Text>
              {source.pdf_reading.document.series.map((series, i) => <View key={i} style={styles.section}>
                <Text style={styles.label}>{series.metric_label} · Page {series.page}</Text>
                <Text style={styles.copy}>{series.population_label}</Text>
                <EvidenceText>{pdfSeriesTable(series)}</EvidenceText>
              </View>)}
              {source.pdf_reading.document.limitations.map((limit, i) => <Text key={i} style={styles.copy}>{limit}</Text>)}
            </Details>}
            <Text style={styles.label}>{source.climate_record ? 'Values from official climate records' : source.forecast ? 'Values from the official forecast' : source.evidence_quote ? 'Words from this source' : 'Source passage'}</Text>
            <EvidenceText quoted baseURL={source.url}>{source.evidence_quote || source.passage}</EvidenceText>
            {!!source.evidence_quote && source.evidence_quote !== source.passage && <Details title="Read the surrounding text">
              <EvidenceText baseURL={source.url}>{source.passage}</EvidenceText>
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
              {!!part.evidence_quote && <EvidenceText quoted baseURL={source?.url}>{part.evidence_quote}</EvidenceText>}
              {!!source && <><Text style={styles.label}>{source.publisher}</Text><WebsiteButton source={source} onPress={openSource} /></>}
            </View>;
          })}
        </Details>}

        </>}
        <ReportResultPanel result={result} />
        <Text style={styles.secondary}>Automated checks can make mistakes. Read the sources before you share.</Text>
        <Button secondary onPress={share}>Share this result</Button>
      </>}
      <Button secondary onPress={() => onNavigate('results')}>Back to saved results</Button>
      <Text style={styles.secondary}>Saved {new Date(result.created_at).toLocaleString()}</Text>
    </PageBody>
  </View>;
}

const styles = StyleSheet.create({
  summary: { borderRadius: 18, borderWidth: 2, padding: 20, gap: 16 },
  title: { ...typography.title },
  card: { borderRadius: 16, backgroundColor: colours.white, borderWidth: 1, borderColor: colours.divider, padding: 18, gap: 16 },
  source: { borderRadius: 16, backgroundColor: colours.white, borderWidth: 1, borderColor: colours.divider, padding: 18, gap: 16 },
  heading: { ...typography.heading, color: colours.ink },
  label: { ...typography.label, color: colours.ink },
  copy: { ...typography.body, color: colours.text },
  secondary: { ...typography.secondary, color: colours.muted },
  bold: { fontWeight: '700' },
  action: { borderTopWidth: 1, borderTopColor: colours.border, paddingTop: 18, gap: 12 },
  toggle: { minHeight: 56, flexDirection: 'row', alignItems: 'center', gap: 12, paddingVertical: 6 },
  flexText: { flex: 1, flexShrink: 1 },
  pressed: { backgroundColor: colours.infoBackground },
  option: { minHeight: 56, flexDirection: 'row', alignItems: 'center', gap: 12, paddingHorizontal: 14, borderWidth: 2, borderColor: colours.border, borderRadius: 12, paddingVertical: 12 },
  optionSelected: { borderColor: colours.blue, backgroundColor: colours.infoBackground },
  optionText: { ...typography.body, color: colours.text, flex: 1, flexShrink: 1 },
  reportInput: { ...typography.body, backgroundColor: colours.white, minHeight: 150, borderColor: colours.border, borderWidth: 2, borderRadius: 14, padding: 16, color: colours.ink },
  detailBody: { gap: 18 },
  section: { borderTopWidth: 1, borderTopColor: colours.divider, paddingTop: 18, gap: 16 },
  quote: { ...typography.body, color: colours.text, borderLeftWidth: 3, borderLeftColor: colours.blue, paddingLeft: 14 },
  websiteButton: { minHeight: 56, borderWidth: 2, borderColor: colours.blue, borderRadius: 12, paddingHorizontal: 16, paddingVertical: 14, flexDirection: 'row', gap: 12, alignItems: 'center' },
  linkText: { ...typography.label, color: colours.blueDark, textDecorationLine: 'underline' },
});
