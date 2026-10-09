import { StatusBar } from 'expo-status-bar';
import React from 'react';
import * as ImagePicker from 'expo-image-picker';
import LinkCheckScreen from './src/screens/LinkCheckScreen';
import LinkResultScreen from './src/screens/LinkResultScreen';
import OcrScreen from './src/screens/OcrScreen';
import { ActivityIndicator, Alert, BackHandler, StyleSheet, Text, View } from 'react-native';
import { SafeAreaProvider, SafeAreaView } from 'react-native-safe-area-context';

import { AuthProvider, useAuth } from './src/auth/AuthContext';
import AuthScreen from './src/screens/AuthScreen';
import HomeScreen from './src/screens/HomeScreen';
import ProfileScreen from './src/screens/ProfileScreen';
import SetupScreen from './src/screens/SetupScreen';
import VerifyEmailScreen from './src/screens/VerifyEmailScreen';
import TextCheckScreen from './src/screens/TextCheckScreen';
import ResultsScreen from './src/screens/ResultsScreen';
import ResultScreen from './src/screens/ResultScreen';
import InfoScreen from './src/screens/InfoScreen';
import { BottomTabs } from './src/components/AppShell';
import { colours } from './src/theme';

function AppContent() {
  const { configurationError, firebaseUser, initialising } = useAuth();
  const [page, setPage] = React.useState('home');
  const [result, setResult] = React.useState(null);
  const [working, setWorking] = React.useState(false);
  const [textDraft, setTextDraft] = React.useState(null);
  const [ocrSelection, setOcrSelection] = React.useState(null);

  React.useEffect(() => {
    setPage('home');
    setResult(null);
    setWorking(false);
    setTextDraft(null);
    setOcrSelection(null);
  }, [firebaseUser?.uid]);

  React.useEffect(() => {
    if (!firebaseUser?.emailVerified) return;
    let active = true;
    // Android may recreate the activity while its system photo picker is open.
    ImagePicker.getPendingResultAsync().then(selection => {
      if (active && selection && !selection.canceled) {
        setOcrSelection(selection); setPage('ocr');
      }
    }).catch(() => {});
    return () => { active = false; };
  }, [firebaseUser?.uid, firebaseUser?.emailVerified]);

  function navigate(next, options = {}) {
    if (working) return;
    setTextDraft(next === 'text' ? options.draft || null : null);
    if (next !== 'ocr') setOcrSelection(null);
    setPage(next);
  }
  React.useEffect(() => {
    const subscription = BackHandler.addEventListener('hardwareBackPress', () => {
      if (working) { Alert.alert('Check in progress', 'Please keep this screen open while your check finishes.'); return true; }
      if (page !== 'home') { setPage(page === 'result' ? 'results' : 'home'); return true; }
      return false;
    });
    return () => subscription.remove();
  }, [page, working]);

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
  function showResult(value) { setResult(value); setPage('result'); }
  let content;
  if (page === 'profile') content = <ProfileScreen onBack={() => navigate('home')} />;
  else if (page === 'text') content = <TextCheckScreen initialDraft={textDraft} onNavigate={navigate} onResult={showResult} setWorking={setWorking} />;
  else if (page === 'link') content = <LinkCheckScreen onNavigate={navigate} onResult={showResult} setWorking={setWorking} />;
  else if (page === 'ocr') content = <OcrScreen initialSelection={ocrSelection} onNavigate={navigate} onResult={showResult} setWorking={setWorking} />;
  else if (page === 'results') content = <ResultsScreen onNavigate={navigate} onResult={showResult} />;
  else if (page === 'result' && result) content = result.input_type === 'link_safety' ? <LinkResultScreen result={result} onNavigate={navigate} /> : <ResultScreen result={result} onNavigate={navigate} />;
  else if (page === 'help' || page === 'premium') content = <InfoScreen premium={page === 'premium'} onNavigate={navigate} />;
  else content = <HomeScreen onNavigate={navigate} />;
  return <View style={{ flex: 1 }}>{content}<BottomTabs active={page === 'result' ? 'results' : ['text', 'link', 'ocr', 'premium'].includes(page) ? 'home' : page} onNavigate={navigate} disabled={working} /></View>;
}

export default function App() {
  return (
    <SafeAreaProvider><SafeAreaView style={styles.safeArea}>
      <StatusBar style="dark" />
      <AuthProvider>
        <AppContent />
      </AuthProvider>
    </SafeAreaView></SafeAreaProvider>
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
