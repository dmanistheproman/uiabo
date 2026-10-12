import React from 'react';
import {
  Alert,
  Image,
  StyleSheet,
  Text,
  View,
} from 'react-native';

import * as ImagePicker from 'expo-image-picker';

import { useAuth } from '../auth/AuthContext';
import { PageBody, PageHeader } from '../components/AppShell';
import Button from '../components/Button';

import { checkDeepfakeAI_Image } from '../services/api';

function isSupportedImage(asset) {
  const mimeType = (asset?.mimeType || '').toLowerCase();
  const fileName = (asset?.fileName || '').toLowerCase();
  const uri = (asset?.uri || '').toLowerCase().split('?')[0];

  if (mimeType) {
    return [
      'image/png',
      'image/jpeg',
      'image/jpg',
    ].includes(mimeType);
  }

  return /\.(png|jpg|jpeg)$/i.test(fileName)
    || /\.(png|jpg|jpeg)$/i.test(uri);
}


export default function Deepfake_AI_Check_Screen({ onNavigate, onResult }) {
  const { profile, firebaseUser, refreshProfile } = useAuth();

  const [selectedImage, setSelectedImage] = React.useState(null);
  const [analysing, setAnalysing] = React.useState(false);

  const requestKeyRef = React.useRef(null);

  const premium = profile?.role === 'premium';
  const remaining = profile?.allowance?.remaining_submissions;

  async function chooseImage() {
    try {
      const result = await ImagePicker.launchImageLibraryAsync({
        mediaTypes: ['images'],
        allowsEditing: false,
        quality: 1,
      });

      if (result.canceled) {
        return;
      }

      const image = result.assets?.[0];

      if (!image) {
        Alert.alert(
          'Unable to select image',
          'Please try selecting the image again.',
        );
        return;
      }

      if (!isSupportedImage(image)) {
        Alert.alert(
          'Unsupported image',
          'Please select a PNG, JPG or JPEG image.',
        );
        return;
      }
      
      requestKeyRef.current = null;
      setSelectedImage(image);
    } catch (error) {
      console.error('Image picker error:', error);

      Alert.alert(
        'Unable to open your images',
        'Please try again.',
      );
    }
  }


  function removeImage() {
    requestKeyRef.current = null;
    setSelectedImage(null);
  }

  async function analyseImage() {
  if (!selectedImage || !firebaseUser || analysing) {
    return;
  }

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
    if (
      error.code === 'IMAGE_ANALYSIS_FAILED' ||
      error.code === 'PREVIOUS_ANALYSIS_FAILED'
    ) {
      requestKeyRef.current = null;
    }

    Alert.alert(
      'Analysis failed',
      error.message || 'Unable to analyse the image. Please try again.',
    );
  } finally {
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
              Premium feature
            </Text>

            <Text style={styles.copy}>
              Deepfake and AI-generated image checking is available
              for Premium users.
            </Text>

            <Button onPress={() => onNavigate('premium')}>
              View Premium
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
        onBack={() => onNavigate('home')}
        badge={remaining == null ? '— left' : `${remaining} left`}
      />

      <PageBody>
        <View>
          <Text style={styles.eyebrow}>
            IMAGE ANALYSIS
          </Text>

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
              Supported formats: PNG, JPG and JPEG.
            </Text>

            <Button onPress={chooseImage}>
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
              onPress={chooseImage}
            >
              Choose another image
            </Button>

            <Button
              secondary
              onPress={removeImage}
            >
              Remove image
            </Button>
          </>
        )}

        <Button
          disabled={!selectedImage || analysing}
          onPress={analyseImage}
        >
          {analysing ? 'Analysing...' : 'Analyse image'}
        </Button>
        
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
  eyebrow: {
    color: '#7952AE',
    fontSize: 12,
    fontWeight: '800',
    letterSpacing: 1,
    marginBottom: 8,
  },

  title: {
    color: '#173447',
    fontSize: 25,
    fontWeight: '800',
    marginBottom: 5,
  },

  copy: {
    color: '#526F83',
    fontSize: 14,
    lineHeight: 21,
  },

  label: {
    color: '#173447',
    fontSize: 14,
    fontWeight: '700',
    marginBottom: 7,
  },

  uploadCard: {
    alignItems: 'center',
    backgroundColor: 'white',
    borderColor: '#D9E4EA',
    borderRadius: 18,
    borderStyle: 'dashed',
    borderWidth: 2,
    gap: 12,
    padding: 24,
  },

  imageIcon: {
    backgroundColor: '#EEE9F9',
    borderRadius: 12,
    color: '#7952AE',
    fontSize: 17,
    fontWeight: '900',
    overflow: 'hidden',
    paddingHorizontal: 16,
    paddingVertical: 14,
  },

  uploadTitle: {
    color: '#173447',
    fontSize: 20,
    fontWeight: '800',
  },

  previewCard: {
    backgroundColor: 'white',
    borderColor: '#D9E4EA',
    borderRadius: 18,
    borderWidth: 1,
    overflow: 'hidden',
  },

  preview: {
    backgroundColor: '#EFF3F4',
    height: 300,
    width: '100%',
  },

  fileDetails: {
    padding: 16,
  },

  fileName: {
    color: '#173447',
    fontSize: 16,
    fontWeight: '700',
    marginBottom: 5,
  },

  hint: {
    color: '#617D90',
    fontSize: 12,
    lineHeight: 18,
  },

  hintCentre: {
    color: '#617D90',
    fontSize: 12,
    lineHeight: 18,
    textAlign: 'center',
  },

  card: {
    backgroundColor: 'white',
    borderColor: '#D9E4EA',
    borderRadius: 18,
    borderWidth: 1,
    gap: 16,
    padding: 20,
  },
});