import { useState } from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';
import Feather from '@expo/vector-icons/Feather';
import { colours, typography } from '../theme';

export default function FeatureExplanation({ title = 'How this works', children }) {
  const [expanded, setExpanded] = useState(false);

  return <View style={styles.card}>
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={`${expanded ? 'Hide' : 'Show'} ${title.toLowerCase()}`}
      accessibilityState={{ expanded }}
      onPress={() => setExpanded(value => !value)}
      style={({ pressed }) => [styles.toggle, pressed && styles.pressed]}
    >
      <Text style={styles.title}>{title}</Text>
      <Feather name={expanded ? 'chevron-up' : 'chevron-down'} size={26} color={colours.blueDark} accessible={false} />
    </Pressable>
    {expanded && <View style={styles.body}>{children}</View>}
  </View>;
}

const styles = StyleSheet.create({
  card: { backgroundColor: colours.infoBackground, borderColor: colours.border, borderWidth: 1, borderRadius: 14, overflow: 'hidden' },
  toggle: { minHeight: 60, paddingHorizontal: 18, paddingVertical: 14, flexDirection: 'row', alignItems: 'center', gap: 14 },
  title: { ...typography.label, color: colours.ink, flex: 1 },
  pressed: { backgroundColor: colours.divider },
  body: { borderTopWidth: 1, borderTopColor: colours.divider, padding: 18, gap: 12 },
});
