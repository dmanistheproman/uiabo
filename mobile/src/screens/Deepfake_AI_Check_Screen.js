import React from 'react';
import {
  Alert,
  Image,
  StyleSheet,
  Text,
  View,
} from 'react-native';

import { chooseImageFor } from '../services/imagePicker';
import { confirmedImageFailure, imageInputError } from '../utils/inputFlows';

import { useAuth } from '../auth/AuthContext';
import { PageBody, PageHeader } from '../components/AppShell';
import Button from '../components/Button';

import { checkDeepfakeAI_Image } from '../services/api';
import { colours, typography } from '../theme';

export default function Deepfake_AI_Check_Screen({ onNavigate, onResult, setWorking, initialSelection = null }) {
  const { profile, firebaseUser, refreshProfile } = useAuth();

  const [selectedImage, setSelectedImage] = React.useState(null);
  const [analysing, setAnalysing] = React.useState(false);
  const [selecting, setSelecting] = React.useState(false);
  const sending = React.useRef(false);
  const busy = analysing || selecting;

  const requestKeyRef = React.useRef(null);

  const premium = profile?.role === 'premium';
  const remaining = profile?.allowance?.remaining_submissions;

  function acceptSelection(result) {
    if (!result || result.canceled) return;
    const image = result.assets?.[0];
    const problem = result.code ? 'Please select the image again.' : imageInputError(image);
    if (problem) { Alert.alert('Unable to use this image', problem); return; }
    requestKeyRef.current = null;
    setSelectedImage(image);
  }

  React.useEffect(() => { acceptSelection(initialSelection); }, [initialSelection]);

  async function chooseImage() {
    if (sending.current) return;
    sending.current = true; setSelecting(true); setWorking(true);
    try {
      const result = await chooseImageFor(firebaseUser.uid, 'deepfakeAI', {
        mediaTypes: ['images'],
        allowsMultipleSelection: false,
        allowsEditing: false,
        quality: 1,
      });

      acceptSelection(result);
    } catch (error) {
      console.error('Image picker error:', error);

      Alert.alert(
        'Unable to open your images',
        'Please try again.',
      );
    } finally {
      sending.current = false; setSelecting(false); setWorking(false);
    }
  }


  function removeImage() {
    if (sending.current) return;
    requestKeyRef.current = null;
    setSelectedImage(null);
  }

  async function analyseImage() {
  if (!selectedImage || !firebaseUser || sending.current || !premium) {
    return;
  }
  sending.current = true;
  setWorking(true);

  // Reuse the key if retrying a request that may have completed despite a connection error or timeout.
  if (!requestKeyRef.current) {
    requestKeyRef.current =
      `${Date.now()}-${Math.random().toString(36).slice(2)}`;
  }

  try {
    setAnalysing(true);

    const imageToUpload = {
      ...selectedImage,
      fileName: selectedImage.fileName || 'image',
    };

    const result = await checkDeepfakeAI_Image(
      firebaseUser,
      imageToUpload,
      requestKeyRef.current,
    );

    // The request completed successfully. A future, intentional check will receive a new key.
    requestKeyRef.current = null;

    try {
      await refreshProfile();
    } catch (refreshError) {
      console.warn('Could not refresh allowance:', refreshError);
    }

    onResult(result);

  } catch (error) {
    console.error('Deepfake_AI analysis error:', error);

    // A recorded model failure needs a new key for a fresh attempt.
    if (confirmedImageFailure(error.code)) {
      requestKeyRef.current = null;
    }
    await refreshProfile().catch(() => {});

    Alert.alert(
      'Analysis failed',
      error.message || 'Unable to analyse the image. Please try again.',
    );
  } finally {
    sending.current = false; setWorking(false);
    setAnalysing(false);
  }
}

  if (!premium) {
    return (
      <View style={{ flex: 1 }}>
        <PageHeader
          title="Deepfake/AI image check"
          onBack={() => onNavigate('home')}
        />

        <PageBody>
          <View style={styles.card}>
            <Text style={styles.title}>
              {profile ? 'Premium feature' : 'Load your account'}
            </Text>

            <Text style={styles.copy}>
              Deepfake and AI-generated image checking is available
              for Premium users.
            </Text>

            <Button onPress={() => profile ? onNavigate('premium') : refreshProfile().catch(error => Alert.alert('Account unavailable', error.message))}>
              {profile ? 'View Premium' : 'Refresh account'}
            </Button>

            <Button
              secondary
              onPress={() => onNavigate('home')}
            >
              Back to home
            </Button>
          </View>
        </PageBody>
      </View>
    );
  }

  return (
    <View style={{ flex: 1 }}>
      <PageHeader
        title="Deepfake/AI image check"
        onBack={() => !busy && onNavigate('home')}
        badge={remaining == null ? '— left' : `${remaining} left`}
      />

      <PageBody>
        <View>
          <Text style={styles.title}>
            Choose an image
          </Text>

          <Text style={styles.copy}>
            Select a PNG or JPEG image to preview.
          </Text>
        </View>

        {!selectedImage ? (
          <View style={styles.uploadCard}>
            <Text style={styles.imageIcon}>IMG</Text>

            <Text style={styles.uploadTitle}>
              No image selected
            </Text>

            <Text style={styles.copy}>
              PNG or JPEG, up to 10 MB and 25 megapixels.
            </Text>

            <Button disabled={busy} onPress={chooseImage}>
              Choose image
            </Button>
          </View>
        ) : (
          <>
            <View style={styles.previewCard}>
              <Image
                accessibilityLabel="Selected image preview"
                resizeMode="contain"
                source={{ uri: selectedImage.uri }}
                style={styles.preview}
              />

              <View style={styles.fileDetails}>
                <Text style={styles.label}>
                  Selected image
                </Text>

                <Text style={styles.fileName}>
                  {selectedImage.fileName || 'Image selected'}
                </Text>

                {!!selectedImage.mimeType && (
                  <Text style={styles.hint}>
                    {selectedImage.mimeType}
                  </Text>
                )}

                {!!selectedImage.width && !!selectedImage.height && (
                  <Text style={styles.hint}>
                    {selectedImage.width} × {selectedImage.height} pixels
                  </Text>
                )}
              </View>
            </View>

            <Button
              secondary
              disabled={busy}
              onPress={chooseImage}
            >
              Choose another image
            </Button>

            <Button
              secondary
              disabled={busy}
              onPress={removeImage}
            >
              Remove image
            </Button>
          </>
        )}

        <View style={styles.info}><Text style={styles.label}>How your image is checked</Text>
          <Text style={styles.copy}>The image is passed into a machine learning model trained specifically to detect AI images. The output score is then passed to Gemini API (Gemini 3.5 Flash Lite) to perform a secondary analysis and reasoning, to provide an explanation for the result. Completed results are saved privately in your history. When image saving is enabled, the uploaded image is also kept with the result; you can remove it from the result page. Do not submit images containing sensitive information.</Text>
          <Text style={styles.copy}>This checks for AI generated images or AI deepfakes. To fact-check an image's caption, try Check Image Context.</Text>
        </View>

        <Button
          disabled={!selectedImage || busy || remaining == null || remaining <= 0}
          onPress={analyseImage}
        >
          {analysing ? 'Analysing...' : 'Analyse image'}
        </Button>

        {remaining === 0 && <Text style={styles.copy}>You have used your allowance. You can still view saved results.</Text>}
        {remaining == null && <Button secondary disabled={busy} onPress={() => refreshProfile().catch(error => Alert.alert('Allowance unavailable', error.message))}>Refresh allowance</Button>}

        <Text style={styles.hintCentre}>
          {analysing
            ? 'Please wait while the image is analysed.'
            : 'Select an image to begin analysis.'}
        </Text>

      </PageBody>
    </View>
  );
}

