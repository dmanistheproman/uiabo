import { StyleSheet, Text, View } from 'react-native';
import { PageBody, PageHeader } from '../components/AppShell';
import Button from '../components/Button';
import { useAuth } from '../auth/AuthContext';
import DemoCheckout from '../components/DemoCheckout';
import FeatureExplanation from '../components/FeatureExplanation';
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
        <FeatureExplanation title="Check text">
          <Text style={styles.copy}>Paste a short English claim to check it against published evidence and see sources. For articles, copy the relevant text with its dates and context.</Text>
        </FeatureExplanation>
        <FeatureExplanation title="Check link safety">
          <Text style={styles.copy}>Checks public links for known phishing, malware and unwanted software. No known threats found does not guarantee safety.</Text>
          <Text style={styles.copy}>Your link is checked online and saved privately in history. Avoid private links, passwords or access codes.</Text>
        </FeatureExplanation>
        <FeatureExplanation title="Read image text">
          <Text style={styles.copy}>With Premium, extract text from a photo or screenshot, review it, then check the message. Verify names, amounts and dates.</Text>
          <Text style={styles.copy}>The image is not saved; submitted text is. This feature does not detect AI-generated images.</Text>
        </FeatureExplanation>
        <FeatureExplanation title="Image context and captions">
          <Text style={styles.copy}>Compare an image and caption with web evidence. Leave the caption blank to read it from a screenshot. Results cannot prove the original date or location.</Text>
        </FeatureExplanation>
        <FeatureExplanation title="Deepfake / AI image check">
          <Text style={styles.copy}>Checks for signs of AI generation or manipulation. Results are assessments, not proof of authenticity.</Text>
          <Text style={styles.copy}>When image saving is enabled, context and deepfake images are saved privately with results. Remove a saved image from its result page.</Text>
        </FeatureExplanation>
        <FeatureExplanation title="Understanding your result">
          <Text style={styles.copy}>Read the result label, then open Why this result. If a score is shown, higher means more supporting evidence and lower means more contradicting evidence. It is not the percentage chance a claim is true.</Text>
          <Text style={styles.copy}>Not enough evidence is not a score of 50. Mixed evidence means relevant evidence on both sides. Likely misinformation may reflect an explained inference from relevant evidence; an unsuccessful search alone cannot prove a claim false.</Text>
        </FeatureExplanation>
        <FeatureExplanation title="Your allowance and results">
          <Text style={styles.copy}>Free accounts get one completed check daily; Premium gets up to 60 per calendar month. Resets happen at midnight Singapore time. Failed checks use no allowance. Completed checks, including Not enough evidence, are saved to your account.</Text>
          <Text style={styles.copy}>After a timeout, open Results before retrying: your check may have completed.</Text>
        </FeatureExplanation>
        <FeatureExplanation title="Delete your account">
          <Text style={styles.copy}>Open Profile, then Delete my account. Enter your current password and confirm. You are signed out once accepted. Removing your account and saved data may take several minutes.</Text>
        </FeatureExplanation>
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
