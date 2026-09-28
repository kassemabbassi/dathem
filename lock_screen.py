import tkinter as tk
import random
import math
import os
import queue
import threading
import time
import cv2
import face_recognition
import numpy as np
from PIL import Image, ImageTk

EYES_IMAGE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "eyes.jpg")


class LockScreen:
    def __init__(self, known_encodings=None, tolerance=0.5, password_verifier=None):
        init_started = time.perf_counter()
        self.root = tk.Tk()
        # There is a separate Tk root for desktop notifications. Bind every
        # Tk variable to this window's interpreter explicitly.
        self.known_encodings = list(known_encodings or [])
        self.tolerance = tolerance
        self.password_verifier = password_verifier
        self.unlock_cam = None
        self._face_stop = threading.Event()
        self._face_results = queue.Queue(maxsize=1)
        self._face_state_lock = threading.Lock()
        self._last_face_encoding = None
        self._face_worker = None
        self.width = self.root.winfo_screenwidth()
        self.height = self.root.winfo_screenheight()

        self.root.geometry(f"{self.width}x{self.height}+0+0")
        self.root.overrideredirect(True)  # removes title bar/borders entirely
        self.root.attributes('-topmost', True)
        self.root.configure(bg='black')
        self.root.protocol("WM_DELETE_WINDOW", self.block_close)
        self.root.bind("<Alt-F4>", lambda e: "break")
        self.root.bind("<Escape>", lambda e: "break")
        self.root.focus_force()

        self.captured_encoding = None

        self.canvas = tk.Canvas(self.root, width=self.width, height=self.height,
                                 bg='black', highlightthickness=0)
        self.canvas.pack(fill='both', expand=True)
        self._transition_items = [
            self.canvas.create_text(
                self.width // 2, int(self.height * 0.43),
                text="DATHEM — ACCÈS BLOQUÉ",
                font=("Segoe UI", 38, "bold"), fill="#FF1A1A",
            ),
            self.canvas.create_text(
                self.width // 2, int(self.height * 0.50),
                text="PRÉSENCE NON AUTORISÉE DÉTECTÉE",
                font=("Consolas", 18, "bold"), fill="#D62828",
            ),
        ]
        # Paint the full-screen lock surface before loading large images and
        # building decorative canvas items, so the lock appears immediately.
        self.root.update_idletasks()
        self.root.update()
        print(
            f"PERF lock surface displayed: "
            f"{(time.perf_counter() - init_started) * 1000:.0f} ms"
        )

        # --- Eyes background: cover the whole screen with one cached image ---
        self.bg_image = self.load_eyes_background()
        if self.bg_image:
            self.bg_image_id = self.canvas.create_image(
                0, 0, image=self.bg_image, anchor="nw"
            )
            self.canvas.tag_lower(self.bg_image_id)
        else:
            self.bg_image_id = None

        # A soft dark overlay so text stays readable over the image
        self.overlay_id = self.canvas.create_rectangle(
            0, 0, self.width, self.height, fill="#000000", outline="", stipple="gray25"
        )

        # --- Static cracked-glass / blood-spatter overlay (drawn once, on top) ---
        self.draw_cracks(count=30)
        self.draw_splatters(count=16)

        # --- Title, positioned near the top so it never overlaps the eyes ---
        self.title_base_x = self.width // 2
        self.title_base_y = int(self.height * 0.11)

        self.glow_ids = []
        glow_colors = ["#1a0000", "#2a0000", "#3a0000", "#4a0000"]
        for i, gcol in enumerate(glow_colors):
            pad = 90 - i * 18
            gid = self.canvas.create_oval(
                self.title_base_x - 260 - pad, self.title_base_y - 45 - pad // 2,
                self.title_base_x + 260 + pad, self.title_base_y + 45 + pad // 2,
                fill=gcol, outline=""
            )
            self.glow_ids.append(gid)

        self.title_id = self.canvas.create_text(
            self.title_base_x, self.title_base_y,
            text="DATHEM CAPTURES YOU",
            font=("Impact", 56, "bold"),
            fill="#FF0000"
        )
        self.title_ghost_id = self.canvas.create_text(
            self.title_base_x + 3, self.title_base_y + 2,
            text="DATHEM CAPTURES YOU",
            font=("Impact", 56, "bold"),
            fill="#3a0000"
        )
        self.canvas.tag_raise(self.title_id, self.title_ghost_id)

        self.title_drips = self.attach_drips_below_text(
            self.title_base_x, self.title_base_y + 34, width=540, count=14
        )

        self.subtitle_id = self.canvas.create_text(
            self.width // 2, self.title_base_y + 92,
            text="UNAUTHORIZED PRESENCE DETECTED",
            font=("Consolas", 16, "bold"),
            fill="#D62828"
        )

        # --- Flickering static noise specks over the whole screen ---
        self.static_ids = []
        for _ in range(24):
            x = random.randint(0, self.width)
            y = random.randint(0, self.height)
            s = random.randint(1, 3)
            sid = self.canvas.create_rectangle(x, y, x + s, y + s, fill="#2a0000", outline="")
            self.static_ids.append(sid)

        # --- Password field, positioned low so the eyes stay fully visible above it ---
        self.pw_var = tk.StringVar(master=self.root)
        self.entry = tk.Entry(
            self.root, textvariable=self.pw_var,
            show="", font=("Consolas", 22),
            bg="black", fg="red", insertbackground="red",
            relief="flat", justify="center", width=20,
            highlightthickness=2, highlightbackground="#8B0000", highlightcolor="#FF0000"
        )
        self.entry_y = int(self.height * 0.80)
        self.entry_window = self.canvas.create_window(self.width // 2, self.entry_y, window=self.entry)
        self.entry.bind("<Return>", self.check_password)
        self.entry.bind("<KeyPress>", self.on_password_keypress)
        self.entry.focus_set()

        self.hint_id = self.canvas.create_text(
            self.width // 2, self.entry_y + 38,
            text="Enter password and press Enter",
            font=("Consolas", 11),
            fill="#666666"
        )
        self.canvas.itemconfigure(self.entry_window, state="hidden")
        self.canvas.itemconfigure(self.hint_id, state="hidden")
        self.start_memory_game()

        # --- Falling blood-rain across the whole screen ---
        self.rain = []
        rain_colors = ["#6B0000", "#8B0000", "#A80000", "#5C0000"]
        for _ in range(36):
            x = random.randint(0, self.width)
            y = random.randint(-self.height, 0)
            length = random.randint(12, 60)
            speed = random.uniform(3, 10)
            col = random.choice(rain_colors)
            rid = self.canvas.create_line(x, y, x, y + length, fill=col, width=random.choice([1, 2, 2, 3]))
            self.rain.append([rid, x, y, length, speed])

        # --- Pulsing vignette border ---
        self.border_id = self.canvas.create_rectangle(
            4, 4, self.width - 4, self.height - 4, outline="#8B0000", width=6
        )
        self.border_inner_id = self.canvas.create_rectangle(
            14, 14, self.width - 14, self.height - 14, outline="#3a0000", width=2
        )

        self.flicker_state = 0
        self.pulse_dir = 1
        self.pulse_width = 6
        self.animate()

        self.root.after(100, self.refocus)
        for item_id in self._transition_items:
            self.canvas.delete(item_id)
        if self.known_encodings:
            self._face_worker = threading.Thread(
                target=self._face_recognition_worker, daemon=True
            )
            self._face_worker.start()
            self.root.after(40, self.poll_authorized_face)
        elif self.known_encodings:
            print("WARNING: Camera unavailable for automatic face unlock.")
        print(
            f"PERF lock-screen content ready: "
            f"{(time.perf_counter() - init_started) * 1000:.0f} ms"
        )
        self.root.mainloop()
        self.stop_face_worker()

    # ---------- background image ----------

    def load_eyes_background(self):
        if not os.path.exists(EYES_IMAGE_PATH):
            print(f"WARNING: {EYES_IMAGE_PATH} not found - running without eyes background.")
            return []

        img = Image.open(EYES_IMAGE_PATH).convert("RGB")

        # Cover-fit: scale so the image fully covers the screen, then center-crop
        img_ratio = img.width / img.height
        screen_ratio = self.width / self.height

        if img_ratio > screen_ratio:
            new_height = self.height
            new_width = int(new_height * img_ratio)
        else:
            new_width = self.width
            new_height = int(new_width / img_ratio)

        img = img.resize((new_width, new_height), Image.LANCZOS)

        left = (new_width - self.width) // 2
        top = (new_height - self.height) // 2
        img = img.crop((left, top, left + self.width, top + self.height))

        # Keep one screen-sized image. Creating several full-resolution
        # brightness variants delayed lock display and consumed substantial RAM.
        return ImageTk.PhotoImage(img, master=self.root)

    # ---------- static decoration builders ----------

    def draw_cracks(self, count):
        for _ in range(count):
            x, y = random.randint(0, self.width), random.randint(0, self.height)
            points = [(x, y)]
            for _ in range(random.randint(3, 6)):
                x += random.randint(-60, 60)
                y += random.randint(-60, 60)
                points.append((x, y))
            flat = [c for p in points for c in p]
            self.canvas.create_line(*flat, fill="#2a0000", width=1)

    def draw_splatters(self, count):
        for _ in range(count):
            cx, cy = random.randint(0, self.width), random.randint(0, self.height)
            for _ in range(random.randint(4, 9)):
                r = random.randint(3, 14)
                ox = cx + random.randint(-40, 40)
                oy = cy + random.randint(-40, 40)
                self.canvas.create_oval(ox - r, oy - r, ox + r, oy + r, fill="#5c0000", outline="")

    def attach_drips_below_text(self, cx, top_y, width, count):
        drips = []
        for _ in range(count):
            x = cx + random.randint(-width // 2, width // 2)
            length = random.randint(15, 55)
            speed = random.uniform(1.5, 4)
            did = self.canvas.create_line(x, top_y, x, top_y + length, fill="#8B0000", width=2)
            drips.append([did, x, top_y, length, speed])
        return drips

    # ---------- window behavior ----------

    def block_close(self):
        pass

    def refocus(self):
        if self.password_ready:
            self.focus_password()
        self.root.after(500, self.refocus)

    def focus_password(self):
        if self.password_ready and self.entry.winfo_exists():
            self.entry.focus_force()

    # ---------- sequence challenge ----------

    def start_memory_game(self):
        """Run a short, escalating sequence game before password entry."""
        self.password_ready = False
        self.game_symbols = ["▲", "●", "■", "◆"]
        self.game_sequence = []
        self.game_round = 0
        self.game_rounds = 5
        self.game_input = []
        self.game_locked = True
        self.game_status = self.canvas.create_text(
            self.width // 2, int(self.height * 0.57),
            text="MEMORY CHALLENGE · 0 / 5",
            font=("Consolas", 20, "bold"), fill="#FF4444"
        )
        self.game_prompt = self.canvas.create_text(
            self.width // 2, int(self.height * 0.62),
            text="Watch the sequence, then repeat it",
            font=("Consolas", 14), fill="#DDDDDD"
        )
        self.game_display = self.canvas.create_text(
            self.width // 2, int(self.height * 0.68),
            text="",
            font=("Consolas", 27, "bold"), fill="#FF1A1A"
        )
        self.game_buttons = []
        spacing = 92
        start_x = self.width // 2 - (len(self.game_symbols) - 1) * spacing // 2
        for index, symbol in enumerate(self.game_symbols):
            button = tk.Button(
                self.root, text=symbol, font=("Segoe UI Symbol", 25, "bold"),
                fg="#FF4444", bg="#160000", activeforeground="white",
                activebackground="#8B0000", relief="flat", width=3,
                command=lambda value=symbol: self.game_guess(value)
            )
            window_id = self.canvas.create_window(
                start_x + index * spacing, int(self.height * 0.76), window=button
            )
            self.game_buttons.append((button, window_id))
        self.next_game_round()

    def next_game_round(self):
        if self.game_round >= self.game_rounds:
            self.finish_memory_game()
            return
        self.game_round += 1
        self.game_sequence.append(random.choice(self.game_symbols))
        self.game_input = []
        self.game_locked = True
        self.canvas.itemconfigure(
            self.game_status, text=f"MEMORY CHALLENGE · {self.game_round} / {self.game_rounds}"
        )
        self.canvas.itemconfigure(self.game_prompt, text="Watch carefully…")
        self.show_sequence(0)

    def show_sequence(self, index):
        if index >= len(self.game_sequence):
            self.canvas.itemconfigure(self.game_display, text="")
            self.canvas.itemconfigure(self.game_prompt, text="Repeat the sequence with the buttons")
            self.game_locked = False
            return
        self.canvas.itemconfigure(self.game_display, text=self.game_sequence[index])
        self.root.after(520, lambda: self.canvas.itemconfigure(self.game_display, text=""))
        self.root.after(760, lambda: self.show_sequence(index + 1))

    def game_guess(self, symbol):
        if self.game_locked:
            return
        index = len(self.game_input)
        if index >= len(self.game_sequence):
            return
        if symbol != self.game_sequence[index]:
            self.game_locked = True
            self.canvas.itemconfigure(self.game_prompt, text="Wrong sequence · try this round again")
            self.flash_wrong()
            self.root.after(900, self.replay_game_round)
            return
        self.game_input.append(symbol)
        self.canvas.itemconfigure(self.game_display, text="● " * len(self.game_input))
        if len(self.game_input) == len(self.game_sequence):
            self.game_locked = True
            self.canvas.itemconfigure(self.game_prompt, text="Correct · next round")
            self.root.after(650, self.next_game_round)

    def replay_game_round(self):
        # A replay starts from the first symbol. Keeping the previous partial
        # input made the next click compare against the wrong sequence index.
        self.game_input = []
        self.canvas.itemconfigure(self.game_prompt, text="Watch carefully…")
        self.show_sequence(0)

    def finish_memory_game(self):
        self.canvas.itemconfigure(self.game_status, text="CHALLENGE COMPLETE")
        self.canvas.itemconfigure(self.game_prompt, text="Enter password and press Enter")
        self.canvas.itemconfigure(self.game_display, text="")
        for button, window_id in self.game_buttons:
            button.destroy()
            self.canvas.delete(window_id)
        self.password_ready = True
        self.canvas.itemconfigure(self.entry_window, state="normal")
        self.canvas.itemconfigure(self.hint_id, state="normal")
        self.canvas.itemconfigure(self.game_status, state="hidden")
        self.canvas.itemconfigure(self.game_prompt, state="hidden")
        self.canvas.itemconfigure(self.game_display, state="hidden")
        self.root.after_idle(self.focus_password)
        self.root.after(150, self.focus_password)

    def on_password_keypress(self, event):
        """Flash a small blood effect near the password field for each key."""
        # Let Tk handle editing/navigation keys normally, but animate only
        # characters that can contribute to the password.
        if event.char and event.char.isprintable():
            self.blood_key_effect()

    def blood_key_effect(self):
        cx = self.width // 2 + random.randint(-115, 115)
        cy = self.entry_y + random.randint(-17, 17)
        colors = ("#FF1A1A", "#B22222", "#8B0000", "#5C0000")
        ids = []
        for _ in range(random.randint(5, 9)):
            angle = random.uniform(0, 6.283)
            distance = random.randint(5, 25)
            x = cx + int(distance * math.cos(angle))
            y = cy + int(distance * math.sin(angle))
            radius = random.randint(2, 5)
            ids.append(self.canvas.create_oval(
                x - radius, y - radius, x + radius, y + radius,
                fill=random.choice(colors), outline=""
            ))

        def fade(step=0):
            if step >= 5:
                for item_id in ids:
                    self.canvas.delete(item_id)
                return
            for item_id in ids:
                self.canvas.itemconfig(item_id, stipple=("gray50", "gray25", "gray12", "gray50", "gray25")[step])
            self.root.after(45, lambda: fade(step + 1))

        fade()

    # ---------- animation loop ----------

    def animate(self):
        self.flicker_state += 1

        colors = ["#8B0000", "#B22222", "#FF1A1A", "#8B0000", "#5C0000", "#FF0000", "#FF4500"]
        self.canvas.itemconfig(self.title_id, fill=colors[self.flicker_state % len(colors)])

        if random.random() < 0.02:
            self.canvas.itemconfig(self.title_id, fill="#000000")

        if random.random() < 0.10:
            jitter_x = self.title_base_x + random.randint(-8, 8)
            jitter_y = self.title_base_y + random.randint(-4, 4)
            ghost_x = jitter_x + random.randint(-4, 4)
            ghost_y = jitter_y + random.randint(-3, 3)
            self.canvas.coords(self.title_id, jitter_x, jitter_y)
            self.canvas.coords(self.title_ghost_id, ghost_x, ghost_y)
        else:
            self.canvas.coords(self.title_id, self.title_base_x, self.title_base_y)
            self.canvas.coords(self.title_ghost_id, self.title_base_x + 3, self.title_base_y + 2)

        pulse = 1 + 0.05 * ((self.flicker_state % 30) - 15) / 15
        for i, gid in enumerate(self.glow_ids):
            pad = (90 - i * 18) * pulse
            self.canvas.coords(
                gid,
                self.title_base_x - 260 - pad, self.title_base_y - 45 - pad // 2,
                self.title_base_x + 260 + pad, self.title_base_y + 45 + pad // 2,
            )

        for sid in self.static_ids:
            if random.random() < 0.15:
                x0, y0, x1, y1 = self.canvas.coords(sid)
                nx = random.randint(0, self.width)
                ny = random.randint(0, self.height)
                self.canvas.coords(sid, nx, ny, nx + (x1 - x0), ny + (y1 - y0))
                self.canvas.itemconfig(sid, fill=random.choice(["#2a0000", "#4a0000", "#1a1a1a"]))

        for drip in self.title_drips:
            did, x, y, length, speed = drip
            length += speed
            if length > 85:
                length = random.randint(15, 30)
            self.canvas.coords(did, x, y, x, y + length)
            drip[3] = length

        for drop in self.rain:
            did, x, y, length, speed = drop
            y += speed
            if y > self.height:
                y = random.randint(-120, 0)
                x = random.randint(0, self.width)
            self.canvas.coords(did, x, y, x, y + length)
            drop[2] = y

        self.pulse_width += self.pulse_dir * 0.5
        if self.pulse_width > 12 or self.pulse_width < 3:
            self.pulse_dir *= -1
        self.canvas.itemconfig(self.border_id, width=self.pulse_width)
        self.canvas.itemconfig(self.border_inner_id, width=max(1, self.pulse_width / 4))

        self.root.after(55, self.animate)

    # ---------- password check ----------

    def check_password(self, event=None):
        if not self.password_ready:
            return "break"

        entered = self.pw_var.get().strip()
        if self.password_verifier is not None and self.password_verifier(entered):
            # The camera worker continuously keeps the latest observed face;
            # reuse it rather than blocking the UI for another capture pass.
            with self._face_state_lock:
                self.captured_encoding = (
                    self._last_face_encoding.copy()
                    if self._last_face_encoding is not None else None
                )
            self._face_stop.set()
            self.root.destroy()
        else:
            self.flash_wrong()
            self.pw_var.set("")
            self.canvas.itemconfigure(
                self.hint_id, text="Incorrect password. Try again.", fill="#FF4444"
            )
            self.entry.focus_force()
        return "break"

    def release_unlock_camera(self):
        if self.unlock_cam is not None:
            self.unlock_cam.release()
            self.unlock_cam = None

    def _face_recognition_worker(self):
        """Read and recognize camera frames without blocking Tk's event loop."""
        # Opening the camera can block on some Windows drivers. Do it away from
        # Tk so the lock surface remains visible while the device initializes.
        cam = cv2.VideoCapture(0)
        self.unlock_cam = cam
        if cam.isOpened():
            cam.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
            cam.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
            cam.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        else:
            cam.release()
            self.unlock_cam = None
            print("WARNING: Camera unavailable for automatic face unlock.")
            return
        try:
            while cam is not None and not self._face_stop.is_set():
                ret, frame = cam.read()
                if not ret:
                    self._face_stop.wait(0.05)
                    continue

                small = cv2.resize(
                    frame, None, fx=0.5, fy=0.5, interpolation=cv2.INTER_AREA
                )
                rgb = cv2.cvtColor(small, cv2.COLOR_BGR2RGB)
                locations = face_recognition.face_locations(
                    rgb, number_of_times_to_upsample=0, model="hog"
                )
                encodings = face_recognition.face_encodings(
                    rgb, locations, num_jitters=1
                )

                for encoding in encodings:
                    encoding = np.asarray(encoding).copy()
                    with self._face_state_lock:
                        self._last_face_encoding = encoding
                    distances = face_recognition.face_distance(
                        self.known_encodings, encoding
                    )
                    if len(distances) and float(np.min(distances)) <= self.tolerance:
                        try:
                            self._face_results.put_nowait(encoding)
                        except queue.Full:
                            pass
                        return

                # Limit background CPU use while checking often enough for a
                # responsive face unlock. Tk remains free to animate meanwhile.
                self._face_stop.wait(0.15)
        except Exception as exc:
            print(f"WARNING: Face recognition worker failed: {exc}")
        finally:
            if cam is not None:
                cam.release()
            self.unlock_cam = None

    def poll_authorized_face(self):
        """Apply a worker recognition result on Tk's main thread."""
        if not self.root.winfo_exists():
            return
        try:
            encoding = self._face_results.get_nowait()
        except queue.Empty:
            self.root.after(40, self.poll_authorized_face)
            return

        print(">>> Authorized face recognized; unlocking automatically <<<")
        self.captured_encoding = encoding
        self._face_stop.set()
        self.root.destroy()

    def stop_face_worker(self):
        self._face_stop.set()
        worker = self._face_worker
        if worker is not None and worker is not threading.current_thread():
            worker.join(timeout=2.0)
            if worker.is_alive():
                self.release_unlock_camera()
                worker.join(timeout=1.0)
        if worker is None or not worker.is_alive():
            self.release_unlock_camera()

    def flash_wrong(self):
        self.canvas.itemconfig(self.overlay_id, fill="#5a0000")
        self.root.after(150, lambda: self.canvas.itemconfig(self.overlay_id, fill="#000000"))
        self.shake_screen()

    def shake_screen(self, count=6):
        if count <= 0:
            self.root.geometry(f"{self.width}x{self.height}+0+0")
            return
        dx = random.randint(-10, 10)
        dy = random.randint(-8, 8)
        self.root.geometry(f"{self.width}x{self.height}+{dx}+{dy}")
        self.root.after(35, lambda: self.shake_screen(count - 1))


if __name__ == "__main__":
    LockScreen()
