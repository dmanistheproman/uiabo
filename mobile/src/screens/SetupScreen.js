import { StyleSheet, Text, View } from 'react-native';

import Screen from '../components/Screen';
import { API_URL } from '../services/api';
import { colours, typography } from '../theme';

export default function SetupScreen({ message }) {
  return (
    <Screen>
      <View style={styles.card}>
        <Text style={styles.title}>Finish app setup</Text>
        <Text style={styles.body}>{message}</Text>
        <Text style={styles.label}>Current backend address</Text>
        <Text selectable style={styles.code}>{API_URL}</Text>
      </View>
    </Screen>
  );
}

const styles = StyleSheet.create({
  body: { ...typography.body, color: colours.text, marginBottom: 24 },
  card: { backgroundColor: colours.white, borderRadius: 16, padding: 22 },
  code: { ...typography.secondary, backgroundColor: colours.locked, color: colours.ink, padding: 16 },
  label: { ...typography.label, color: colours.ink, marginBottom: 8 },
  title: { ...typography.title, color: colours.danger, marginBottom: 16 },
});
