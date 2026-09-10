import { StyleSheet, Text, View } from 'react-native';
import { PageBody, PageHeader } from '../components/AppShell';
import Button from '../components/Button';
import { useAuth } from '../auth/AuthContext';

export default function InfoScreen({ premium, onNavigate }) {
  const { profile } = useAuth();
  const activePremium = profile?.role === 'premium';
  return <View style={{ flex: 1 }}><PageHeader title={premium ? 'Premium' : 'Help'} onBack={() => onNavigate('home')} /><PageBody>
    <View style={styles.card}><Text style={styles.heading}>{premium ? activePremium ? 'Your Premium account is active' : 'More ways to check images' : 'Make your next share an informed one'}</Text>
      <Text style={styles.copy}>{premium ? activePremium ? 'You receive up to 60 successful text checks each calendar month. Your allowance resets at midnight Singapore time on the first day of the month.' : 'The planned Premium tier includes image + caption, image context, OCR and AI-image checks, with up to 60 successful checks per month for SGD 20/month.' : 'Paste a short English claim into Check text. UIABO looks for a checkable statement, searches published evidence, and shows a concern label with citations.'}</Text>
      <Text style={styles.copy}>{premium ? 'Image checks and subscription payments are not available in this prototype yet. No payment will be taken.' : 'A concern score is an automated indicator, not proof. Read the source passages and check the uncertainty before sharing.'}</Text>
      {!premium && <><Text style={styles.heading}>Your allowance and results</Text><Text style={styles.copy}>Free accounts receive one successful check per day, resetting at midnight Singapore time. Failed checks do not use your allowance. Completed checks, including Not Enough Information results, are saved to your account.</Text><Text style={styles.copy}>If a request times out, open Results before retrying. A check may have completed while your connection was interrupted.</Text></>}
      {!premium && <><Text style={styles.heading}>Understanding policy checks</Text><Text style={styles.copy}>“Not supported by policy checked” means related official information was found, but it does not establish the message. Read the comparisons for amounts, dates and affected people. “Contradicted by evidence” requires an incompatible fact that applies to the claim. An unsuccessful search alone does not prove a claim false.</Text></>}
      <Button onPress={() => onNavigate('text')}>Check some text</Button>
    </View>
  </PageBody></View>;
}
const styles = StyleSheet.create({ card: { backgroundColor: 'white', borderRadius: 18, padding: 20, gap: 20 }, heading: { color: '#173447', fontSize: 22, fontWeight: '800' }, copy: { color: '#526F83', fontSize: 15, lineHeight: 23 } });
