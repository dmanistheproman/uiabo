
import React from 'react';

import {
  Alert,
  Linking,
  StyleSheet,
  Text,
  View,
} from 'react-native';

import Feather from '@expo/vector-icons/Feather';

import { PageBody, PageHeader } from '../components/AppShell';
import Button from '../components/Button';

const concernStyles = {
  'Low Concern': {
    color: '#197551',
    backgroundColor: '#E4F4EC',
    icon: 'check-circle',
    message:
      'The available evidence does not indicate a strong concern, but this does not guarantee that the post is accurate.',
  },
  'Needs Caution': {
    color: '#896306',
    backgroundColor: '#FFF4D2',
    icon: 'alert-triangle',
    message:
      'Some aspects of this post may need further verification. Review the explanation and sources before drawing a conclusion.',
  },
  'High Concern': {
    color: '#AA2825',
    backgroundColor: '#FBE9E7',
    icon: 'alert-circle',
    message:
      'The available evidence raises significant concerns about the post. Review the explanation and supporting sources.',
  },
  'Not Enough Information': {
    color: '#285B7D',
    backgroundColor: '#E5F3FA',
    icon: 'help-circle',
    message:
      'There was not enough usable information to assess the post reliably. This does not mean the post is necessarily true or false.',
  },
};

function normaliseConcernLabel(label) {
  const value = String(label || '')
    .trim()
    .toLowerCase()
    .replace(/\s+/g, ' ');

  if (value === 'low concern') return 'Low Concern';
  if (value === 'needs caution') return 'Needs Caution';
  if (value === 'high concern') return 'High Concern';

  return 'Not Enough Information';
}

function EvidenceCard({ item, index }) {
  const relationship = String(item?.relationship || 'context')
    .toLowerCase();

  const relationshipLabel = {
    supports: 'Supports the claim',
    contradicts: 'Contradicts the claim',
    context: 'Provides context',
  }[relationship] || 'Provides context';

  async function openSource() {
    const url = item?.url;

    // Only open ordinary HTTP(S) web links.
    if (
      typeof url !== 'string' ||
      !/^https?:\/\/\S+$/i.test(url)
    ) {
      Alert.alert(
        'Link unavailable',
        'This source does not have a valid web address.',
      );
      return;
    }

    try {
      await Linking.openURL(url);
    } catch (error) {
      Alert.alert(
        'Unable to open link',
        'Please try opening this source again.',
      );
    }
  }

  return (
    <View style={styles.evidenceCard}>
      <View style={styles.sourceHeader}>
        <View style={styles.sourceNumber}>
          <Text style={styles.sourceNumberText}>
            {index + 1}
          </Text>
        </View>

        <Text style={styles.relationship}>
          {relationshipLabel}
        </Text>
      </View>

      <Text style={styles.sourceTitle}>
        {item?.title || 'Untitled source'}
      </Text>

      {!!item?.summary && (
        <Text style={styles.bodyText}>
          {item.summary}
        </Text>
      )}

      {!!item?.url && (
        <Text
          accessibilityRole="link"
          accessibilityHint="Opens the source in your browser"
          onPress={openSource}
          style={styles.link}
        >
          Open source <Feather name="external-link" size={13} />
        </Text>
      )}
    </View>
  );
}

