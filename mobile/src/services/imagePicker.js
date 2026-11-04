import AsyncStorage from '@react-native-async-storage/async-storage';
import * as ImagePicker from 'expo-image-picker';
import { Platform } from 'react-native';

const KEY = 'uiabo.pendingImagePicker';
const PAGES = ['ocr', 'imageContext', 'deepfakeAI'];

export async function chooseImageFor(userId, page, options) {
  if (!PAGES.includes(page)) throw new Error('Unknown image screen');
  if (Platform.OS === 'web') return ImagePicker.launchImageLibraryAsync(options);
  await AsyncStorage.setItem(KEY, JSON.stringify({ userId, page, at: Date.now() }));
  try { return await ImagePicker.launchImageLibraryAsync(options); }
  finally { await AsyncStorage.removeItem(KEY).catch(() => {}); }
}

export async function recoverImageSelection(userId) {
  const [saved, selection] = await Promise.all([AsyncStorage.getItem(KEY), ImagePicker.getPendingResultAsync()]);
  await AsyncStorage.removeItem(KEY);
  let intent;
  try { intent = JSON.parse(saved); } catch { return null; }
  const age = Date.now() - intent?.at;
  if (!intent || intent.userId !== userId || !PAGES.includes(intent.page) || !Number.isFinite(age) || age < 0 || age > 600000 || !selection || selection.canceled) return null;
  return { page: intent.page, selection };
}
