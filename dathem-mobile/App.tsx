import { useEffect, useState } from 'react';
import {
  ActivityIndicator,
  ImageBackground,
  KeyboardAvoidingView,
  Platform,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  TouchableOpacity,
  View,
} from 'react-native';
import { StatusBar } from 'expo-status-bar';
import * as SecureStore from 'expo-secure-store';
import * as Notifications from 'expo-notifications';
import { SafeAreaProvider, SafeAreaView } from 'react-native-safe-area-context';
import FaceEnrollment from './FaceEnrollment';
import DathemAgent from './modules/dathem-agent';

const eyes = require('./assets/eyes.jpg');
const PASSWORD_KEY = 'dathem.guard.password.v1';
const FACE_VECTOR_KEY = 'dathem.guard.face-vector.v1';
const GUARD_ACTIVE_KEY = 'dathem.guard.active.v1';

function DathemGuard() {
  const [password, setPassword] = useState('');
  const [confirmation, setConfirmation] = useState('');
  const [message, setMessage] = useState('');
  const [saved, setSaved] = useState<boolean | null>(null);
  const [faceEnrolled, setFaceEnrolled] = useState(false);
  const [guardActive, setGuardActive] = useState(false);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    let mounted = true;
    SecureStore.getItemAsync(PASSWORD_KEY)
      .then(async (value) => {
        const faceVector = await SecureStore.getItemAsync(FACE_VECTOR_KEY);
        const isGuardActive = await SecureStore.getItemAsync(GUARD_ACTIVE_KEY);
        let restoredGuard = false;
        if (faceVector !== null && isGuardActive === 'true' && Platform.OS === 'android') {
          try {
            const notificationPermission = await Notifications.getPermissionsAsync();
            if (notificationPermission.granted) {
              await DathemAgent.start();
              restoredGuard = true;
            } else {
              await SecureStore.setItemAsync(GUARD_ACTIVE_KEY, 'false');
            }
          } catch (error) {
            console.error('[Dathem][Guard] Reprise de l’agent impossible.', error);
            await SecureStore.setItemAsync(GUARD_ACTIVE_KEY, 'false');
          }
        }
        if (mounted) {
          setSaved(value !== null);
          setFaceEnrolled(faceVector !== null);
          setGuardActive(restoredGuard);
        }
      })
      .catch(() => {
        if (mounted) {
          setSaved(false);
          setMessage('Impossible de lire le stockage sécurisé de cet appareil.');
        }
      });
    return () => {
      mounted = false;
    };
  }, []);

  async function createPassword() {
    setMessage('');
    if (password.length < 8) {
      setMessage('Choisis un mot de passe d’au moins 8 caractères.');
      return;
    }
    if (password !== confirmation) {
      setMessage('Les deux mots de passe ne correspondent pas.');
      return;
    }

    setSaving(true);
    try {
      await SecureStore.setItemAsync(PASSWORD_KEY, password);
      setSaved(true);
      setFaceEnrolled(false);
      setPassword('');
      setConfirmation('');
    } catch {
      setMessage('Enregistrement impossible. Réessaie dans un instant.');
    } finally {
      setSaving(false);
    }
  }

  async function updateGuardState(active: boolean) {
    if (Platform.OS !== 'android') {
      throw new Error('Le service de garde est disponible uniquement sur Android.');
    }
    if (active) {
      let permission = await Notifications.getPermissionsAsync();
      if (!permission.granted) permission = await Notifications.requestPermissionsAsync();
      if (!permission.granted) {
        throw new Error('Autorise les notifications pour afficher l’agent Dathem actif.');
      }
      await DathemAgent.start();
      try {
        await SecureStore.setItemAsync(GUARD_ACTIVE_KEY, 'true');
      } catch (error) {
        await DathemAgent.stop();
        throw error;
      }
      setGuardActive(true);
      return;
    }
    await DathemAgent.stop();
    await SecureStore.setItemAsync(GUARD_ACTIVE_KEY, 'false');
    setGuardActive(false);
  }

  return (
    <ImageBackground source={eyes} resizeMode="cover" style={styles.background}>
      <View style={styles.shade}>
        <StatusBar style="light" />
        <SafeAreaView style={styles.safeArea}>
          {saved === null ? (
            <View style={styles.loading}>
              <ActivityIndicator color="#ff3636" size="large" />
            </View>
          ) : (
            <KeyboardAvoidingView
              style={styles.flex}
              behavior={Platform.OS === 'ios' ? 'padding' : undefined}
            >
              <ScrollView
                contentContainerStyle={styles.scrollContent}
                keyboardShouldPersistTaps="handled"
              >
                <View style={styles.content}>
                  <Text style={styles.eyebrow}>MOBILE SECURITY</Text>
                  <Text style={styles.title}>DATHEM</Text>
                  <Text style={styles.subtitle}>YOUR PHONE. UNDER WATCH.</Text>

                  {saved ? (
                    <View style={styles.card}>
                      <FaceEnrollment
                        enrolled={faceEnrolled}
                        onEnrolled={() => setFaceEnrolled(true)}
                        guardActive={guardActive}
                        onGuardChange={updateGuardState}
                      />
                    </View>
                  ) : (
                    <View style={styles.card}>
                      <Text style={styles.step}>ÉTAPE 1 SUR 2</Text>
                      <Text style={styles.cardTitle}>Crée ton mot de passe</Text>
                      <Text style={styles.description}>
                        Il servira de méthode de secours pour accéder à Dathem.
                      </Text>

                      <TextInput
                        value={password}
                        onChangeText={setPassword}
                        placeholder="Mot de passe (8 caractères minimum)"
                        placeholderTextColor="#9b8585"
                        secureTextEntry
                        autoCapitalize="none"
                        autoCorrect={false}
                        autoComplete="new-password"
                        textContentType="newPassword"
                        style={styles.input}
                        accessibilityLabel="Créer un mot de passe"
                      />
                      <TextInput
                        value={confirmation}
                        onChangeText={setConfirmation}
                        placeholder="Confirmer le mot de passe"
                        placeholderTextColor="#9b8585"
                        secureTextEntry
                        autoCapitalize="none"
                        autoCorrect={false}
                        autoComplete="new-password"
                        textContentType="newPassword"
                        onSubmitEditing={createPassword}
                        returnKeyType="done"
                        style={styles.input}
                        accessibilityLabel="Confirmer le mot de passe"
                      />

                      {message ? <Text style={styles.error}>{message}</Text> : null}

                      <TouchableOpacity
                        accessibilityRole="button"
                        disabled={saving}
                        onPress={createPassword}
                        style={[styles.button, saving && styles.buttonDisabled]}
                      >
                        <Text style={styles.buttonText}>
                          {saving ? 'ENREGISTREMENT…' : 'ENREGISTRER LE MOT DE PASSE'}
                        </Text>
                      </TouchableOpacity>
                    </View>
                  )}

                  <Text style={styles.footer}>DATHEM GUARD  •  VERSION MOBILE</Text>
                </View>
              </ScrollView>
            </KeyboardAvoidingView>
          )}
        </SafeAreaView>
      </View>
    </ImageBackground>
  );
}

