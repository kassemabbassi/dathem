import cv2
import face_recognition
import numpy as np
import time
import threading
import queue
import tkinter as tk
from tkinter import messagebox
import os
import sys
from lock_screen import LockScreen
from dathem_config import load_profile, verify_password


def configure_frozen_logging():
    """Keep diagnostics available when the agent is built without a console."""
    if not getattr(sys, "frozen", False) or (sys.stdout is not None and sys.stderr is not None):
        return

    log_root = os.path.join(
        os.environ.get("LOCALAPPDATA", os.path.expanduser("~")), "DathemAgentV1"
    )
    os.makedirs(log_root, exist_ok=True)
    log_stream = open(
        os.path.join(log_root, "agent.log"), "a", encoding="utf-8", buffering=1
    )
    sys.stdout = log_stream
    sys.stderr = log_stream


configure_frozen_logging()

TOLERANCE = 0.5
ABSENCE_LOCK_AFTER = 20     # lock if no one detected for this many seconds
READ_ERROR_RETRY = 0.05     # short retry only when the camera fails to return a frame
LOCK_COOLDOWN = 5           # don't re-trigger lock within this many seconds
NOTIFICATION_SECONDS = 5000  # milliseconds
ANALYSIS_SCALE = 0.5        # run HOG detection on a half-size frame
STATUS_LOG_INTERVAL = 10    # keep frozen-build disk logging off the hot path


class CompanionNotifier:
    """Show a small, non-blocking Windows desktop notification via Tk."""
    def __init__(self):
        self.messages = queue.Queue()
        threading.Thread(target=self._run, daemon=True).start()

    def show(self, message):
        self.messages.put(message)

    def _run(self):
        try:
            root = tk.Tk()
            root.withdraw()
        except tk.TclError as exc:
            print(f"WARNING: Could not start desktop notifications: {exc}")
            return

        current = {"window": None, "after_id": None}

        def close_current():
            window = current["window"]
            current["window"] = None
            current["after_id"] = None
            if window is not None:
                try:
                    if window.winfo_exists():
                        window.destroy()
                except tk.TclError:
                    pass

        def poll():
            try:
                message = self.messages.get_nowait()
            except queue.Empty:
                message = None

            if message:
                if current["after_id"] is not None:
                    try:
                        root.after_cancel(current["after_id"])
                    except tk.TclError:
                        pass
                close_current()

                window = tk.Toplevel(root)
                window.overrideredirect(True)
                window.attributes("-topmost", True)
                window.configure(bg="#171717")
                tk.Label(
                    window, text="Présence détectée", bg="#171717", fg="#ff4040",
                    font=("Segoe UI", 12, "bold"), padx=18, pady=4
                ).pack(anchor="w", pady=(10, 0))
                tk.Label(
                    window, text=message, bg="#171717", fg="white",
                    font=("Segoe UI", 10), padx=18, pady=4
                ).pack(anchor="w")
                window.update_idletasks()
                x = root.winfo_screenwidth() - window.winfo_reqwidth() - 24
                y = root.winfo_screenheight() - window.winfo_reqheight() - 60
                window.geometry(f"+{x}+{y}")
                current["window"] = window
                current["after_id"] = root.after(
                    NOTIFICATION_SECONDS, close_current
                )
            root.after(25, poll)

        root.after(25, poll)
        root.mainloop()

profile = load_profile()
known_names = []
known_encodings = []
if profile is not None:
    for encoding in profile["encodings"]:
        known_names.append(profile["name"])
        known_encodings.append(np.asarray(encoding, dtype=float))
    print(f"Loaded {len(known_encodings)} samples for: {profile['name']}")
else:
    print("DATHEM profile not found. Run DathemAgentV1Setup.exe first.")


def lock_windows(cam):
    """Shows the lock screen and blocks until unlocked. If the correct
    password was entered, returns the face encoding captured at that
    moment so the caller can grant this person session-level trust.
    Also reports whether the surveillance camera handle can be reused."""
    print(">>> TRIGGERING LOCK SCREEN <<<")
    screen = LockScreen(
        known_encodings=known_encodings,
        tolerance=TOLERANCE,
        password_verifier=lambda candidate: verify_password(candidate, profile),
        unlock_camera=cam,
    )
    return screen.captured_encoding, screen.reuse_unlock_camera


