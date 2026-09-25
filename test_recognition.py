import cv2
import face_recognition
import pickle
import numpy as np

TOLERANCE = 0.5  # lower = stricter match

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

cam = cv2.VideoCapture(0)
if not cam.isOpened():
    print("ERROR: Could not open camera")
    exit()

print("Recognizing. Press 'q' to quit.")

while True:
    ret, frame = cam.read()
    if not ret:
        break

    rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    locations = face_recognition.face_locations(rgb, model="hog")
    encodings = face_recognition.face_encodings(rgb, locations)

    for (top, right, bottom, left), face_encoding in zip(locations, encodings):
        distances = face_recognition.face_distance(known_encodings, face_encoding)

        if len(distances) > 0:
            best_idx = int(np.argmin(distances))
            best_distance = distances[best_idx]
        else:
            best_distance = 999

        if best_distance <= TOLERANCE:
            label = f"{known_names[best_idx]} ({best_distance:.2f})"
            color = (0, 255, 0)  # green = known
        else:
            label = f"UNKNOWN ({best_distance:.2f})"
            color = (0, 0, 255)  # red = unknown

        cv2.rectangle(frame, (left, top), (right, bottom), color, 2)
        cv2.putText(frame, label, (left, top - 10),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)

    cv2.imshow("Recognition Test", frame)

    if cv2.waitKey(1) & 0xFF == ord('q'):
        break

cam.release()
cv2.destroyAllWindows()