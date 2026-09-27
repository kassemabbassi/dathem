import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  ActivityIndicator,
  LayoutChangeEvent,
  StyleSheet,
  Text,
  TouchableOpacity,
  View,
} from 'react-native';
import * as SecureStore from 'expo-secure-store';
import { Camera, usePhotoOutput, useCameraDevice, useCameraPermission, type CameraRef } from 'react-native-vision-camera';
import { createFaceDetectorOutput, transformFacesToPreviewCoordinates, type Face } from 'react-native-vision-camera-face-detector';
import { useTensorflowModel } from 'react-native-fast-tflite';

// Metro must resolve the model as a bundled binary asset.
// eslint-disable-next-line @typescript-eslint/no-require-imports
const faceModelAsset = require('./assets/models/mobile_facenet-tflite-float/mobile_facenet.tflite');
const FACE_VECTOR_KEY = 'dathem.guard.face-vector.v1';
const MODEL_SIZE = 112;
const PIXELS = MODEL_SIZE * MODEL_SIZE;

function normalize(values: number[]): number[] {
  const length = Math.sqrt(values.reduce((sum, value) => sum + value * value, 0));
  if (!Number.isFinite(length) || length < 1e-8) {
    throw new Error('Le modèle n’a pas produit de mesure faciale valide.');
  }
  return values.map((value) => value / length);
}

function createModelInput(
  pixels: Uint8Array,
  width: number,
  height: number,
  pixelFormat: string,
): ArrayBuffer {
  const bytesPerPixel = pixels.length / (width * height);
  if (!Number.isInteger(bytesPerPixel) || bytesPerPixel < 3) {
    throw new Error('Format de pixels non pris en charge par le modèle.');
  }

  const isBgr = pixelFormat === 'BGR' || pixelFormat === 'BGRA' || pixelFormat === 'BGRX';
  const tensor = new Float32Array(PIXELS * 3);
  for (let pixel = 0; pixel < PIXELS; pixel += 1) {
    const source = pixel * bytesPerPixel;
    const red = pixels[source + (isBgr ? 2 : 0)] / 255;
    const green = pixels[source + 1] / 255;
    const blue = pixels[source + (isBgr ? 0 : 2)] / 255;
    tensor[pixel] = red;
    tensor[PIXELS + pixel] = green;
    tensor[PIXELS * 2 + pixel] = blue;
  }
  return tensor.buffer;
}

type Props = {
  enrolled: boolean;
  onEnrolled: () => void;
  guardActive: boolean;
  onGuardChange: (active: boolean) => Promise<void>;
};

