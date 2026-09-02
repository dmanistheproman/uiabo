import { StatusBar } from 'expo-status-bar';
import React from 'react';
import { ActivityIndicator, SafeAreaView, StyleSheet, Text, View } from 'react-native';

import { AuthProvider, useAuth } from './src/auth/AuthContext';
import AuthScreen from './src/screens/AuthScreen';
import HomeScreen from './src/screens/HomeScreen';
import ProfileScreen from './src/screens/ProfileScreen';
import SetupScreen from './src/screens/SetupScreen';
import VerifyEmailScreen from './src/screens/VerifyEmailScreen';
import { colours } from './src/theme';

function AppContent() {
  const { configurationError, firebaseUser, initialising } = useAuth();
  const [page, setPage] = React.useState('home');

  React.useEffect(() => {
    setPage('home');
  }, [firebaseUser?.uid]);

  if (initialising) {
    return (
      <View style={styles.centre}>
        <ActivityIndicator color={colours.blue} size="large" />
        <Text style={styles.loadingText}>Opening UIABO…</Text>
      </View>
    );
  }

  if (configurationError) return <SetupScreen message={configurationError} />;
  if (!firebaseUser) return <AuthScreen />;
  if (!firebaseUser.emailVerified) return <VerifyEmailScreen />;
  if (page === 'profile') return <ProfileScreen onBack={() => setPage('home')} />;
  return <HomeScreen onOpenProfile={() => setPage('profile')} />;
}

export default function App() {
  return (
    <SafeAreaView style={styles.safeArea}>
      <StatusBar style="dark" />
      <AuthProvider>
        <AppContent />
      </AuthProvider>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safeArea: {
    flex: 1,
    backgroundColor: colours.background,
  },
  centre: {
    alignItems: 'center',
    backgroundColor: colours.background,
    flex: 1,
    justifyContent: 'center',
  },
  loadingText: {
    color: colours.ink,
    fontSize: 18,
    marginTop: 16,
  },
});
