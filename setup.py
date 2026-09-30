"""Interactive first-run setup with a responsive camera preview and guided capture."""

import queue
import threading
import time
import tkinter as tk
from tkinter import messagebox, ttk

import cv2
import face_recognition
import numpy as np
from PIL import Image, ImageTk

from dathem_config import make_password_record, save_profile


SAMPLES_NEEDED = 8
CAMERA_WIDTH = 640
CAMERA_HEIGHT = 480
PREVIEW_WIDTH = 640
PREVIEW_HEIGHT = 400
PREVIEW_INTERVAL_MS = 33
PREVIEW_DETECTION_INTERVAL_SECONDS = 0.12
PREVIEW_ANALYSIS_SCALE = 0.5


class SetupWindow:
    def __init__(self, root):
        self.root = root
        self.root.title("DATHEM Agent V1 — première configuration")
        self.root.resizable(False, False)
        self.root.protocol("WM_DELETE_WINDOW", self.close)

        self.camera = cv2.VideoCapture(0)
        if not self.camera.isOpened():
            self.camera.release()
            messagebox.showerror(
                "Caméra indisponible",
                "DATHEM ne peut pas ouvrir la caméra. Vérifiez qu'elle est branchée "
                "et autorisée dans les paramètres de confidentialité de Windows.",
                parent=root,
            )
            root.destroy()
            return

        # Ask the webcam for a moderate size. Some drivers ignore these hints;
        # the preview and full-resolution capture paths handle the actual size.
        self.camera.set(cv2.CAP_PROP_FRAME_WIDTH, CAMERA_WIDTH)
        self.camera.set(cv2.CAP_PROP_FRAME_HEIGHT, CAMERA_HEIGHT)
        self.camera.set(cv2.CAP_PROP_BUFFERSIZE, 1)

        self.stop_event = threading.Event()
        self.frame_lock = threading.Lock()
        self.latest_frame = None
        self.latest_frame_sequence = 0
        self.latest_detection_frame = None
        self.latest_locations = ()
        self.latest_detection_count = None
        self.latest_detection_time = 0.0
        self.last_guidance_count = None
        self.capture_results = queue.Queue()
        self.capture_in_progress = False
        self.encodings = []
        self.photo = None

        container = ttk.Frame(root, padding=14)
        container.grid(row=0, column=0, sticky="nsew")

        self.preview = ttk.Label(container, text="Ouverture de la caméra…")
        self.preview.grid(row=0, column=0, rowspan=9, padx=(0, 18), sticky="n")

        ttk.Label(container, text="Nom de l'utilisateur").grid(row=0, column=1, sticky="w")
        self.name_var = tk.StringVar()
        ttk.Entry(container, textvariable=self.name_var, width=34).grid(
            row=1, column=1, sticky="ew", pady=(2, 10)
        )

        ttk.Label(container, text="Choisissez un mot de passe (8 caractères minimum)").grid(
            row=2, column=1, sticky="w"
        )
        self.password_var = tk.StringVar()
        ttk.Entry(container, textvariable=self.password_var, show="•", width=34).grid(
            row=3, column=1, sticky="ew", pady=(2, 10)
        )

        ttk.Label(container, text="Confirmez le mot de passe").grid(
            row=4, column=1, sticky="w"
        )
        self.confirm_var = tk.StringVar()
        ttk.Entry(container, textvariable=self.confirm_var, show="•", width=34).grid(
            row=5, column=1, sticky="ew", pady=(2, 10)
        )

        ttk.Label(
            container,
            text=(
                "Placez-vous seul devant la caméra. Attendez le cadre vert, puis "
                "cliquez sur « Capturer ». Faites 8 captures en changeant légèrement "
                "l'angle du visage. DATHEM enregistre des encodages, pas les photos."
            ),
            wraplength=300,
            justify="left",
        ).grid(row=6, column=1, sticky="w", pady=(0, 10))

        self.status_var = tk.StringVar(value="Recherche d'un seul visage…")
        ttk.Label(container, textvariable=self.status_var, wraplength=300).grid(
            row=7, column=1, sticky="w", pady=(0, 8)
        )

        actions = ttk.Frame(container)
        actions.grid(row=8, column=1, sticky="ew")
        self.capture_button = ttk.Button(
            actions, text="Capturer", command=self.capture_sample
        )
        self.capture_button.pack(side="left")
        self.save_button = ttk.Button(
            actions, text="Enregistrer le profil", command=self.save, state="disabled"
        )
        self.save_button.pack(side="left", padx=(8, 0))

        self.capture_thread = threading.Thread(
            target=self._camera_reader, name="DathemSetupCamera", daemon=True
        )
        self.detection_thread = threading.Thread(
            target=self._preview_detector, name="DathemSetupPreviewDetector", daemon=True
        )
        self.capture_thread.start()
        self.detection_thread.start()
        self.root.after(0, self.update_preview)

    def _camera_reader(self):
        """Continuously keep the newest camera frame without touching Tk."""
        while not self.stop_event.is_set():
            try:
                ok, frame = self.camera.read()
            except cv2.error:
                ok, frame = False, None

            if not ok or frame is None:
                self.stop_event.wait(0.02)
                continue

            with self.frame_lock:
                self.latest_frame = frame
                self.latest_frame_sequence += 1

    def _preview_detector(self):
        """Run lightweight preview detection periodically, outside the UI loop."""
        last_sequence = -1
        next_detection = 0.0

        while not self.stop_event.is_set():
            now = time.monotonic()
            if now < next_detection:
                self.stop_event.wait(min(0.02, next_detection - now))
                continue

            with self.frame_lock:
                frame = self.latest_frame
                sequence = self.latest_frame_sequence

            if frame is None or sequence == last_sequence:
                self.stop_event.wait(0.01)
                continue

            last_sequence = sequence
            try:
                small = cv2.resize(
                    frame,
                    None,
                    fx=PREVIEW_ANALYSIS_SCALE,
                    fy=PREVIEW_ANALYSIS_SCALE,
                    interpolation=cv2.INTER_AREA,
                )
                small_rgb = cv2.cvtColor(small, cv2.COLOR_BGR2RGB)
                small_locations = face_recognition.face_locations(
                    small_rgb,
                    number_of_times_to_upsample=0,
                    model="hog",
                )
                scale_y = frame.shape[0] / small.shape[0]
                scale_x = frame.shape[1] / small.shape[1]
                locations = tuple(
                    (
                        round(top * scale_y),
                        round(right * scale_x),
                        round(bottom * scale_y),
                        round(left * scale_x),
                    )
                    for top, right, bottom, left in small_locations
                )
                with self.frame_lock:
                    # Keep the exact source frame used for these coordinates.
                    # Enrollment can then encode this sample without running a
                    # second, full-resolution face-detection pass after the click.
                    self.latest_detection_frame = frame
                    self.latest_locations = locations
                    self.latest_detection_count = len(locations)
                    self.latest_detection_time = time.monotonic()
            except Exception:
                # Keep the live preview available even if a detection frame fails.
                pass

            next_detection = time.monotonic() + PREVIEW_DETECTION_INTERVAL_SECONDS

    def update_preview(self):
        if self.stop_event.is_set() or not self.root.winfo_exists():
            return

        with self.frame_lock:
            frame = None if self.latest_frame is None else self.latest_frame.copy()
            locations = self.latest_locations
            detection_count = self.latest_detection_count

        if frame is not None:
            color = (40, 220, 80) if detection_count == 1 else (40, 60, 240)
            for top, right, bottom, left in locations:
                cv2.rectangle(frame, (left, top), (right, bottom), color, 3)

            height, width = frame.shape[:2]
            scale = min(PREVIEW_WIDTH / width, PREVIEW_HEIGHT / height)
            display_size = (max(1, round(width * scale)), max(1, round(height * scale)))
            preview_bgr = cv2.resize(frame, display_size, interpolation=cv2.INTER_AREA)
            preview_rgb = cv2.cvtColor(preview_bgr, cv2.COLOR_BGR2RGB)
            image = Image.fromarray(preview_rgb)
            self.photo = ImageTk.PhotoImage(image, master=self.root)
            self.preview.configure(image=self.photo, text="")

        if not self.capture_in_progress and detection_count != self.last_guidance_count:
            self.last_guidance_count = detection_count
            if detection_count == 1:
                self.status_var.set(
                    f"Visage détecté. Captures : {len(self.encodings)}/{SAMPLES_NEEDED}. "
                    "Changez légèrement l'angle entre les captures."
                )
            elif detection_count is not None and detection_count > 1:
                self.status_var.set("Plusieurs visages détectés : restez seul dans le cadre.")
            elif detection_count == 0:
                self.status_var.set(
                    "Aucun visage détecté : rapprochez-vous et regardez la caméra."
                )

        self._poll_capture_result()
        if not self.stop_event.is_set():
            self.root.after(PREVIEW_INTERVAL_MS, self.update_preview)

    def capture_sample(self):
        with self.frame_lock:
            frame = (
                None if self.latest_detection_frame is None
                else self.latest_detection_frame.copy()
            )
            locations = self.latest_locations
            count = self.latest_detection_count
            detection_age = time.monotonic() - self.latest_detection_time

        if frame is None:
            self.status_var.set("La caméra n'a pas encore fourni d'image. Réessayez.")
            return
        if count != 1 or detection_age > 1.0:
            self.status_var.set(
                "Capture refusée : attendez le cadre vert avec un seul visage."
            )
            return

        self.capture_in_progress = True
        self.capture_button.configure(state="disabled")
        self.status_var.set("Analyse de la capture… l'aperçu reste actif.")
        requested_at = time.perf_counter()
        threading.Thread(
            target=self._encode_capture,
            args=(frame, locations, requested_at),
            name="DathemSetupCaptureEncoder",
            daemon=True,
        ).start()

    def _encode_capture(self, frame, locations, requested_at):
        """Encode the detected full-resolution sample away from Tk."""
        try:
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            if len(locations) != 1:
                self.capture_results.put(
                    (False, "Capture refusée : il faut exactement un visage net dans le cadre.")
                )
                return

            found = face_recognition.face_encodings(rgb, locations, num_jitters=1)
            if not found:
                self.capture_results.put(
                    (False, "Visage détecté, mais capture impossible. Améliorez la lumière puis réessayez.")
                )
                return

            encoding = np.asarray(found[0], dtype=float).tolist()
            elapsed_ms = (time.perf_counter() - requested_at) * 1000
            self.capture_results.put((True, (encoding, elapsed_ms)))
        except Exception:
            self.capture_results.put(
                (False, "Erreur pendant l'analyse. Réessayez avec le visage bien éclairé.")
            )

    def _poll_capture_result(self):
        try:
            succeeded, result = self.capture_results.get_nowait()
        except queue.Empty:
            return

        self.capture_in_progress = False
        if succeeded:
            encoding, elapsed_ms = result
            self.encodings.append(encoding)
            self.status_var.set(
                f"Capture {len(self.encodings)}/{SAMPLES_NEEDED} enregistrée "
                f"({elapsed_ms:.0f} ms). "
                "Changez légèrement l'angle puis capturez à nouveau."
            )
            if len(self.encodings) >= SAMPLES_NEEDED:
                self.capture_button.configure(state="disabled")
                self.save_button.configure(state="normal")
            else:
                self.capture_button.configure(state="normal")
        else:
            self.status_var.set(result)
            self.capture_button.configure(state="normal")

    def save(self):
        name = self.name_var.get().strip()
        password = self.password_var.get().strip()
        confirmation = self.confirm_var.get().strip()

        if not name:
            messagebox.showwarning("Nom requis", "Saisissez le nom de l'utilisateur.", parent=self.root)
            return
        if len(password) < 8:
            messagebox.showwarning(
                "Mot de passe trop court",
                "Choisissez au moins 8 caractères.",
                parent=self.root,
            )
            return
        if password != confirmation:
            messagebox.showwarning(
                "Confirmation incorrecte",
                "Les deux mots de passe ne correspondent pas.",
                parent=self.root,
            )
            return
        if len(self.encodings) < SAMPLES_NEEDED:
            messagebox.showwarning(
                "Captures manquantes",
                f"Prenez les {SAMPLES_NEEDED} captures demandées.",
                parent=self.root,
            )
            return

        profile = {
            "version": 1,
            "name": name,
            "encodings": self.encodings,
            **make_password_record(password),
        }
        try:
            saved_path = save_profile(profile)
        except OSError as exc:
            messagebox.showerror(
                "Enregistrement impossible", str(exc), parent=self.root
            )
            return

        messagebox.showinfo(
            "Configuration terminée",
            "Le profil DATHEM a été enregistré sur ce PC. "
            "Les captures de la caméra n'ont pas été conservées. "
            f"Emplacement : {saved_path}",
            parent=self.root,
        )
        self.close()

    def close(self):
        if not self.stop_event.is_set():
            self.stop_event.set()
        camera = getattr(self, "camera", None)
        if camera is not None:
            try:
                camera.release()
            except cv2.error:
                pass
        if self.root.winfo_exists():
            self.root.destroy()


def main():
    root = tk.Tk()
    SetupWindow(root)
    root.mainloop()


if __name__ == "__main__":
    main()