export default function FaceEnrollment({ enrolled, onEnrolled, guardActive, onGuardChange }: Props) {
  const device = useCameraDevice('front');
  const permission = useCameraPermission();
  const modelState = useTensorflowModel(faceModelAsset, []);
  const photoOutput = usePhotoOutput({ containerFormat: 'jpeg', qualityPrioritization: 'speed' });
  const [started, setStarted] = useState(false);
  const [hint, setHint] = useState('Le modèle facial se prépare.');
  const [busy, setBusy] = useState(false);
  const [guardBusy, setGuardBusy] = useState(false);
  const [complete, setComplete] = useState(enrolled);
  const [previewSize, setPreviewSize] = useState({ width: 0, height: 0 });
  const [eyePoints, setEyePoints] = useState<{ left: { x: number; y: number }; right: { x: number; y: number } } | null>(null);
  const faceReady = useRef(false);
  const captureInProgress = useRef(false);
  const statusLockUntil = useRef(0);
  const lastLoggedHint = useRef('');
  const previewSizeRef = useRef(previewSize);
  const eyePointsRef = useRef<typeof eyePoints>(null);
  const lastEyeUpdate = useRef(0);
  const completeRef = useRef(enrolled);
  const cameraRef = useRef<CameraRef>(null);

  const reportHint = useCallback((message: string) => {
    setHint(message);
    if (lastLoggedHint.current !== message) {
      lastLoggedHint.current = message;
      console.log(`[Dathem][FaceEnrollment] ${new Date().toISOString()} ${message}`);
    }
  }, []);

  useEffect(() => {
    console.log(`[Dathem][FaceEnrollment] ${new Date().toISOString()} modèle TFLite: ${modelState.state}`);
    if (modelState.state === 'error') {
      console.error('[Dathem][FaceEnrollment] Échec du chargement du modèle TFLite.', modelState.error);
    }
  }, [modelState]);

  const handleFacesDetected = useCallback((faces: Face[]) => {
    const camera = cameraRef.current;
    const previewFaces = camera?.preview
      ? transformFacesToPreviewCoordinates(faces, camera)
      : faces;
    faceReady.current = false;
    if (previewFaces.length === 0) {
      if (eyePointsRef.current !== null) {
        eyePointsRef.current = null;
        setEyePoints(null);
      }
      if (!captureInProgress.current && Date.now() >= statusLockUntil.current) {
        reportHint('Place ton visage dans le cadre.');
      }
      return;
    }
    if (previewFaces.length > 1) {
      if (eyePointsRef.current !== null) {
        eyePointsRef.current = null;
        setEyePoints(null);
      }
      if (!captureInProgress.current && Date.now() >= statusLockUntil.current) {
        reportHint('Une seule personne doit être visible.');
      }
      return;
    }

    const face = previewFaces[0];
    const leftEye = face.landmarks?.LEFT_EYE;
    const rightEye = face.landmarks?.RIGHT_EYE;
    if (leftEye && rightEye && Date.now() - lastEyeUpdate.current >= 90) {
      const points = { left: leftEye, right: rightEye };
      eyePointsRef.current = points;
      lastEyeUpdate.current = Date.now();
      setEyePoints(points);
    }
    if (captureInProgress.current || Date.now() < statusLockUntil.current) return;
    if (completeRef.current) {
      reportHint('Les repères suivent les yeux en direct tant que Dathem est ouvert.');
      return;
    }

    const preview = previewSizeRef.current;
    const centered = preview.width > 0 &&
      Math.abs(face.bounds.x + face.bounds.width / 2 - preview.width / 2) < preview.width * 0.2 &&
      Math.abs(face.bounds.y + face.bounds.height / 2 - preview.height / 2) < preview.height * 0.22;
    const largeEnough = preview.width > 0 && face.bounds.width > preview.width * 0.24;
    if (!centered || !largeEnough) {
      reportHint('Rapproche ou recentre ton visage dans le cadre.');
      return;
    }

    const eyesOpen = face.leftEyeOpenProbability !== undefined &&
      face.rightEyeOpenProbability !== undefined &&
      face.leftEyeOpenProbability > 0.55 && face.rightEyeOpenProbability > 0.55;
    if (!eyesOpen) {
      reportHint('Regarde droit devant toi, les deux yeux ouverts.');
      return;
    }
    if (Math.abs(face.yawAngle) > 12 || Math.abs(face.pitchAngle) > 15) {
      reportHint('Regarde droit devant toi, sans incliner la tête.');
      return;
    }

    faceReady.current = true;
    reportHint('C’est bon. Appuie sur « Capturer mon visage ».');
  }, [reportHint]);

  const handleCameraError = useCallback((error: Error) => {
    console.error(`[Dathem][FaceEnrollment] ${new Date().toISOString()} erreur caméra`, error);
    setStarted(false);
    faceReady.current = false;
    eyePointsRef.current = null;
    setEyePoints(null);
    reportHint(`Erreur caméra : ${error.message}`);
  }, [reportHint]);

  // The detector is a stable native output. Creating it inside this memo is required
  // so a button state update cannot reconfigure and close the active camera session.
  // eslint-disable-next-line react-hooks/refs
  const faceOutput = useMemo(() => createFaceDetectorOutput({
    cameraFacing: 'front',
    mirrorMode: 'auto',
    autoMode: true,
    outputResolution: 'preview',
    performanceMode: 'fast',
    runClassifications: true,
    runLandmarks: true,
    onFacesDetected: handleFacesDetected,
    onError: handleCameraError,
  }), [handleCameraError, handleFacesDetected]);
  const outputs = useMemo(() => [faceOutput, photoOutput], [faceOutput, photoOutput]);

  function onPreviewLayout(event: LayoutChangeEvent) {
    const { width, height } = event.nativeEvent.layout;
    const size = { width, height };
    previewSizeRef.current = size;
    setPreviewSize(size);
  }

  async function startEnrollment() {
    if (!complete && modelState.state !== 'loaded') {
      reportHint(modelState.state === 'error' ? 'Impossible de charger le modèle facial.' : 'Le modèle facial se prépare.');
      console.warn(`[Dathem][FaceEnrollment] ${new Date().toISOString()} démarrage refusé; modèle=${modelState.state}`);
      return;
    }
    if (!permission.hasPermission && !(await permission.requestPermission())) {
      reportHint('Autorise la caméra dans les paramètres Android pour continuer.');
      console.warn(`[Dathem][FaceEnrollment] ${new Date().toISOString()} autorisation caméra refusée`);
      return;
    }
    setStarted(true);
    reportHint(complete ? 'Recherche des yeux…' : 'Place-toi face à la caméra, les deux yeux ouverts.');
    console.log(`[Dathem][FaceEnrollment] ${new Date().toISOString()} caméra démarrée; inscription terminée=${complete}`);
  }

  async function capturePosition() {
    const model = modelState.state === 'loaded' ? modelState.model : undefined;
    console.log(`[Dathem][FaceEnrollment] ${new Date().toISOString()} bouton capture; modèle=${modelState.state}, visage prêt=${faceReady.current}, occupé=${busy}`);
    if (!model || !faceReady.current || busy) {
      console.warn(`[Dathem][FaceEnrollment] ${new Date().toISOString()} capture ignorée: modèle, cadrage ou état occupé invalide`);
      return;
    }

    setBusy(true);
    captureInProgress.current = true;
    faceReady.current = false;
    reportHint('Capture et calcul local du vecteur facial…');
    const captureStartedAt = Date.now();
    console.log(`[Dathem][FaceEnrollment] ${new Date().toISOString()} capture commencée`);
    let photo: Awaited<ReturnType<typeof photoOutput.capturePhoto>> | undefined;
    try {
      photo = await photoOutput.capturePhoto({ flashMode: 'off' }, {});
      console.log(`[Dathem][FaceEnrollment] ${new Date().toISOString()} photo capturée: ${photo.width}x${photo.height}`);
      const image = await photo.toImageAsync();
      const cropSize = Math.min(image.width, image.height) * 0.7;
      const crop = await image.cropAsync(
        (image.width - cropSize) / 2,
        (image.height - cropSize) / 2,
        (image.width + cropSize) / 2,
        (image.height + cropSize) / 2,
      );
      const modelImage = await crop.resizeAsync(MODEL_SIZE, MODEL_SIZE);
      const raw = await modelImage.toRawPixelDataAsync();
      const input = createModelInput(new Uint8Array(raw.buffer), raw.width, raw.height, raw.pixelFormat);
      const output = await model.run([input, input]);
      const values = new Float32Array(output[0]);
      console.log(`[Dathem][FaceEnrollment] ${new Date().toISOString()} inférence terminée; sortie=${values.length} valeurs`);
      if (values.length < 128) throw new Error('Sortie du modèle facial inattendue.');
      const identityVector = normalize(Array.from(values.slice(0, 128)));
      const compactVector = identityVector.map((value) => Number(value.toFixed(5)));
      await SecureStore.setItemAsync(FACE_VECTOR_KEY, JSON.stringify(compactVector));
      completeRef.current = true;
      setComplete(true);
      setStarted(false);
      statusLockUntil.current = Date.now() + 1800;
      reportHint('Inscription terminée. Les repères des yeux sont suivis en direct.');
      console.log(`[Dathem][FaceEnrollment] ${new Date().toISOString()} vecteur sécurisé; opération=${Date.now() - captureStartedAt}ms; aucune photo conservée`);
      onEnrolled();
    } catch (error) {
      statusLockUntil.current = Date.now() + 2500;
      const message = error instanceof Error ? error.message : 'La capture a échoué. Réessaie.';
      reportHint(message);
      console.error(`[Dathem][FaceEnrollment] ${new Date().toISOString()} échec après ${Date.now() - captureStartedAt}ms`, error);
    } finally {
      photo?.dispose();
      captureInProgress.current = false;
      setBusy(false);
    }
  }

  async function toggleGuard() {
    if (guardBusy) return;
    setGuardBusy(true);
    try {
      if (guardActive) {
        await onGuardChange(false);
        setStarted(false);
        reportHint('Dathem est désactivé.');
        console.log(`[Dathem][Guard] ${new Date().toISOString()} garde désactivée`);
        return;
      }
      if (!permission.hasPermission && !(await permission.requestPermission())) {
        reportHint('Autorise la caméra pour activer la garde Dathem.');
        return;
      }
      await onGuardChange(true);
      setStarted(false);
      reportHint('Agent Dathem démarré. La caméra en arrière-plan sera ajoutée à l’étape suivante.');
      console.log(`[Dathem][Guard] ${new Date().toISOString()} service natif démarré; caméra non connectée à cette étape`);
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Impossible de modifier la garde Dathem.';
      reportHint(message);
      console.error(`[Dathem][Guard] ${new Date().toISOString()} échec changement état`, error);
    } finally {
      setGuardBusy(false);
    }
  }

  return (
    <View>
      <View style={styles.headerRow}>
        <View style={[styles.statusDot, complete && styles.statusComplete]} />
        <Text style={styles.cardTitle}>{complete ? 'Visage inscrit' : 'Inscription du visage autorisé'}</Text>
      </View>
      <Text style={styles.description}>
        Dathem capture une seule image de face, la transforme en vecteur sur le téléphone, puis supprime l’image. Les repères rouges suivent ensuite les deux yeux dans l’aperçu.
      </Text>

      {started && device ? (
        <View style={styles.preview} onLayout={onPreviewLayout}>
          <Camera
            style={StyleSheet.absoluteFill}
            ref={cameraRef}
            device={device}
            isActive
            mirrorMode="auto"
            outputs={outputs}
            onError={handleCameraError}
          />
          <View pointerEvents="none" style={styles.guide} />
          {eyePoints ? (
            <>
              <View pointerEvents="none" style={[styles.eyeMarker, { left: eyePoints.left.x - 9, top: eyePoints.left.y - 9 }]} />
              <View pointerEvents="none" style={[styles.eyeMarker, { left: eyePoints.right.x - 9, top: eyePoints.right.y - 9 }]} />
            </>
          ) : null}
        </View>
      ) : (
        <View style={styles.placeholder}>
          {modelState.state === 'loading' ? <ActivityIndicator color="#ff3636" /> : null}
          <Text style={styles.placeholderText}>
            {modelState.state === 'error'
              ? 'Le modèle facial n’a pas pu être chargé.'
              : complete
                ? 'Visage inscrit. Le service de garde sera relié à la caméra à l’étape suivante.'
                : modelState.state === 'loading'
                  ? 'Chargement du modèle facial…'
                  : 'La caméra ne démarre que lorsque tu lances l’inscription.'}
          </Text>
        </View>
      )}

      <Text style={styles.hint}>{hint}</Text>
      {!complete ? (
        <TouchableOpacity
          accessibilityRole="button"
          disabled={busy || modelState.state === 'loading'}
          onPress={() => (started ? void capturePosition() : void startEnrollment())}
          style={[styles.button, (busy || modelState.state === 'loading') && styles.buttonDisabled]}
        >
          {busy ? <ActivityIndicator color="#fff" /> : null}
          <Text style={styles.buttonText}>
            {started ? 'CAPTURER MON VISAGE' : 'COMMENCER L’INSCRIPTION FACIALE'}
          </Text>
        </TouchableOpacity>
      ) : (
        <TouchableOpacity
          accessibilityRole="button"
          disabled={guardBusy}
          onPress={() => void toggleGuard()}
          style={[styles.button, guardActive && styles.guardActiveButton, guardBusy && styles.buttonDisabled]}
        >
          {guardBusy ? <ActivityIndicator color="#fff" /> : null}
          <Text style={styles.buttonText}>{guardActive ? 'DÉSACTIVER LA GARDE DATHEM' : 'ACTIVER LA GARDE DATHEM'}</Text>
        </TouchableOpacity>
      )}
      <Text style={styles.privacyNote}>
        {complete
          ? 'Étape 1 : le service reste visible dans les notifications et suit l’état de l’écran. La caméra de garde sera connectée après validation de ce service.'
          : 'Cette reconnaissance protège l’accès à Dathem. Elle ne remplace pas le verrouillage système Android et ne surveille pas le téléphone en arrière-plan.'}
      </Text>
    </View>
  );
}