export default function App() {
  return (
    <SafeAreaProvider>
      <DathemGuard />
    </SafeAreaProvider>
  );
}

const styles = StyleSheet.create({
  flex: {
    flex: 1,
  },
  background: {
    flex: 1,
    backgroundColor: '#050505',
  },
  shade: {
    flex: 1,
    backgroundColor: 'rgba(0, 0, 0, 0.62)',
  },
  safeArea: {
    flex: 1,
  },
  loading: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
  },
  scrollContent: {
    flexGrow: 1,
  },
  content: {
    flexGrow: 1,
    alignItems: 'center',
    justifyContent: 'center',
    paddingHorizontal: 26,
    paddingTop: 30,
    paddingBottom: 56,
  },
  eyebrow: {
    color: '#d33a3a',
    fontSize: 12,
    fontWeight: '700',
    letterSpacing: 4,
    marginBottom: 8,
  },
  title: {
    color: '#ff2424',
    fontSize: 46,
    fontWeight: '900',
    letterSpacing: 7,
    textShadowColor: '#900000',
    textShadowRadius: 18,
  },
  subtitle: {
    color: '#e5dada',
    fontSize: 10,
    fontWeight: '600',
    letterSpacing: 2.5,
    marginTop: 8,
  },
  card: {
    width: '100%',
    maxWidth: 400,
    marginTop: 42,
    padding: 20,
    borderColor: 'rgba(255, 40, 40, 0.58)',
    borderWidth: 1,
    borderRadius: 14,
    backgroundColor: 'rgba(8, 5, 5, 0.88)',
  },
  step: {
    color: '#e04444',
    fontSize: 11,
    fontWeight: '700',
    letterSpacing: 2,
    marginBottom: 8,
  },
  statusRow: {
    flexDirection: 'row',
    alignItems: 'center',
  },
  statusDot: {
    width: 9,
    height: 9,
    borderRadius: 5,
    backgroundColor: '#ff3636',
    marginRight: 11,
  },
  cardTitle: {
    color: '#fff',
    fontSize: 18,
    fontWeight: '700',
  },
  description: {
    color: '#c7baba',
    fontSize: 13,
    lineHeight: 20,
    marginTop: 10,
    marginBottom: 16,
  },
  input: {
    minHeight: 52,
    borderWidth: 1,
    borderColor: '#5b2828',
    borderRadius: 9,
    backgroundColor: 'rgba(0, 0, 0, 0.62)',
    color: '#fff',
    fontSize: 14,
    paddingHorizontal: 14,
    marginTop: 12,
  },
  error: {
    color: '#ff7777',
    fontSize: 13,
    lineHeight: 18,
    marginTop: 12,
  },
  button: {
    minHeight: 52,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: '#9f1111',
    borderRadius: 9,
    marginTop: 18,
    paddingHorizontal: 12,
  },
  buttonDisabled: {
    opacity: 0.65,
  },
  buttonText: {
    color: '#fff',
    fontSize: 12,
    fontWeight: '800',
    letterSpacing: 1,
  },
  footer: {
    position: 'absolute',
    bottom: 18,
    color: '#a89595',
    fontSize: 9,
    letterSpacing: 1.7,
  },
});
