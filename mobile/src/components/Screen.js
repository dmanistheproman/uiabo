import { KeyboardAvoidingView, Platform, ScrollView, StyleSheet } from 'react-native';

import { colours } from '../theme';

export default function Screen({ children }) {
  return (
    <KeyboardAvoidingView behavior={Platform.OS === 'ios' ? 'padding' : undefined} style={styles.container}>
      <ScrollView contentContainerStyle={styles.content} keyboardShouldPersistTaps="handled">
        {children}
      </ScrollView>
    </KeyboardAvoidingView>
  );
}

const styles = StyleSheet.create({
  container: { backgroundColor: colours.background, flex: 1 },
  content: { flexGrow: 1, justifyContent: 'center', padding: 24 },
});
