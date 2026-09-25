import cv2
import face_recognition
import pickle
import numpy as np
import time
from lock_screen import LockScreen

TOLERANCE = 0.5
CHECK_INTERVAL = 2          # seconds between checks
ABSENCE_LOCK_AFTER = 20     # lock if no one detected for this many seconds
BAD_READINGS_TO_LOCK = 2    # consecutive "unknown present" readings before locking
LOCK_COOLDOWN = 5           # don't re-trigger lock within this many seconds

# Load enrolled faces
with open("encodings.pkl", "rb") as f:
    data = pickle.load(f)

known_names = []
known_encodings = []
for name, samples in data.items():
    for enc in samples:
        known_names.append(name)
        known_encodings.append(enc)

print(f"Loaded {len(known_encodings)} samples for: {list(data.keys())}")


def lock_windows():
    print(">>> TRIGGERING LOCK SCREEN <<<")
    LockScreen()  # blocks here until the correct password is entered


def analyze_frame(frame):
    rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    locations = face_recognition.face_locations(rgb, model="hog")
    encodings = face_recognition.face_encodings(rgb, locations)

    total = len(encodings)
    unknown_count = 0
    names_seen = []

    for enc in encodings:
        distances = face_recognition.face_distance(known_encodings, enc)
        best_distance = np.min(distances) if len(distances) > 0 else 999

        if best_distance <= TOLERANCE:
            best_idx = int(np.argmin(distances))
            names_seen.append(known_names[best_idx])
        else:
            unknown_count += 1
            names_seen.append("unknown")

    return total, unknown_count, names_seen


def main():
    cam = cv2.VideoCapture(0)
    if not cam.isOpened():
        print("ERROR: Could not open camera")
        return

    print("Guard running. Press Ctrl+C to stop.\n")

    consecutive_bad = 0
    absence_start = None
    last_lock_time = 0

    try:
        while True:
            ret, frame = cam.read()
            if not ret:
                time.sleep(CHECK_INTERVAL)
                continue

            total, unknown_count, names_seen = analyze_frame(frame)
            now = time.time()

            if total == 0:
                if absence_start is None:
                    absence_start = now
                elapsed = now - absence_start
                print(f"[{time.strftime('%H:%M:%S')}] No one detected ({elapsed:.0f}s)")
                if elapsed >= ABSENCE_LOCK_AFTER and (now - last_lock_time) > LOCK_COOLDOWN:
                    lock_windows()
                    last_lock_time = time.time()
                    absence_start = None
                consecutive_bad = 0

            else:
                absence_start = None

                if unknown_count > 0:
                    consecutive_bad += 1
                    print(f"[{time.strftime('%H:%M:%S')}] Faces: {names_seen} "
                          f"-> unknown present ({consecutive_bad}/{BAD_READINGS_TO_LOCK})")
                    if consecutive_bad >= BAD_READINGS_TO_LOCK and (now - last_lock_time) > LOCK_COOLDOWN:
                        lock_windows()
                        last_lock_time = time.time()
                        consecutive_bad = 0
                else:
                    consecutive_bad = 0
                    print(f"[{time.strftime('%H:%M:%S')}] Faces: {names_seen} -> OK")

            time.sleep(CHECK_INTERVAL)

    except KeyboardInterrupt:
        print("\nStopped by user.")
    finally:
        cam.release()


if __name__ == "__main__":
    main()