export const colours = {
  background: '#F6F7F4',
  blue: '#145DA0',
  blueDark: '#0B3C68',
  border: '#758895',
  divider: '#D6DFE3',
  danger: '#9B2727',
  ink: '#172B3A',
  locked: '#E3E7EB',
  muted: '#465D6B',
  text: '#243E50',
  teal: '#006A68',
  success: '#17613B',
  warning: '#7A4D00',
  infoBackground: '#EAF2F8',
  warningBackground: '#FFF4D6',
  successBackground: '#EAF5EE',
  dangerBackground: '#FCEDEA',
  white: '#FFFFFF',
};

// Native system sans-serif (Roboto on Android / system font on iOS).
// Keep React Native's font scaling enabled; containers must grow with the text.
export const typography = {
  body: { fontSize: 20, lineHeight: 30 },
  secondary: { fontSize: 18, lineHeight: 27 },
  small: { fontSize: 16, lineHeight: 24 },
  label: { fontSize: 20, lineHeight: 28, fontWeight: '600' },
  title: { fontSize: 28, lineHeight: 36, fontWeight: '700' },
  heading: { fontSize: 22, lineHeight: 30, fontWeight: '700' },
  button: { fontSize: 20, lineHeight: 28, fontWeight: '700' },
  tab: { fontSize: 16, lineHeight: 22, fontWeight: '600' },
};

export const sharedStyles = {
  field: {
    backgroundColor: colours.white,
    borderColor: colours.border,
    borderRadius: 10,
    borderWidth: 2,
    color: colours.ink,
    ...typography.body,
    marginBottom: 16,
    minHeight: 56,
    paddingHorizontal: 16,
    paddingVertical: 12,
  },
  label: {
    color: colours.ink,
    ...typography.label,
    marginBottom: 10,
  },
};