def analyze_frame(frame):
    analysis_started = time.perf_counter()
    # Face detection and encoding dominate CPU time. Processing half-size
    # frames cuts the pixel work substantially while retaining enough detail
    # for ordinary webcam distances.
    if ANALYSIS_SCALE != 1.0:
        frame = cv2.resize(
            frame, None, fx=ANALYSIS_SCALE, fy=ANALYSIS_SCALE,
            interpolation=cv2.INTER_AREA,
        )
    rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    detection_started = time.perf_counter()
    locations = face_recognition.face_locations(
        rgb, number_of_times_to_upsample=0, model="hog"
    )
    detection_ms = (time.perf_counter() - detection_started) * 1000
    encoding_started = time.perf_counter()
    encodings = face_recognition.face_encodings(rgb, locations, num_jitters=1)
    encoding_ms = (time.perf_counter() - encoding_started) * 1000

    total = len(encodings)
    unknown_count = 0
    names_seen = []
    comparison_started = time.perf_counter()

    for enc in encodings:
        distances = face_recognition.face_distance(known_encodings, enc)
        best_distance = np.min(distances) if len(distances) > 0 else 999

        if best_distance <= TOLERANCE:
            best_idx = int(np.argmin(distances))
            names_seen.append(known_names[best_idx])
        else:
            unknown_count += 1
            names_seen.append("unknown")

    metrics = {
        "detect_ms": detection_ms,
        "encode_ms": encoding_ms,
        "compare_ms": (time.perf_counter() - comparison_started) * 1000,
        "total_ms": (time.perf_counter() - analysis_started) * 1000,
    }
    return total, unknown_count, names_seen, metrics


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


def open_camera():
    cam = cv2.VideoCapture(0)
    cam.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
    cam.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
    cam.set(cv2.CAP_PROP_BUFFERSIZE, 1)
    return cam


def trigger_lock(cam):
    """Temporarily transfers the camera handle to the lock screen.

    The surveillance loop is blocked here, so the lock-screen worker can use
    the existing camera sequentially. Reopen the device only if its driver
    cannot return the shared handle safely.
    """
    captured, camera_reusable = lock_windows(cam)
    grant_session_trust(captured)

    if camera_reusable and cam.isOpened():
        print(">>> Camera handle returned to surveillance loop <<<")
        return cam

    print(">>> Reopening camera after lock-screen camera handoff fallback...")
    new_cam = open_camera()
    if not new_cam.isOpened():
        print("WARNING: Could not reopen camera after unlock. "
              "Guard will keep retrying.")
    return new_cam


def main():
    if profile is None:
        root = tk.Tk()
        root.withdraw()
        messagebox.showerror(
            "DATHEM Agent V1 non configuré",
            "Lancez DathemAgentV1Setup.exe et enregistrez le profil de l'utilisateur avant de démarrer le service.",
            parent=root,
        )
        root.destroy()
        return

    # Ask the webcam for a modest frame size. Some drivers ignore these hints;
    # the half-size analysis above still limits recognition work in that case.
    cam = open_camera()
    # Avoid processing frames queued while face recognition is busy; the next
    # analysis should use the most recent image available from the camera.
    cam.set(cv2.CAP_PROP_BUFFERSIZE, 1)
    if not cam.isOpened():
        print("ERROR: Could not open camera")
        return

    print("Guard running. Press Ctrl+C to stop.\n")

    notifier = CompanionNotifier()
    companion_present = False
    absence_start = None
    last_lock_time = 0
    last_status = None
    last_status_log_time = 0.0
    last_analysis_timing_log = 0.0

    def report_status(status, now):
        nonlocal last_status, last_status_log_time
        if status != last_status or now - last_status_log_time >= STATUS_LOG_INTERVAL:
            print(f"[{time.strftime('%H:%M:%S')}] {status}")
            last_status = status
            last_status_log_time = now

    try:
        while True:
            ret, frame = cam.read()
            if not ret:
                time.sleep(READ_ERROR_RETRY)
                continue

            total, unknown_count, names_seen, analysis_metrics = analyze_frame(frame)
            now = time.time()

            if total == 0:
                companion_present = False
                if absence_start is None:
                    absence_start = now
                elapsed = now - absence_start
                report_status("No one detected", now)
                if elapsed >= ABSENCE_LOCK_AFTER and (now - last_lock_time) > LOCK_COOLDOWN:
                    cam = trigger_lock(cam)
                    last_lock_time = time.time()
                    absence_start = None

            else:
                absence_start = None
                has_unknown = unknown_count > 0
                has_known = any(name != "unknown" for name in names_seen)

                if has_unknown and has_known:
                    if not companion_present:
                        notifier.show("Une autre personne est détectée devant votre PC.")
                        report_status(
                            f"Faces: {names_seen} -> known and unknown together; notification only",
                            now,
                        )
                    companion_present = True
                elif has_unknown:
                    companion_present = False
                    if now - last_analysis_timing_log >= 5:
                        print(
                            "PERF face analysis before unknown lock: "
                            f"detect={analysis_metrics['detect_ms']:.0f} ms, "
                            f"encode={analysis_metrics['encode_ms']:.0f} ms, "
                            f"compare={analysis_metrics['compare_ms']:.0f} ms, "
                            f"total={analysis_metrics['total_ms']:.0f} ms"
                        )
                        last_analysis_timing_log = now
                    report_status(f"Faces: {names_seen} -> unknown present; locking immediately", now)
                    if (now - last_lock_time) > LOCK_COOLDOWN:
                        cam = trigger_lock(cam)
                        last_lock_time = time.time()
                else:
                    companion_present = False
                    report_status(f"Faces: {names_seen} -> OK", now)

    except KeyboardInterrupt:
        print("\nStopped by user.")
    finally:
        cam.release()


if __name__ == "__main__":
    main()
