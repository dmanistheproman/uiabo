import { StyleSheet, Text, View } from 'react-native';

import Screen from '../components/Screen';
import { API_URL } from '../services/api';
import { colours } from '../theme';

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
  body: { color: colours.ink, fontSize: 18, lineHeight: 27, marginBottom: 22 },
  card: { backgroundColor: colours.white, borderRadius: 16, padding: 22 },
  code: { backgroundColor: colours.locked, color: colours.ink, fontSize: 16, padding: 14 },
  label: { color: colours.ink, fontSize: 17, fontWeight: '700', marginBottom: 8 },
  title: { color: colours.danger, fontSize: 28, fontWeight: '700', marginBottom: 15 },
});
