import React from 'react';
import {
  ActivityIndicator,
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
import { checkImageContext } from '../services/api';

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

export default function Image_Context_Analysis_Screen({ onNavigate, onResult, setWorking }) {
  const { firebaseUser, profile, refreshProfile } = useAuth();

  const [selectedImage, setSelectedImage] = React.useState(null);
  const [analysing, setAnalysing] = React.useState(false);

  const requestKeyRef = React.useRef(null);

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
    if (analysing) return;

    requestKeyRef.current = null;
    setSelectedImage(null);
  }

  async function analyseImage() {
    if (!selectedImage || !firebaseUser || analysing) return;

    // Reuse the same key when retrying a request that might
    // have completed despite a connection error or timeout.
    if (!requestKeyRef.current) {
      requestKeyRef.current =
        `${Date.now()}-${Math.random().toString(36).slice(2)}`;
    }

    try {
      setAnalysing(true);
      setWorking?.(true);

      const imageToUpload = {
        ...selectedImage,
        fileName: selectedImage.fileName || 'image',
      };

      const result = await checkImageContext(
        firebaseUser,
        imageToUpload,
        requestKeyRef.current,
      );

      // The request succeeded. A future intentional check
      // should use a new idempotency key.
      requestKeyRef.current = null;

      try {
        await refreshProfile();
      } catch (refreshError) {
        console.warn('Could not refresh allowance:', refreshError);
      }

      onResult(result);
    } catch (error) {
      console.error('Image context analysis error:', error);

      // If the backend recorded a failed analysis, a fresh
      // attempt should use a new request key.
      if (
        error.code === 'IMAGE_CONTEXT_ANALYSIS_FAILED' ||
        error.code === 'PREVIOUS_ANALYSIS_FAILED'
      ) {
        requestKeyRef.current = null;
      }

      Alert.alert(
        'Analysis failed',
        error.message ||
          'Unable to check the image context. Please try again.',
      );
    } finally {
      setAnalysing(false);
      setWorking?.(false);
    }
  }

  return (
    <View style={{ flex: 1 }}>
      <PageHeader
        title="Check image context"
        onBack={() => onNavigate('home')}
        badge={remaining == null ? '— left' : `${remaining} left`}
      />

      <PageBody>
        <View>
          <Text style={styles.eyebrow}>
            IMAGE CONTEXT ANALYSIS
          </Text>

          <Text style={styles.title}>
            Choose an image
          </Text>

          <Text style={styles.copy}>
            Select a screenshot of a social media post to preview.
            We will extract its caption, search for relevant evidence,
            and analyse whether the caption and image may be misleading.
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
              disabled={analysing}
              onPress={chooseImage}
            >
              Choose another image
            </Button>

            <Button
              secondary
              disabled={analysing}
              onPress={removeImage}
            >
              Remove image
            </Button>
          </>
        )}

        <View style={styles.info}>
          <Text style={styles.label}>
            About image context checking
          </Text>

          <Text style={styles.copy}>
            This feature checks whether a social media post's caption
            and image may be misleading. It extracts the caption,
            searches for relevant information, and uses that evidence
            to produce an assessment and explanation.
          </Text>
        </View>

        <Button
          disabled={!selectedImage || analysing}
          loading={analysing}
          onPress={analyseImage}
        >
          {analysing ? 'Analysing...' : 'Analyse image'}
        </Button>

        <View style={styles.status}>
          {analysing && (
            <ActivityIndicator color="#7952AE" />
          )}

          <Text style={styles.hintCentre}>
            {analysing
              ? 'Please keep this screen open while the caption is extracted and the image context is analysed.'
              : selectedImage
                ? 'Your image is ready to analyse.'
                : 'Select an image to begin analysis.'}
          </Text>
        </View>
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

  status: {
    alignItems: 'center',
    gap: 8,
  },

  info: {
    backgroundColor: '#EEE9F9',
    borderLeftWidth: 3,
    borderLeftColor: '#7952AE',
    padding: 16,
    borderRadius: 14,
    gap: 10,
  },
});