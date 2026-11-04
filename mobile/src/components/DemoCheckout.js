import { useEffect, useRef, useState } from 'react';
import { StyleSheet, Text, View } from 'react-native';
import Button from './Button';
import { useAuth } from '../auth/AuthContext';
import { getDemoPaymentOffer } from '../services/api';
import { colours, typography } from '../theme';

export default function DemoCheckout({ onWorking }) {
  const { firebaseUser, profile, upgradeWithDemoPayment } = useAuth();
  const [offer, setOffer] = useState(null);
  const [review, setReview] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [receipt, setReceipt] = useState(null);
  const submitting = useRef(false);
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    let active = true;
    setError('');
    getDemoPaymentOffer(firebaseUser).then(value => { if (active) setOffer(value); })
      .catch(() => { if (active) setError('Could not load demo checkout. Please retry.'); });
    return () => { active = false; };
  }, [firebaseUser, attempt]);

  async function pay() {
    if (submitting.current) return;
    submitting.current = true; setBusy(true); setError(''); onWorking?.(true);
    try { setReceipt(await upgradeWithDemoPayment()); setReview(false); }
    catch (caught) { setError(caught.message); }
    finally { submitting.current = false; setBusy(false); onWorking?.(false); }
  }

  if (receipt) return <View style={styles.box} accessibilityLiveRegion="polite">
    <Text style={styles.title}>Demo payment complete</Text>
    <Text style={styles.copy}>Premium is active. Amount charged: S$0.00.</Text>
    <Text style={styles.hint}>Your monthly allowance is shown on Home. Repeating checkout does not reset it.</Text>
    {receipt.receipt_id && <Text selectable style={styles.hint}>Demo receipt: {receipt.receipt_id}</Text>}
  </View>;
  if (profile?.role === 'premium') return null;
  return <View style={styles.box}>
    <Text style={styles.title}>{review ? 'Review demo payment' : 'Try Premium with demo checkout'}</Text>
    <Text style={styles.copy}>DEMO ONLY — no real payment. Do not enter bank or card details.</Text>
    {error ? <Text accessibilityRole="alert" style={styles.error}>{error}</Text> : null}
    {!offer ? <Button secondary onPress={() => setAttempt(value => value + 1)}>Reload checkout</Button>
      : !offer.enabled ? <Text style={styles.copy}>Demo checkout is not enabled on this server.</Text>
      : review ? <>
        <Text style={styles.copy}>Premium demo price: S${(offer.display_price_cents / 100).toFixed(2)} per month.</Text>
        <Text style={styles.copy}>Actual charge today: S$0.00.</Text>
        <Text style={styles.copy}>Payment method: Demo payment (simulated approval).</Text>
        <Text style={styles.hint}>Get 60 completed checks per calendar month and image features. This prototype upgrade stays active until the project team changes it. There are no recurring charges.</Text>
        <Button loading={busy} onPress={pay}>Complete demo payment</Button>
        <Button secondary disabled={busy} onPress={() => { setReview(false); setError(''); }}>Cancel</Button>
      </> : <Button onPress={() => { setReview(true); setError(''); }}>Continue to demo checkout</Button>}
  </View>;
}

const styles = StyleSheet.create({
  box: { borderWidth: 1, borderColor: colours.divider, borderRadius: 14, padding: 16, gap: 18, backgroundColor: colours.infoBackground },
  title: { ...typography.heading, color: colours.ink },
  copy: { ...typography.body, color: colours.text },
  hint: { ...typography.secondary, color: colours.muted },
  error: { ...typography.secondary, color: colours.danger },
});