export default function Image_Context_Result_Screen({
  result,
  onNavigate,
  onBack,
}) {
  const label = normaliseConcernLabel(result?.concern_label);
  const appearance = concernStyles[label];

  const evidenceLinks = Array.isArray(result?.evidence_links)
    ? result.evidence_links
    : [];

  const filename = result?.image_filename;
  const caption = result?.extracted_caption;
  const explanation = result?.explanation;

  const isFailed = result?.processing_status === 'failed';

  const displayLabel = isFailed ? 'Analysis failed' : label;

  const icon = isFailed ? 'x-circle' : appearance.icon;
  const color = isFailed ? '#AA2825' : appearance.color;
  const summaryBackground = isFailed
    ? '#FBE9E7'
    : appearance.backgroundColor;

  const message = isFailed
    ? result?.message ||
      'The image context analysis could not be completed. Please try again.'
    : appearance.message;

  return (
    <View style={{ flex: 1 }}>
      <PageHeader
        title="Image context result"
        onBack={onBack || (() => onNavigate('imageContext'))}
      />

      <PageBody>
        <View
          style={[
            styles.summary,
            { backgroundColor: summaryBackground, borderColor: color },
          ]}
        >
          <Feather
            name={icon}
            size={42}
            color={color}
            accessible={false}
          />

          <Text
            accessibilityRole="header"
            style={[styles.title, { color }]}
          >
            {displayLabel}
          </Text>

          <Text style={styles.summaryCopy}>
            {message}
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
            Extracted caption
          </Text>

          <Text style={caption ? styles.bodyText : styles.placeholder}>
            {caption || 'No caption could be extracted from this image.'}
          </Text>
        </View>

        <View style={styles.card}>
          <Text accessibilityRole="header" style={styles.heading}>
            Explanation
          </Text>

          <Text style={explanation ? styles.bodyText : styles.placeholder}>
            {explanation ||
              'An explanation is unavailable for this analysis.'}
          </Text>
        </View>

        {!isFailed && (
          <View style={styles.card}>
            <Text accessibilityRole="header" style={styles.heading}>
              Evidence sources
            </Text>

            <Text style={styles.secondary}>
              These additional sources were retrieved during the check. Review
              them directly to understand how they relate to the post.

            </Text>

            {evidenceLinks.length > 0 ? (
              <View style={styles.evidenceList}>
                {evidenceLinks.slice(0, 2).map((item, index) => (
                  <EvidenceCard
                    key={`${item?.url || 'source'}-${index}`}
                    item={item}
                    index={index}
                  />
                ))}
              </View>
            ) : (
              <Text style={styles.placeholder}>
                No additional evidence links.
              </Text>
            )}
          </View>
        )}

        <Text style={styles.disclaimer}>
          This is an automated assessment, not definitive proof that a
          social media post is true or false. Sources may be incomplete
          or may not directly establish the accuracy of the original post.
        </Text>

        <Button onPress={() => onNavigate('imageContext')}>
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
    borderWidth: 1,
    padding: 20,
    gap: 14,
  },

  title: {
    fontWeight: '800',
    fontSize: 27,
    lineHeight: 35,
    textAlign: 'center',
  },

  summaryCopy: {
    color: '#243E50',
    fontSize: 16,
    lineHeight: 25,
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

  filename: {
    color: '#243E50',
    fontSize: 16,
    lineHeight: 24,
    fontWeight: '600',
    overflow: 'hidden',
  },

  bodyText: {
    color: '#243E50',
    fontSize: 16,
    lineHeight: 25,
  },

  secondary: {
    color: '#465D6B',
    fontSize: 14,
    lineHeight: 22,
  },

  placeholder: {
    color: '#71818B',
    fontSize: 16,
    lineHeight: 25,
    fontStyle: 'italic',
  },

  evidenceList: {
    gap: 12,
  },

  evidenceCard: {
    borderWidth: 1,
    borderColor: '#D5E1E8',
    borderRadius: 12,
    padding: 14,
    gap: 10,
  },

  sourceHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 9,
  },

  sourceNumber: {
    width: 25,
    height: 25,
    borderRadius: 13,
    backgroundColor: '#E5F3FA',
    alignItems: 'center',
    justifyContent: 'center',
  },

  sourceNumberText: {
    color: '#174968',
    fontSize: 13,
    fontWeight: '800',
  },

  relationship: {
    color: '#526F83',
    fontSize: 12,
    fontWeight: '700',
  },

  sourceTitle: {
    color: '#173447',
    fontSize: 16,
    lineHeight: 23,
    fontWeight: '700',
  },

  link: {
    color: '#285B7D',
    fontSize: 14,
    lineHeight: 22,
    fontWeight: '700',
    textDecorationLine: 'underline',
  },

  disclaimer: {
    color: '#465D6B',
    fontSize: 14,
    lineHeight: 22,
    textAlign: 'center',
  },
});
