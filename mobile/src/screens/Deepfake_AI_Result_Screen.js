import { colours, typography } from '../theme';
import ReportResultPanel from '../components/ReportResultPanel';
import SavedResultImage from '../components/SavedResultImage';
import FeatureExplanation from '../components/FeatureExplanation';
import React from 'react';

import {
  StyleSheet,
  Text,
  View,
} from 'react-native';

import Feather from '@expo/vector-icons/Feather';

import { PageBody, PageHeader } from '../components/AppShell';

import Button from '../components/Button';

export default function Deepfake_AI_Result_Screen({ result, onNavigate, onBack }) {
  const formatPercent = (value) => {
    const num = Number(value);
    // Checks if it's a valid finite number AND greater than 0
    return Number.isFinite(num) && num > 0 ? `${(num * 100).toFixed(1)}%` : '-';
  };

  const realPercent = formatPercent(result?.real_probability);
  const fakePercent = formatPercent(result?.fake_probability);

  const isReal = result?.label === 'Real';
  const isFake = result?.label === 'Fake';
  const isUncertain = result?.label === 'Uncertain';

  const getAnalysisMessage = () => {
    if (isUncertain) {
      return 'The analysis could not reach a sufficiently reliable conclusion. Treat this result as inconclusive.';
    }
    if (isReal || isFake) {
      return `The image analysis model classified this image as ${result.label}.`;
    }
    // Fallback when it is none of the three
    return 'Analysis of this image failed. Your allowance was not consumed, please try again later.';
  };

  const resultIcon = isUncertain
    ? 'help-circle'
    : isReal
      ? 'check-circle'
      : 'alert-circle';

  const resultColor = isUncertain
    ? colours.warning
    : isReal
      ? colours.success
      : isFake
        ? colours.danger
        : colours.danger;

  const summaryStyle = isReal
    ? styles.realSummary
    : isFake
      ? styles.fakeSummary
      : null;

  const titleStyle = isReal
    ? styles.realTitle
    : isFake
      ? styles.fakeTitle
      : null;

  const explanation = result?.explanation;

  const filename = result?.filename;

  const visualEvidence = explanation?.visual_evidence;
  const reasoning = explanation?.reasoning;
  const limitations = explanation?.limitations;



  return (
    <View style={{ flex: 1 }}>
      <PageHeader
        title="Deepfake/AI analysis result"
        onBack={onBack || (() => onNavigate('deepfakeAI'))}
        badge="Premium"
      />

      <PageBody>
        <SavedResultImage result={result} />
        <View style={[styles.summary, summaryStyle]}>
          <Feather
            name={resultIcon}
            size={42}
            color={resultColor}
            accessible={false}
          />

          <Text accessibilityRole="header" style={[styles.title, titleStyle]}>
            Model classification: {result?.label || 'Unavailable'}
          </Text>

          <Text style={styles.copy}>
            {getAnalysisMessage()}
          </Text>
        </View>

        <View style={styles.card}>
          <Text accessibilityRole="header" style={styles.heading}>
            Image filename
          </Text>

          <Text style={styles.filename}>
            {filename || 'Filename unavailable'}
          </Text>
        </View>

        <FeatureExplanation title="Model probabilities" key={result?.result_id}>
          <View style={styles.row}>
            <Text style={styles.label}>Real</Text>
            <Text style={styles.value}>{realPercent}</Text>
          </View>

          <View style={styles.row}>
            <Text style={styles.label}>AI-generated</Text>
            <Text style={styles.value}>{fakePercent}</Text>
          </View>
        </FeatureExplanation>

        <View style={styles.card}>
          <Text accessibilityRole="header" style={styles.heading}>
            Explanation
          </Text>

          <Text style={styles.explanationHeading}>
            Visual evidence
          </Text>

          {Array.isArray(visualEvidence) && visualEvidence.length > 0 ? (
            visualEvidence.map((item, index) => (
              <View key={`${index}-${item}`} style={styles.evidenceRow}>
                <Text style={styles.bullet}>•</Text>
                <Text style={styles.explanationText}>{item}</Text>
              </View>
            ))
          ) : (
            <Text style={styles.placeholder}>
              Visual evidence will appear here when available.
            </Text>
          )}

          <Text style={styles.explanationHeading}>
            Reasoning
          </Text>

          <Text style={reasoning ? styles.explanationText : styles.placeholder}>
            {reasoning || 'The reasoning behind this classification will appear here.'}
          </Text>

          <Text style={styles.explanationHeading}>
            Limitations
          </Text>

          <Text style={limitations ? styles.explanationText : styles.placeholder}>
            {limitations || 'Limitations of this analysis will appear here.'}
          </Text>
        </View>

        <Text style={styles.disclaimer}>
          This is an automated model result and should not be treated as
          definitive proof that an image is real or AI-generated.
        </Text>

        <Button onPress={() => onNavigate('deepfakeAI')}>
          Check another image
        </Button>
        <ReportResultPanel result={result} />
      </PageBody>
    </View>
  );
}

const styles = StyleSheet.create({
  summary: { borderRadius: 18, backgroundColor: colours.white, borderWidth: 2, borderColor: colours.divider, padding: 20, gap: 16 },
  realSummary: { backgroundColor: colours.successBackground, borderColor: colours.success },
  fakeSummary: { backgroundColor: colours.dangerBackground, borderColor: colours.danger },
  realTitle: { color: colours.success },
  fakeTitle: { color: colours.danger },
  title: { ...typography.title, color: colours.ink },
  copy: { ...typography.body, color: colours.text },
  card: { borderRadius: 16, backgroundColor: colours.white, borderWidth: 1, borderColor: colours.divider, padding: 18, gap: 16 },
  heading: { ...typography.heading, color: colours.ink },
  row: { flexDirection: 'row', flexWrap: 'wrap', justifyContent: 'space-between', alignItems: 'baseline', columnGap: 16, rowGap: 8, borderTopWidth: 1, borderTopColor: colours.divider, paddingTop: 16 },
  label: { ...typography.body, color: colours.text, flexShrink: 1 },
  value: { ...typography.label, color: colours.ink },
  filename: { ...typography.secondary, color: colours.text },
  explanationHeading: { ...typography.label, color: colours.ink },
  explanationText: { ...typography.body, color: colours.text, flexShrink: 1 },
  placeholder: { ...typography.secondary, color: colours.muted },
  evidenceRow: { flexDirection: 'row', alignItems: 'flex-start', gap: 12 },
  bullet: { ...typography.body, color: colours.blueDark },
  disclaimer: { ...typography.secondary, color: colours.muted },
});
