import { StatusBar } from 'expo-status-bar';
import React from 'react';
import LinkCheckScreen from './src/screens/LinkCheckScreen';
import LinkResultScreen from './src/screens/LinkResultScreen';
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
import Deepfake_AI_Check_Screen from './src/screens/Deepfake_AI_Check_Screen';
import Deepfake_AI_Result_Screen from './src/screens/Deepfake_AI_Result_Screen';
import Image_Context_Analysis_Screen from './src/screens/Image_Context_Analysis_Screen';
import Image_Context_Result_Screen from './src/screens/Image_Context_Result_Screen';
import { BottomTabs } from './src/components/AppShell';
import { colours } from './src/theme';

function AppContent() {
  const { configurationError, firebaseUser, initialising } = useAuth();
  const [page, setPage] = React.useState('home');
  const [result, setResult] = React.useState(null);
  const [deepfakeAI_Result, setDeepfakeAI_Result] = React.useState(null);
  const [deepfakeAI_ResultOrigin, setDeepfakeAI_ResultOrigin] = React.useState('home');
  const [imageContext_Result, setImageContext_Result] = React.useState(null);
  const [imageContext_ResultOrigin, setImageContext_ResultOrigin] = React.useState('home');
  const [working, setWorking] = React.useState(false);
  const [textDraft, setTextDraft] = React.useState(null);

  React.useEffect(() => {
    setPage('home');
    setResult(null);
    setDeepfakeAI_Result(null);
    setImageContext_Result(null);
    setWorking(false);
    setTextDraft(null);
  }, [firebaseUser?.uid]);

  function navigate(next, options = {}) {
    if (working) return;
    setTextDraft(next === 'text' ? options.draft || null : null);
    
    setPage(next);
  }
  React.useEffect(() => {
    const subscription = BackHandler.addEventListener('hardwareBackPress', () => {
      if (working) { Alert.alert('Check in progress', 'Please keep this screen open while your check finishes.'); return true; }
      if (page !== 'home') {
        if (page === 'result') {
          setPage('results');
        } else if (page === 'deepfakeAI-result') {
          setPage(deepfakeAI_ResultOrigin);
        } else if (page === 'imageContext-result') {
          setPage(imageContext_ResultOrigin);
        } else {
          setPage('home');
        }

        return true;
      }
      
      return false;
    });
    return () => subscription.remove();
  }, [page, working, deepfakeAI_ResultOrigin, imageContext_ResultOrigin]);

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

  function showResult(value) {
    if (value.input_type === 'deepfake_ai') {
      setDeepfakeAI_Result(value);
      setDeepfakeAI_ResultOrigin('results');
      setPage('deepfakeAI-result');
      return;
    }

    if (value.input_type === 'image_context') {
      setImageContext_Result(value);
      setImageContext_ResultOrigin('results');
      setPage('imageContext-result');
      return;
    }

    setResult(value);
    setPage('result');
  }

  function showDeepfakeAI_Result(value) {
    setDeepfakeAI_Result(value);
    setDeepfakeAI_ResultOrigin('home');
    setPage('deepfakeAI-result');
  }

  function showImageContext_Result(value) {
    setImageContext_Result(value);
    setImageContext_ResultOrigin('home');
    setPage('imageContext-result');
  }

  let content;
  if (page === 'profile') content = <ProfileScreen onBack={() => navigate('home')} />;
  else if (page === 'text') content = <TextCheckScreen initialDraft={textDraft} onNavigate={navigate} onResult={showResult} setWorking={setWorking} />;
  else if (page === 'link') content = <LinkCheckScreen onNavigate={navigate} onResult={showResult} setWorking={setWorking} />;
  else if (page === 'deepfakeAI') content = <Deepfake_AI_Check_Screen onNavigate={navigate} onResult={showDeepfakeAI_Result} />;
  else if (page === 'deepfakeAI-result' && deepfakeAI_Result) content = ( <Deepfake_AI_Result_Screen result={deepfakeAI_Result} onNavigate={navigate} onBack={() => navigate(deepfakeAI_ResultOrigin)} />);
  else if (page === 'imageContext') content = ( <Image_Context_Analysis_Screen onNavigate={navigate} onResult={showImageContext_Result} setWorking={setWorking} />);
  else if (page === 'imageContext-result' && imageContext_Result) content = ( <Image_Context_Result_Screen result={imageContext_Result} onNavigate={navigate} onBack={() => navigate(imageContext_ResultOrigin)} />);
  else if (page === 'results') content = <ResultsScreen onNavigate={navigate} onResult={showResult} />;
  else if (page === 'result' && result) content = result.input_type === 'link_safety' ? <LinkResultScreen result={result} onNavigate={navigate} /> : <ResultScreen result={result} onNavigate={navigate} />;
  else if (page === 'help' || page === 'premium') content = <InfoScreen premium={page === 'premium'} onNavigate={navigate} />;
  else content = <HomeScreen onNavigate={navigate} />;
  return <View style={{ flex: 1 }}>{content}<BottomTabs active={page === 'result' ? 'results' : ['text', 'link', 'deepfakeAI', 'deepfakeAI-result', 'imageContext', 'imageContext-result', 'premium'].includes(page) ? 'home' : page} onNavigate={navigate} disabled={working} /></View>;
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