const styles = StyleSheet.create({
  headerRow: { flexDirection: 'row', alignItems: 'center' },
  statusDot: { width: 9, height: 9, borderRadius: 5, backgroundColor: '#ff3636', marginRight: 11 },
  statusComplete: { backgroundColor: '#54d68a' },
  cardTitle: { color: '#fff', fontSize: 18, fontWeight: '700', flexShrink: 1 },
  description: { color: '#c7baba', fontSize: 13, lineHeight: 20, marginTop: 10, marginBottom: 16 },
  preview: { height: 250, overflow: 'hidden', borderRadius: 10, backgroundColor: '#160c0c' },
  guide: {
    position: 'absolute',
    width: '62%',
    height: '82%',
    left: '19%',
    top: '9%',
    borderColor: 'rgba(255, 255, 255, 0.8)',
    borderWidth: 1.5,
    borderRadius: 150,
  },
  placeholder: {
    height: 120,
    alignItems: 'center',
    justifyContent: 'center',
    paddingHorizontal: 16,
    borderRadius: 10,
    backgroundColor: '#160c0c',
  },
  placeholderText: { color: '#c7baba', textAlign: 'center', fontSize: 13, lineHeight: 20, marginTop: 8 },
  hint: { color: '#fff', fontSize: 14, fontWeight: '700', marginTop: 13 },
  eyeMarker: {
    position: 'absolute',
    width: 18,
    height: 18,
    borderRadius: 9,
    borderWidth: 2,
    borderColor: '#ff3636',
    backgroundColor: 'rgba(255, 54, 54, 0.2)',
  },
  privacyNote: { color: '#b6a6a6', fontSize: 11, lineHeight: 17, marginTop: 12 },
  button: {
    minHeight: 52,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: '#9f1111',
    borderRadius: 9,
    marginTop: 18,
    paddingHorizontal: 12,
  },
  buttonDisabled: { opacity: 0.65 },
  guardActiveButton: { backgroundColor: '#315d3c', borderColor: '#54d68a', borderWidth: 1 },
  buttonText: { color: '#fff', fontSize: 12, fontWeight: '800', letterSpacing: 1, textAlign: 'center' },
});
