const { getDefaultConfig } = require('expo/metro-config');
const path = require('path');

// Firebase JS SDK v12 dropped the react-native resolution path from the public
// firebase/auth wrapper, so Metro resolves it to the browser build where
// getReactNativePersistence does not exist. Redirect the whole firebase/auth
// module graph to the RN build of @firebase/auth on native platforms, as
// recommended by the Firebase team (firebase-js-sdk issue #9316).
const FIREBASE_AUTH_RN_PATH = path.resolve(
  __dirname,
  'node_modules/@firebase/auth/dist/rn/index.js',
);

const config = getDefaultConfig(__dirname);

const originalResolver = config.resolver.resolveRequest;
config.resolver.resolveRequest = (context, moduleName, platform) => {
  if (moduleName === 'firebase/auth' && platform !== 'web') {
    return { type: 'sourceFile', filePath: FIREBASE_AUTH_RN_PATH };
  }
  if (originalResolver) {
    return originalResolver(context, moduleName, platform);
  }
  return context.resolveRequest(context, moduleName, platform);
};

module.exports = config;
