import { requireNativeModule } from 'expo';
import { Platform } from 'react-native';

export type DathemAgentNativeModule = {
  start(): Promise<boolean>;
  stop(): Promise<boolean>;
};

function getNativeModule(): DathemAgentNativeModule {
  if (Platform.OS !== 'android') {
    throw new Error('L’agent Dathem est disponible uniquement sur Android.');
  }
  return requireNativeModule<DathemAgentNativeModule>('DathemAgent');
}

const DathemAgent: DathemAgentNativeModule = {
  start: async () => getNativeModule().start(),
  stop: async () => getNativeModule().stop(),
};

export default DathemAgent;
