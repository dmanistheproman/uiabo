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
  const confidence = Number(result?.confidence);
  const realProbability = Number(result?.real_probability);
  const fakeProbability = Number(result?.fake_probability);
  
  const formatPercent = (value) => {
    const num = Number(value);
    // Checks if it's a valid finite number AND greater than 0
    return Number.isFinite(num) && num > 0 ? `${(num * 100).toFixed(1)}%` : '-';
  };

  const confidencePercent = formatPercent(result?.confidence);
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
    ? '#8A6D1D'
    : isReal
      ? '#197551'
      : isFake
        ? '#AA2825'
        : '#A33A3A';
  
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

        <View style={styles.card}>
          <Text accessibilityRole="header" style={styles.heading}>
            Confidence
          </Text>

          <Text style={styles.score}>
            {confidencePercent}
          </Text>

          <Text style={styles.secondary}>
            This is the model's confidence in its classification.
          </Text>
        </View>

        <View style={styles.card}>
          <Text accessibilityRole="header" style={styles.heading}>
            Model probabilities
          </Text>

          <View style={styles.row}>
            <Text style={styles.label}>Real</Text>
            <Text style={styles.value}>{realPercent}</Text>
          </View>

          <View style={styles.row}>
            <Text style={styles.label}>AI-generated</Text>
            <Text style={styles.value}>{fakePercent}</Text>
          </View>
        </View>

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
      </PageBody>
    </View>
  );
}

const styles = StyleSheet.create({
  summary: {
    alignItems: 'center',
    borderRadius: 18,
    backgroundColor: 'white',
    borderWidth: 1,
    borderColor: '#CCDCE5',
    padding: 20,
    gap: 14,
  },
  realSummary: {
    backgroundColor: '#E4F4EC',
    borderColor: '#197551',
  },
  fakeSummary: {
    backgroundColor: '#FBE9E7',
    borderColor: '#AA2825',
  },
  realTitle: {
    color: '#197551',
  },
  fakeTitle: {
    color: '#AA2825',
  },
  title: {
    color: '#173447',
    fontWeight: '800',
    fontSize: 27,
    lineHeight: 35,
    textAlign: 'center',
  },
  copy: {
    color: '#243E50',
    fontSize: 18,
    lineHeight: 28,
    textAlign: 'center',
  },
  card: {
    borderRadius: 16,
    backgroundColor: 'white',
    borderWidth: 1,
    borderColor: '#CCDCE5',
    padding: 16,
    gap: 12,
  },
  heading: {
    color: '#173447',
    fontWeight: '700',
    fontSize: 21,
    lineHeight: 29,
  },
  score: {
    color: '#173447',
    fontWeight: '800',
    fontSize: 46,
    lineHeight: 58,
  },
  secondary: {
    color: '#465D6B',
    fontSize: 16,
    lineHeight: 25,
  },
  row: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    borderTopWidth: 1,
    borderTopColor: '#D5E1E8',
    paddingTop: 12,
  },
  label: {
    color: '#243E50',
    fontSize: 18,
    lineHeight: 27,
  },
  value: {
    color: '#173447',
    fontWeight: '700',
    fontSize: 18,
    lineHeight: 27,
  },
  filename: {
    color: '#243E50',
    fontSize: 16,
    lineHeight: 24,
    fontWeight: '600',
    overflow: 'hidden',
  },
  explanationHeading: {
  color: '#173447',
  fontWeight: '700',
  fontSize: 17,
  lineHeight: 25,
  },
  explanationText: {
    color: '#243E50',
    fontSize: 16,
    lineHeight: 25,
  },
  placeholder: {
    color: '#71818B',
    fontSize: 16,
    lineHeight: 25,
    fontStyle: 'italic',
  },
  evidenceRow: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    gap: 8,
  },
  bullet: {
    color: '#174E72',
    fontSize: 18,
    lineHeight: 25,
  },
  disclaimer: {
    color: '#465D6B',
    fontSize: 15,
    lineHeight: 23,
    textAlign: 'center',
  },
});