import cv2

cam = cv2.VideoCapture(0)

if not cam.isOpened():
    print("ERROR: Could not open camera at index 0")
else:
    print("Camera opened successfully. Press 'q' in the window to quit.")

    while True:
        ret, frame = cam.read()
        if not ret:
            print("Failed to grab frame")
            break

        cv2.imshow("Camera Test", frame)

        if cv2.waitKey(1) & 0xFF == ord('q'):
            break

cam.release()
cv2.destroyAllWindows()