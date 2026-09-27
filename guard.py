import cv2
import face_recognition
import pickle
import numpy as np
import time
from lock_screen import LockScreen

TOLERANCE = 0.5
ABSENCE_LOCK_AFTER = 20     # lock if no one detected for this many seconds
READ_ERROR_RETRY = 0.05     # short retry only when the camera fails to return a frame
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
    """Shows the lock screen and blocks until unlocked. If the correct
    password was entered, returns the face encoding captured at that
    moment so the caller can grant this person session-level trust.
    Returns None if no face could be captured (encoding stays untrusted)."""
    print(">>> TRIGGERING LOCK SCREEN <<<")
    screen = LockScreen()
    return screen.captured_encoding


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


def grant_session_trust(encoding):
    """Adds a freshly captured face to the in-memory known list for the
    rest of this run. NOT saved to encodings.pkl - resets next time
    guard.py is restarted. This is what stops an immediate re-lock
    right after someone correctly enters the password."""
    if encoding is None:
        print("WARNING: Could not capture a face at unlock time - "
              "session trust not granted, this person may be re-locked.")
        return

    known_encodings.append(encoding)
    known_names.append("session_trusted")
    print(">>> Session trust granted to the person who unlocked the screen <<<")


def trigger_lock(cam):
    """Releases the main-loop camera handle before showing the lock
    screen (which needs its own exclusive access to the webcam to
    capture the unlocking person's face), then reopens it afterward.
    Returns a fresh, working VideoCapture object to keep using in the
    main loop - the caller must replace its `cam` variable with it."""
    print(">>> Releasing camera before showing lock screen...")
    cam.release()

    captured = lock_windows()
    grant_session_trust(captured)

    print(">>> Reopening camera after unlock...")
    new_cam = cv2.VideoCapture(0)
    if not new_cam.isOpened():
        print("WARNING: Could not reopen camera after unlock. "
              "Guard will keep retrying.")
    return new_cam


def main():
    cam = cv2.VideoCapture(0)
    # Avoid processing frames queued while face recognition is busy; the next
    # analysis should use the most recent image available from the camera.
    cam.set(cv2.CAP_PROP_BUFFERSIZE, 1)
    if not cam.isOpened():
        print("ERROR: Could not open camera")
        return

    print("Guard running. Press Ctrl+C to stop.\n")

    absence_start = None
    last_lock_time = 0

    try:
        while True:
            ret, frame = cam.read()
            if not ret:
                time.sleep(READ_ERROR_RETRY)
                continue

            total, unknown_count, names_seen = analyze_frame(frame)
            now = time.time()

            if total == 0:
                if absence_start is None:
                    absence_start = now
                elapsed = now - absence_start
                print(f"[{time.strftime('%H:%M:%S')}] No one detected ({elapsed:.0f}s)")
                if elapsed >= ABSENCE_LOCK_AFTER and (now - last_lock_time) > LOCK_COOLDOWN:
                    cam = trigger_lock(cam)
                    last_lock_time = time.time()
                    absence_start = None

            else:
                absence_start = None

                if unknown_count > 0:
                    print(f"[{time.strftime('%H:%M:%S')}] Faces: {names_seen} "
                          "-> unknown present; locking immediately")
                    if (now - last_lock_time) > LOCK_COOLDOWN:
                        cam = trigger_lock(cam)
                        last_lock_time = time.time()
                else:
                    print(f"[{time.strftime('%H:%M:%S')}] Faces: {names_seen} -> OK")

    except KeyboardInterrupt:
        print("\nStopped by user.")
    finally:
        cam.release()


if __name__ == "__main__":
    main()
