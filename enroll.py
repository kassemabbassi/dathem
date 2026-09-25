import cv2
import face_recognition
import pickle
import os
import time
import argparse

ENCODINGS_FILE = "encodings.pkl"


def load_existing():
    if os.path.exists(ENCODINGS_FILE):
        with open(ENCODINGS_FILE, "rb") as f:
            return pickle.load(f)
    return {}


def save(data):
    with open(ENCODINGS_FILE, "wb") as f:
        pickle.dump(data, f)


def enroll(name, samples_needed=8):
    cam = cv2.VideoCapture(0)
    if not cam.isOpened():
        print("ERROR: Could not open camera")
        return

    print(f"Enrolling '{name}'. Move your head slightly between captures.")
    print("Press 'q' to abort.\n")

    collected = []
    last_capture = 0

    while len(collected) < samples_needed:
        ret, frame = cam.read()
        if not ret:
            continue

        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        locations = face_recognition.face_locations(rgb, model="hog")

        display = frame.copy()
        for (top, right, bottom, left) in locations:
            cv2.rectangle(display, (left, top), (right, bottom), (0, 255, 0), 2)

        cv2.putText(display, f"Captured: {len(collected)}/{samples_needed}",
                    (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2)
        cv2.imshow("Enrollment", display)

        now = time.time()
        if len(locations) == 1 and (now - last_capture) > 1.0:
            encoding = face_recognition.face_encodings(rgb, locations)[0]
            collected.append(encoding)
            last_capture = now
            print(f"Captured sample {len(collected)}/{samples_needed}")
        elif len(locations) > 1:
            cv2.putText(display, "Multiple faces - only you should be visible",
                        (10, 60), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 255), 2)

        if cv2.waitKey(1) & 0xFF == ord('q'):
            print("Aborted.")
            cam.release()
            cv2.destroyAllWindows()
            return

    cam.release()
    cv2.destroyAllWindows()

    data = load_existing()
    data[name] = collected
    save(data)

    print(f"\nDone. '{name}' enrolled with {len(collected)} samples.")
    print(f"Enrolled people so far: {list(data.keys())}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--name", required=True)
    parser.add_argument("--samples", type=int, default=8)
    args = parser.parse_args()
    enroll(args.name, args.samples)