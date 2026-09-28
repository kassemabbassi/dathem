"""Interactive first-run setup with a live camera preview and guided capture."""

import tkinter as tk
from tkinter import messagebox, ttk

import cv2
import face_recognition
import numpy as np
from PIL import Image, ImageTk

from dathem_config import make_password_record, save_profile


SAMPLES_NEEDED = 8
PREVIEW_WIDTH = 640
PREVIEW_HEIGHT = 400


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

        self.current_rgb = None
        self.current_locations = []
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

        self.root.after(100, self.update_preview)

    def update_preview(self):
        if not self.root.winfo_exists() or not self.camera.isOpened():
            return

        ok, frame = self.camera.read()
        if ok:
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            locations = face_recognition.face_locations(rgb, model="hog")
            preview_frame = rgb.copy()
            for top, right, bottom, left in locations:
                color = (40, 220, 80) if len(locations) == 1 else (240, 55, 55)
                cv2.rectangle(preview_frame, (left, top), (right, bottom), color, 3)

            self.current_rgb = rgb
            self.current_locations = locations
            image = Image.fromarray(preview_frame)
            image.thumbnail((PREVIEW_WIDTH, PREVIEW_HEIGHT), Image.Resampling.LANCZOS)
            self.photo = ImageTk.PhotoImage(image, master=self.root)
            self.preview.configure(image=self.photo, text="")

            if len(locations) == 1:
                self.status_var.set(
                    f"Visage détecté. Captures : {len(self.encodings)}/{SAMPLES_NEEDED}. "
                    "Changez légèrement l'angle entre les captures."
                )
            elif len(locations) > 1:
                self.status_var.set("Plusieurs visages détectés : restez seul dans le cadre.")
            else:
                self.status_var.set("Aucun visage détecté : rapprochez-vous et regardez la caméra.")

        self.root.after(100, self.update_preview)

    def capture_sample(self):
        if self.current_rgb is None or len(self.current_locations) != 1:
            self.status_var.set("Capture refusée : il faut exactement un visage dans le cadre.")
            return

        found = face_recognition.face_encodings(
            self.current_rgb, self.current_locations
        )
        if not found:
            self.status_var.set("Visage détecté, mais capture impossible. Réessayez.")
            return

        self.encodings.append(np.asarray(found[0], dtype=float).tolist())
        self.status_var.set(
            f"Capture {len(self.encodings)}/{SAMPLES_NEEDED} enregistrée. "
            "Changez légèrement l'angle puis capturez à nouveau."
        )
        if len(self.encodings) >= SAMPLES_NEEDED:
            self.capture_button.configure(state="disabled")
            self.save_button.configure(state="normal")

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
        if getattr(self, "camera", None) is not None:
            self.camera.release()
        if self.root.winfo_exists():
            self.root.destroy()


def main():
    root = tk.Tk()
    SetupWindow(root)
    root.mainloop()


if __name__ == "__main__":
    main()
