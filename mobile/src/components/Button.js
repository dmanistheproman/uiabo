import { ActivityIndicator, Pressable, StyleSheet, Text } from 'react-native';

import { colours } from '../theme';

export default function Button({ children, disabled = false, loading = false, onPress, secondary = false }) {
  const unavailable = disabled || loading;
  return (
    <Pressable
      accessibilityRole="button"
      disabled={unavailable}
      onPress={onPress}
      style={({ pressed }) => [
        styles.button,
        secondary && styles.secondary,
        unavailable && styles.disabled,
        pressed && !unavailable && styles.pressed,
      ]}
    >
      {loading ? (
        <ActivityIndicator color={secondary ? colours.blue : colours.white} />
      ) : (
        <Text style={[styles.text, secondary && styles.secondaryText]}>{children}</Text>
      )}
    </Pressable>
  );
}

const styles = StyleSheet.create({
  button: {
    alignItems: 'center', backgroundColor: colours.blue, borderColor: colours.blue,
    borderRadius: 10, borderWidth: 2, justifyContent: 'center', marginBottom: 12,
    minHeight: 56, paddingHorizontal: 18,
  },
  disabled: { opacity: 0.55 },
  pressed: { backgroundColor: colours.blueDark },
  secondary: { backgroundColor: colours.white },
  secondaryText: { color: colours.blue },
  text: { color: colours.white, fontSize: 18, fontWeight: '700', textAlign: 'center' },
});
