import { colours, typography } from '../theme';
import ReportResultPanel from '../components/ReportResultPanel';
import SavedResultImage from '../components/SavedResultImage';

import React from 'react';

import {
  Alert,
  Linking,
  Pressable,
  StyleSheet,
  Text,
  View,
} from 'react-native';

import Feather from '@expo/vector-icons/Feather';

import { PageBody, PageHeader } from '../components/AppShell';
import Button from '../components/Button';

const concernStyles = {
  'Low Concern': {
    color: colours.success,
    backgroundColor: colours.successBackground,
    icon: 'check-circle',
    message:
      'The available evidence does not indicate a strong concern, but this does not guarantee that the post is accurate.',
  },
  'Needs Caution': {
    color: colours.warning,
    backgroundColor: colours.warningBackground,
    icon: 'alert-triangle',
    message:
      'Some aspects of this post may need further verification. Review the explanation and sources before drawing a conclusion.',
  },
  'High Concern': {
    color: colours.danger,
    backgroundColor: colours.dangerBackground,
    icon: 'alert-circle',
    message:
      'The available evidence raises significant concerns about the post. Review the explanation and supporting sources.',
  },
  'Not Enough Information': {
    color: colours.blueDark,
    backgroundColor: colours.infoBackground,
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
        <Pressable
          accessibilityRole="link"
          accessibilityLabel={`Open source: ${item.title || 'Source website'}`}
          accessibilityHint="Opens the source in your browser"
          onPress={openSource}
          style={({ pressed }) => [styles.link, pressed && styles.pressed]}
        >
          <Text style={styles.linkText}>Open source</Text>
          <Feather name="external-link" size={22} color={colours.blueDark} accessible={false} />
        </Pressable>
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
  const color = isFailed ? colours.danger : appearance.color;
  const summaryBackground = isFailed
    ? colours.dangerBackground
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
        <SavedResultImage result={result} />
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
            Caption we checked
          </Text>

          <Text style={caption ? styles.bodyText : styles.placeholder}>
            {caption || 'No caption was available for this image.'}
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
        <ReportResultPanel result={result} />
      </PageBody>
    </View>
  );
}

const styles = StyleSheet.create({
  summary: { borderRadius: 18, borderWidth: 2, padding: 20, gap: 16 },
  title: { ...typography.title },
  summaryCopy: { ...typography.body, color: colours.text },
  card: { borderRadius: 16, backgroundColor: colours.white, borderWidth: 1, borderColor: colours.divider, padding: 18, gap: 16 },
  heading: { ...typography.heading, color: colours.ink },
  filename: { ...typography.secondary, color: colours.text },
  bodyText: { ...typography.body, color: colours.text },
  secondary: { ...typography.secondary, color: colours.muted },
  placeholder: { ...typography.secondary, color: colours.muted },
  evidenceList: { gap: 16 },
  evidenceCard: { borderWidth: 1, borderColor: colours.divider, borderRadius: 12, padding: 14, gap: 14 },
  sourceHeader: { flexDirection: 'row', alignItems: 'center', gap: 12 },
  sourceNumber: { minWidth: 36, minHeight: 36, padding: 6, borderRadius: 18, backgroundColor: colours.infoBackground, alignItems: 'center', justifyContent: 'center' },
  sourceNumberText: { ...typography.small, color: colours.blueDark, fontWeight: '700' },
  relationship: { ...typography.secondary, color: colours.muted, fontWeight: '600', flex: 1, flexShrink: 1 },
  sourceTitle: { ...typography.label, color: colours.ink },
  link: { minHeight: 56, borderWidth: 2, borderColor: colours.blue, borderRadius: 12, paddingHorizontal: 14, paddingVertical: 12, flexDirection: 'row', alignItems: 'center', gap: 12 },
  linkText: { ...typography.label, color: colours.blueDark, textDecorationLine: 'underline', flex: 1, flexShrink: 1 },
  pressed: { backgroundColor: colours.infoBackground },
  disclaimer: { ...typography.secondary, color: colours.muted },
});