const styles = StyleSheet.create({
  title: {
    ...typography.title,
    color: colours.ink,
    marginBottom: 8,
  },

  copy: {
    ...typography.body,
    color: colours.text,
  },

  label: {
    ...typography.label,
    color: colours.ink,
    marginBottom: 8,
  },

  uploadCard: {
    alignItems: 'center',
    backgroundColor: colours.white,
    borderColor: colours.border,
    borderRadius: 18,
    borderStyle: 'dashed',
    borderWidth: 2,
    gap: 12,
    padding: 24,
  },

  imageIcon: {
    ...typography.label,
    backgroundColor: colours.infoBackground,
    borderRadius: 12,
    color: colours.blueDark,
    overflow: 'hidden',
    paddingHorizontal: 16,
    paddingVertical: 14,
  },

  uploadTitle: {
    ...typography.heading,
    color: colours.ink,
  },

  previewCard: {
    backgroundColor: colours.white,
    borderColor: colours.divider,
    borderRadius: 18,
    borderWidth: 1,
    overflow: 'hidden',
  },

  preview: {
    backgroundColor: colours.infoBackground,
    height: 300,
    width: '100%',
  },

  fileDetails: {
    padding: 16,
  },

  fileName: {
    ...typography.secondary,
    color: colours.ink,
    fontWeight: '600',
    marginBottom: 5,
  },

  hint: {
    ...typography.secondary,
    color: colours.muted,
  },

  hintCentre: {
    ...typography.secondary,
    color: colours.muted,
    textAlign: 'center',
  },

  card: {
    backgroundColor: colours.white,
    borderColor: colours.divider,
    borderRadius: 18,
    borderWidth: 1,
    gap: 16,
    padding: 20,
  },

  info: { backgroundColor: colours.infoBackground, borderLeftWidth: 3, borderLeftColor: colours.blue, padding: 18, borderRadius: 14, gap: 12 },
});
