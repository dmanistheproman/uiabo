import React from 'react';
import { Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';
import Feather from '@expo/vector-icons/Feather';
import { colours } from '../theme';

export function PageHeader({ title, onBack, badge, children }) {
  return <View style={styles.header}>
    {onBack ? <Pressable accessibilityRole="button" accessibilityLabel="Back" onPress={onBack} style={styles.headerButton}>
      <Feather name="chevron-left" size={22} color={colours.blueDark} />
    </Pressable> : <Text style={styles.brand}>uiabo<Text style={{ color: '#008B89' }}>.</Text></Text>}
    {!!title && <Text style={styles.title}>{title}</Text>}
    {children || (badge ? <Text style={styles.badge}>{badge}</Text> : <View style={{ width: 40 }} />)}
  </View>;
}

export function BottomTabs({ active, onNavigate, disabled = false }) {
  return <View style={styles.tabs}>
    {[['home', 'Home', 'home'], ['results', 'Results', 'list'], ['help', 'Help', 'help-circle'], ['profile', 'Profile', 'user']].map(([page, label, icon]) => (
      <Pressable key={page} accessibilityRole="tab" accessibilityState={{ selected: active === page, disabled }}
        accessibilityLabel={label} disabled={disabled} onPress={() => onNavigate(page)} style={styles.tab}>
        <Feather name={icon} size={20} color={active === page ? '#008B89' : '#63788A'} />
        <Text style={[styles.tabLabel, active === page && { color: '#008B89', fontWeight: '700' }]}>{label}</Text>
      </Pressable>
    ))}
  </View>;
}

export function PageBody({ children, ...props }) {
  return <ScrollView {...props} keyboardShouldPersistTaps="handled" contentContainerStyle={styles.body}>{children}</ScrollView>;
}

const styles = StyleSheet.create({
  header: { minHeight: 66, paddingHorizontal: 22, gap: 12, flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', backgroundColor: 'white', borderBottomColor: '#DCE5EB', borderBottomWidth: 1 },
  headerButton: { width: 42, height: 42, borderWidth: 1, borderColor: '#DCE5EB', borderRadius: 12, alignItems: 'center', justifyContent: 'center' },
  brand: { fontSize: 28, color: '#103A53', fontWeight: '900', letterSpacing: -1.6 },
  title: { color: colours.ink, fontSize: 20, fontWeight: '700', flex: 1, textAlign: 'center' },
  badge: { backgroundColor: '#E5F3FA', color: colours.blueDark, fontWeight: '700', paddingHorizontal: 12, paddingVertical: 7, borderRadius: 20, fontSize: 12 },
  tabs: { flexDirection: 'row', backgroundColor: 'white', borderTopColor: '#DCE5EB', borderTopWidth: 1, paddingVertical: 9 },
  tab: { flex: 1, alignItems: 'center', justifyContent: 'center', gap: 5, minHeight: 46 },
  tabLabel: { fontSize: 11, color: '#63788A' },
  body: { padding: 22, gap: 16, paddingBottom: 28 },
});
