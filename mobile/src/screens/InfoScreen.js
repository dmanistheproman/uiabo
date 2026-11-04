import { StyleSheet, Text, View } from 'react-native';
import { PageBody, PageHeader } from '../components/AppShell';
import Button from '../components/Button';
import { useAuth } from '../auth/AuthContext';
import DemoCheckout from '../components/DemoCheckout';
import { colours, typography } from '../theme';

export default function InfoScreen({ premium, onNavigate, onWorking }) {
  const { profile } = useAuth();
  const activePremium = profile?.role === 'premium';
  return <View style={{ flex: 1 }}><PageHeader title={premium ? 'Premium' : 'Help'} onBack={() => onNavigate('home')} /><PageBody>
    <View style={styles.card}>
      <Text style={styles.heading}>{premium ? activePremium ? 'Your Premium account is active' : 'More ways to check images' : 'Make your next share an informed one'}</Text>
      {premium ? <>
        <Text style={styles.copy}>Premium includes Read image text, Check image context with an optional caption, and Deepfake / AI image check. Premium accounts receive up to 60 completed checks per calendar month, shared across text, link and image checks.</Text>
        <Text style={styles.copy}>The allowance resets at midnight Singapore time on the first day of the month. Image text extraction does not use a check; a completed analysis does.</Text>
        <Text style={styles.copy}>Real subscription payments are not available. Demo checkout uses no real money or card details.</Text>
        <DemoCheckout onWorking={onWorking} />
      </> : <>
        <Text style={styles.copy}>Paste a short English claim into Check text. UIABO looks for a checkable statement, searches published evidence and explains its findings with sources.</Text>
        <Text style={styles.heading}>Understanding your result</Text>
        <Text style={styles.copy}>Read the result label first, then open Why this result for the explanation and any credibility details. When a score is available, higher means more supporting evidence and lower means more contradicting evidence. It is not a percentage chance that the claim is true.</Text>
        <Text style={styles.copy}>Not enough evidence is not a score of 50. Mixed evidence means there is relevant evidence on both sides. Likely misinformation can reflect an explained inference from relevant evidence; an unsuccessful search alone does not prove a claim false.</Text>
        <Text style={styles.heading}>Your allowance and results</Text>
        <Text style={styles.copy}>Free accounts receive one completed check per day. Premium accounts receive up to 60 per calendar month. Both reset at midnight Singapore time. Failed checks do not use allowance. Completed checks, including Not enough evidence results, are saved to your account.</Text>
        <Text style={styles.copy}>If a request times out, open Results before retrying. A check may have completed while your connection was interrupted.</Text>
        <Text style={styles.copy}>To check a claim from an article, copy the relevant text and paste it into Check text. Keep important dates and context.</Text>
        <Text style={styles.heading}>Check link safety</Text>
        <Text style={styles.copy}>This separate check screens public URLs against Google's known phishing, malware and unwanted software lists. No known threats found does not guarantee safety. The full URL is sent to Google Web Risk and saved in your history. Avoid private links or links containing passwords or access tokens.</Text>
        <Text style={styles.heading}>Read image text</Text>
        <Text style={styles.copy}>Premium accounts can extract words from a screenshot or photo, correct them and fact-check the message. Check names, amounts and dates carefully. The OCR image is not saved; the reviewed text is saved when you submit a check. OCR does not detect whether an image is AI-generated.</Text>
        <Text style={styles.heading}>Image context and captions</Text>
        <Text style={styles.copy}>Choose an image and add its caption, or leave the caption blank to read it from a screenshot. We compare the image and message with web evidence. This does not prove the image's original date or location.</Text>
        <Text style={styles.heading}>Deepfake / AI image check</Text>
        <Text style={styles.copy}>Look for signs of AI-generated or manipulated imagery. The result is an assessment, not proof of authenticity. When image saving is enabled, image-context and deepfake images are saved privately with the result. You can remove a saved image from its result page.</Text>
        <Text style={styles.heading}>Delete your account</Text>
        <Text style={styles.copy}>Open Profile, then Delete my account. Enter your current password and confirm. Once accepted, you are signed out while your account and saved data are removed. Cleanup may take several minutes.</Text>
      </>}
      <Button onPress={() => onNavigate('text')}>Check some text</Button>
    </View>
  </PageBody></View>;
}
const styles = StyleSheet.create({
  card: { backgroundColor: colours.white, borderRadius: 18, padding: 20, gap: 24 },
  heading: { ...typography.heading, color: colours.ink },
  copy: { ...typography.body, color: colours.text },
});
