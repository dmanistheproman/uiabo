import { colours, typography } from '../theme';
import { useState } from 'react';
import { Alert, Pressable, StyleSheet, Text, TextInput, View } from 'react-native';
import Feather from '@expo/vector-icons/Feather';
import Button from './Button';
import { useAuth } from '../auth/AuthContext';
import { reportResult } from '../services/api';
import { canReport, reportOptions } from '../utils/resultReporting';

export default function ReportResultPanel({ result }) {
  // Remount the form when a different saved result is opened.
  return canReport(result) ? <ReportForm key={result.result_id} result={result} /> : null;
}

function ReportForm({ result }) {
  const { firebaseUser } = useAuth();
  const [open, setOpen] = useState(false);
  const [reason, setReason] = useState(null);
  const [detail, setDetail] = useState('');
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState(false);
  async function submit() {
    if (busy) return;
    if (!reason || !detail.trim()) {
      Alert.alert('Add a little more', 'Choose a reason and describe what looks wrong.'); return;
    }
    setBusy(true);
    try {
      await reportResult(firebaseUser, result.result_id, reason, detail.trim()); setDone(true);
    } catch (error) {
      if (error.code === 'ALREADY_REPORTED') setDone(true);
      else Alert.alert('Could not send report', error.message);
    } finally { setBusy(false); }
  }
  return <View style={styles.card}>
    <Pressable accessibilityRole="button" accessibilityState={{ expanded: open }} onPress={() => setOpen(!open)} style={styles.toggle}>
      <Text style={styles.heading}>Report a problem with this result</Text>
      <Feather name={open ? 'chevron-up' : 'chevron-down'} size={24} color={colours.ink} />
    </Pressable>
    {open && (done ? <Text style={styles.copy}>Your report is with our team for review. Thank you.</Text> : <>
      <Text style={styles.copy}>What looks wrong?</Text>
      <Text style={styles.hint}>Our review team can see this result and its saved image, if available. Reporting does not use a check.</Text>
      {reportOptions(result).map(option => <Pressable key={option.value} disabled={busy} accessibilityRole="radio"
        accessibilityState={{ checked: reason === option.value, disabled: busy }}
        onPress={() => setReason(option.value)} style={[styles.option, reason === option.value && styles.selected]}>
        <Feather name={reason === option.value ? 'check-circle' : 'circle'} size={22} color={colours.blueDark} />
        <Text style={styles.optionText}>{option.label}</Text>
      </Pressable>)}
      <TextInput accessibilityLabel="Describe what is wrong" multiline textAlignVertical="top" editable={!busy}
        maxLength={2000} placeholder="Tell us what looks wrong…" placeholderTextColor={colours.muted}
        style={styles.input} value={detail} onChangeText={setDetail} />
      <Button secondary loading={busy} onPress={submit}>Send report</Button>
    </>)}
  </View>;
}

const styles = StyleSheet.create({
  card: { backgroundColor: colours.white, borderRadius: 16, borderWidth: 1, borderColor: colours.divider, padding: 18, gap: 16 },
  toggle: { minHeight: 56, flexDirection: 'row', alignItems: 'center', gap: 12 },
  heading: { ...typography.heading, color: colours.ink, flex: 1, flexShrink: 1 },
  copy: { ...typography.body, color: colours.text },
  hint: { ...typography.secondary, color: colours.muted },
  option: { minHeight: 56, flexDirection: 'row', alignItems: 'center', gap: 12, padding: 14, borderWidth: 2, borderColor: colours.border, borderRadius: 12 },
  selected: { borderColor: colours.blue, backgroundColor: colours.infoBackground },
  optionText: { ...typography.body, color: colours.text, flex: 1, flexShrink: 1 },
  input: { ...typography.body, minHeight: 150, borderWidth: 2, borderColor: colours.border, borderRadius: 14, padding: 16, color: colours.ink, backgroundColor: colours.white },
});
