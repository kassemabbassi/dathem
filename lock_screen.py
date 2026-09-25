import tkinter as tk
import random

PASSWORD = "kassem030903"


class LockScreen:
    def __init__(self):
        self.root = tk.Tk()
        self.root.attributes('-fullscreen', True)
        self.root.attributes('-topmost', True)
        self.root.configure(bg='black')
        self.root.protocol("WM_DELETE_WINDOW", self.block_close)
        self.root.bind("<Alt-F4>", lambda e: "break")
        self.root.bind("<Escape>", lambda e: "break")
        self.root.focus_force()

        self.width = self.root.winfo_screenwidth()
        self.height = self.root.winfo_screenheight()

        self.canvas = tk.Canvas(self.root, width=self.width, height=self.height,
                                 bg='black', highlightthickness=0)
        self.canvas.pack(fill='both', expand=True)

        # --- Static cracked-glass / blood-spatter background (drawn once) ---
        self.draw_cracks(count=22)
        self.draw_splatters(count=14)

        # --- Big title, glitch-jittered + flickering, with a drip trail under it ---
        self.title_base_x = self.width // 2
        self.title_base_y = self.height // 4
        self.title_id = self.canvas.create_text(
            self.title_base_x, self.title_base_y,
            text="DATHEM CAPTURES YOU",
            font=("Impact", 58, "bold"),
            fill="#8B0000"
        )
        self.title_drips = self.attach_drips_below_text(
            self.title_base_x, self.title_base_y + 35, width=520, count=10
        )

        self.subtitle_id = self.canvas.create_text(
            self.width // 2, self.title_base_y + 90,
            text="UNAUTHORIZED PRESENCE DETECTED",
            font=("Consolas", 16),
            fill="#B22222"
        )

        # --- Requested line ---
        self.warning_id = self.canvas.create_text(
            self.width // 2, self.title_base_y + 125,
            text="aya sidi ay chtaaml ghadi hani fo9t bik",
            font=("Consolas", 14, "italic"),
            fill="#7A0000"
        )

        # --- Password field: characters replaced by a space -> nothing visible,
        #     only the cursor moves. ---
        self.pw_var = tk.StringVar()
        self.entry = tk.Entry(
            self.root, textvariable=self.pw_var,
            show=" ", font=("Consolas", 22),
            bg="black", fg="red", insertbackground="red",
            relief="flat", justify="center", width=20,
            highlightthickness=2, highlightbackground="#8B0000", highlightcolor="#FF0000"
        )
        self.canvas.create_window(self.width // 2, self.height // 2 + 40, window=self.entry)
        self.entry.bind("<Return>", self.check_password)
        self.entry.focus_set()

        self.hint_id = self.canvas.create_text(
            self.width // 2, self.height // 2 + 80,
            text="Enter password and press Enter",
            font=("Consolas", 11),
            fill="#4a4a4a"
        )

        # --- Falling blood-rain lines across the whole screen ---
        self.rain = []
        for _ in range(45):
            x = random.randint(0, self.width)
            y = random.randint(-self.height, 0)
            length = random.randint(12, 55)
            speed = random.uniform(3, 9)
            rid = self.canvas.create_line(x, y, x, y + length, fill="#6B0000", width=2)
            self.rain.append([rid, x, y, length, speed])

        # --- Blood pool slowly filling the bottom of the screen ---
        self.pool_height = 0
        self.pool_id = self.canvas.create_rectangle(
            0, self.height, self.width, self.height,
            fill="#4a0000", outline=""
        )

        # --- Vignette pulse (glowing red border that breathes like a heartbeat) ---
        self.border_id = self.canvas.create_rectangle(
            4, 4, self.width - 4, self.height - 4,
            outline="#8B0000", width=6
        )

        self.flicker_state = 0
        self.pulse_dir = 1
        self.pulse_width = 6
        self.animate()

        self.root.after(100, self.refocus)
        self.root.mainloop()

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
                self.canvas.create_oval(
                    ox - r, oy - r, ox + r, oy + r,
                    fill="#5c0000", outline=""
                )

    def attach_drips_below_text(self, cx, top_y, width, count):
        drips = []
        for _ in range(count):
            x = cx + random.randint(-width // 2, width // 2)
            length = random.randint(15, 60)
            speed = random.uniform(1.5, 4)
            did = self.canvas.create_line(x, top_y, x, top_y + length, fill="#8B0000", width=2)
            drips.append([did, x, top_y, length, speed])
        return drips

    # ---------- window behavior ----------

    def block_close(self):
        pass  # ignore the window-close (X) request entirely

    def refocus(self):
        self.entry.focus_force()
        self.root.after(500, self.refocus)

    # ---------- animation loop ----------

    def animate(self):
        self.flicker_state += 1

        # Flicker the title through shades of red, with an occasional glitch jump
        colors = ["#8B0000", "#B22222", "#FF1A1A", "#8B0000", "#5C0000", "#FF0000"]
        self.canvas.itemconfig(self.title_id, fill=colors[self.flicker_state % len(colors)])

        if random.random() < 0.08:
            jitter_x = self.title_base_x + random.randint(-6, 6)
            jitter_y = self.title_base_y + random.randint(-3, 3)
            self.canvas.coords(self.title_id, jitter_x, jitter_y)
        else:
            self.canvas.coords(self.title_id, self.title_base_x, self.title_base_y)

        # Drips growing/falling below the title
        for drip in self.title_drips:
            did, x, y, length, speed = drip
            length += speed
            if length > 90:
                length = random.randint(15, 30)
            self.canvas.coords(did, x, y, x, y + length)
            drip[3] = length

        # Full-screen blood rain
        for drop in self.rain:
            did, x, y, length, speed = drop
            y += speed
            if y > self.height:
                y = random.randint(-120, 0)
                x = random.randint(0, self.width)
            self.canvas.coords(did, x, y, x, y + length)
            drop[2] = y

        # Rising blood pool at the bottom (slow, stops near an eighth of the screen)
        if self.pool_height < self.height * 0.12:
            self.pool_height += 0.3
            self.canvas.coords(
                self.pool_id,
                0, self.height - self.pool_height, self.width, self.height
            )

        # Heartbeat-style pulsing border thickness
        self.pulse_width += self.pulse_dir * 0.4
        if self.pulse_width > 10 or self.pulse_width < 3:
            self.pulse_dir *= -1
        self.canvas.itemconfig(self.border_id, width=self.pulse_width)

        self.root.after(60, self.animate)

    # ---------- password check ----------

    def check_password(self, event=None):
        if self.pw_var.get() == PASSWORD:
            self.root.destroy()
        else:
            self.flash_wrong()
            self.pw_var.set("")

    def flash_wrong(self):
        self.canvas.configure(bg="#4a0000")
        self.root.after(150, lambda: self.canvas.configure(bg="black"))


if __name__ == "__main__":
    LockScreen()