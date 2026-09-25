import cv2
import face_recognition
import time

cam = cv2.VideoCapture(0)

if not cam.isOpened():
    print("ERROR: Could not open camera")
    exit()

print("Detecting faces. Press 'q' to quit.")

while True:
    ret, frame = cam.read()
    if not ret:
        break

    # face_recognition expects RGB, OpenCV gives BGR
    rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

    start = time.time()
    face_locations = face_recognition.face_locations(rgb_frame, model="hog")
    elapsed = time.time() - start

    # Draw a box around every detected face
    for (top, right, bottom, left) in face_locations:
        cv2.rectangle(frame, (left, top), (right, bottom), (0, 255, 0), 2)

    cv2.putText(
        frame,
        f"Faces: {len(face_locations)} | {elapsed*1000:.0f}ms",
        (10, 30),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.7,
        (0, 255, 0),
        2
    )

    cv2.imshow("Face Detection Test", frame)

    if cv2.waitKey(1) & 0xFF == ord('q'):
        break

cam.release()
cv2.destroyAllWindows()