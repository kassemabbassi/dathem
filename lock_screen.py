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

        # --- Title (flickers between shades of red like a warning light) ---
        self.title_id = self.canvas.create_text(
            self.width // 2, self.height // 3,
            text="SYSTEM LOCKED",
            font=("Impact", 72, "bold"),
            fill="#8B0000"
        )

        self.subtitle_id = self.canvas.create_text(
            self.width // 2, self.height // 3 + 65,
            text="UNAUTHORIZED PRESENCE DETECTED",
            font=("Consolas", 16),
            fill="#B22222"
        )

        # --- Password field: characters are replaced by a space, so nothing
        #     visible is typed - only the cursor moves. ---
        self.pw_var = tk.StringVar()
        self.entry = tk.Entry(
            self.root, textvariable=self.pw_var,
            show=" ", font=("Consolas", 22),
            bg="black", fg="red", insertbackground="red",
            relief="flat", justify="center", width=20,
            highlightthickness=2, highlightbackground="#8B0000", highlightcolor="red"
        )
        self.canvas.create_window(self.width // 2, self.height // 2, window=self.entry)
        self.entry.bind("<Return>", self.check_password)
        self.entry.focus_set()

        self.hint_id = self.canvas.create_text(
            self.width // 2, self.height // 2 + 40,
            text="Enter password and press Enter",
            font=("Consolas", 11),
            fill="#555555"
        )

        # --- Falling "blood drip" lines for atmosphere ---
        self.drips = []
        for _ in range(35):
            x = random.randint(0, self.width)
            y = random.randint(-self.height, 0)
            length = random.randint(10, 45)
            speed = random.uniform(2, 6)
            drip_id = self.canvas.create_line(x, y, x, y + length, fill="#6B0000", width=2)
            self.drips.append([drip_id, x, y, length, speed])

        self.flicker_state = 0
        self.animate()

        # Keep grabbing focus so the entry field can't be tabbed away from easily
        self.root.after(100, self.refocus)

        self.root.mainloop()

    def block_close(self):
        pass  # ignore the window-close (X) request entirely

    def refocus(self):
        self.entry.focus_force()
        self.root.after(500, self.refocus)

    def animate(self):
        self.flicker_state += 1
        colors = ["#8B0000", "#B22222", "#FF1A1A", "#8B0000", "#5C0000"]
        self.canvas.itemconfig(self.title_id, fill=colors[self.flicker_state % len(colors)])

        for drip in self.drips:
            drip_id, x, y, length, speed = drip
            y += speed
            if y > self.height:
                y = random.randint(-120, 0)
                x = random.randint(0, self.width)
            self.canvas.coords(drip_id, x, y, x, y + length)
            drip[2] = y

        self.root.after(80, self.animate)

    def check_password(self, event=None):
        if self.pw_var.get() == PASSWORD:
            self.root.destroy()
        else:
            self.flash_wrong()
            self.pw_var.set("")

    def flash_wrong(self):
        self.canvas.configure(bg="#3a0000")
        self.root.after(150, lambda: self.canvas.configure(bg="black"))


if __name__ == "__main__":
    LockScreen()