import React from 'react';
import { Pressable, ScrollView, StyleSheet, Text, View, useWindowDimensions } from 'react-native';
import Feather from '@expo/vector-icons/Feather';
import { colours, typography } from '../theme';

export function PageHeader({ title, onBack, badge, children }) {
  const { width, fontScale } = useWindowDimensions();
  const stacked = fontScale > 1.3 || width < 360;
  const titleElement = !!title && <Text accessibilityRole="header" style={[styles.title, stacked && styles.stackedTitle]}>{title}</Text>;
  return <View style={styles.header}>
    <View style={styles.headerRow}>
    {onBack ? <Pressable accessibilityRole="button" accessibilityLabel="Back" onPress={onBack} style={styles.headerButton}>
      <Feather name="chevron-left" size={28} color={colours.blueDark} />
    </Pressable> : <Text style={styles.brand}>uiabo<Text style={{ color: colours.teal }}>.</Text></Text>}
    {!stacked && titleElement}
    {children || (badge ? <Text style={styles.badge}>{badge}</Text> : <View style={{ width: 56 }} />)}
    </View>
    {stacked && titleElement}
  </View>;
}

export function BottomTabs({ active, onNavigate, disabled = false }) {
  const { fontScale, width } = useWindowDimensions();
  const wrapTabs = fontScale > 1.3 || width < 360;
  return <View style={[styles.tabs, wrapTabs && styles.wrappedTabs]}>
    {[['home', 'Home', 'home'], ['results', 'Results', 'list'], ['help', 'Help', 'help-circle'], ['profile', 'Profile', 'user']].map(([page, label, icon]) => (
      <Pressable key={page} accessibilityRole="tab" accessibilityState={{ selected: active === page, disabled }}
        accessibilityLabel={label} disabled={disabled} onPress={() => onNavigate(page)}
        style={({ pressed }) => [styles.tab, wrapTabs && styles.wrappedTab, active === page && styles.selectedTab, pressed && styles.pressedTab]}>
        <Feather name={icon} size={24} color={active === page ? colours.teal : colours.muted} />
        <Text style={[styles.tabLabel, active === page && styles.selectedLabel]}>{label}</Text>
      </Pressable>
    ))}
  </View>;
}

export function PageBody({ children, contentContainerStyle, ...props }) {
  return <ScrollView {...props} keyboardShouldPersistTaps="handled" contentContainerStyle={[styles.body, contentContainerStyle]}>{children}</ScrollView>;
}

const styles = StyleSheet.create({
  header: { paddingHorizontal: 18, paddingVertical: 10, gap: 10, backgroundColor: colours.white, borderBottomColor: colours.divider, borderBottomWidth: 1 },
  headerRow: { minHeight: 56, gap: 12, flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' },
  headerButton: { width: 56, height: 56, borderWidth: 2, borderColor: colours.border, borderRadius: 12, alignItems: 'center', justifyContent: 'center' },
  brand: { ...typography.title, color: colours.blueDark, fontWeight: '800', flexShrink: 1 },
  title: { ...typography.heading, color: colours.ink, flex: 1, textAlign: 'center' },
  stackedTitle: { flex: 0, textAlign: 'left' },
  badge: { ...typography.small, backgroundColor: colours.infoBackground, color: colours.blueDark, fontWeight: '700', paddingHorizontal: 10, paddingVertical: 8, borderRadius: 16, flexShrink: 1 },
  tabs: { flexDirection: 'row', backgroundColor: colours.white, borderTopColor: colours.divider, borderTopWidth: 1, padding: 6, gap: 2 },
  wrappedTabs: { flexWrap: 'wrap' },
  tab: { flex: 1, alignItems: 'center', justifyContent: 'center', gap: 4, minHeight: 64, paddingVertical: 8, paddingHorizontal: 2, borderTopWidth: 3, borderTopColor: 'transparent', borderRadius: 8 },
  wrappedTab: { flex: 0, flexBasis: '49%', flexGrow: 1, flexDirection: 'row', gap: 8 },
  selectedTab: { backgroundColor: colours.infoBackground, borderTopColor: colours.teal },
  pressedTab: { backgroundColor: colours.infoBackground },
  tabLabel: { ...typography.tab, color: colours.muted, textAlign: 'center', flexShrink: 1 },
  selectedLabel: { color: colours.teal, fontWeight: '700' },
  body: { padding: 20, gap: 20, paddingBottom: 32 },
});
