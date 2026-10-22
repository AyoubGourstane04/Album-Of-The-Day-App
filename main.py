from logging import root
from pathlib import Path
import time
import requests
import random
import tkinter as tk
from PIL import Image, ImageTk
import threading
from tkinter import ttk, messagebox

BASE_URL = "https://musicbrainz.org/ws/2"
COVER_URL = "https://coverartarchive.org"

HEADERS = {
    "User-Agent": "AlbumOfTheDay/1.0 (ayoubgourstan@gmail.com)"
}

COVERS_DIR = Path("covers")
COVERS_DIR.mkdir(exist_ok=True)

BG = "#000000"
CARD = "#121216"
PANEL = "#1c1c24"
BORDER = "#2e2e36"
TEXT = "#f4f4f5"
MUTED = "#9a9aa5"
DIM = "#6b6b76"
ACCENT = "#c8f56a"
ACCENT_HOVER = "#b5e04f"
BADGE_BG = "#0f3b22"
BADGE_FG = "#22c55e"

FONT = "Segoe UI"
COVER_SIZE = 190


last_request_time = 0

def mb_request(endpoint : str, params=None):
    global last_request_time

    elapsed = time.monotonic() - last_request_time

    if elapsed < 1.1:
        time.sleep(1.1 - elapsed)

    response = requests.get(
        f"{BASE_URL}/{endpoint.strip().removeprefix("/") if endpoint.startswith("/") else endpoint.strip()}",
        params=params,
        headers=HEADERS,
        timeout=20
    )

    last_request_time = time.monotonic()
    response.raise_for_status()

    return response.json()




def get_random_album():
    albums = mb_request("release-group/", {
            "query": "primarytype:album AND status:official",
            "fmt": "json",
            "limit": 20,
            "offset": random.randint(0, 100),
        }).get("release-groups", [])

    if not albums:
        raise RuntimeError("No albums found. Try again.")

    album = random.choice(albums)

    artist_names = []

    for credit in album.get("artist-credit", []):
        if isinstance(credit, dict) and credit.get("artist"):
            artist_names.append(credit["artist"]["name"])
    
    artist_name = ", ".join(artist_names) or "Unkown artist"


    releases = mb_request("release/", {
            "release-group": album["id"],
            "fmt": "json",
            "limit": 10
        }).get("releases", [])

    release = {}

    if releases:
        selected_release = random.choice(releases)

        release = mb_request(f"/release/{selected_release["id"]}",  {
                "inc": "recordings+artists+labels",
                "fmt": "json",
            })
    tracks = []
    for medium in release.get("media", []):
        for track in medium.get("tracks", []):
            recording = track.get("recording", {})

            duration_ms = (
                recording.get("length")
                or
                track.get("length")
            )

            if duration_ms is not None:
                total_seconds = duration_ms // 1000
                duration = (
                    f"{total_seconds// 60}:"
                    f"{total_seconds % 60:02d}"
                )
            else:
                duration = "Unknown"
            
            tracks.append({
                "number": track.get("position", "?"),
                "title": recording.get(
                    "title",
                    track.get("title", "Unkown track")
                ),
                "duration": duration
            })
    
    return {
        "id": album["id"],
        "title": album.get("title", "Unknown album"),
        "artist": artist_name,
        "first_release_date": album.get(
            "first-release-date", "Unknown"
        ),
        "release_date": release.get("date", "Unknown"),
        "country": release.get("country", "Unknown"),
        "label": ", ".join(
            info.get("label", {}).get("name", "")
            for info in release.get("label-info", [])
            if info.get("label")
        ) or "Unknown",
        "tracks": tracks
    }
    


def download_album_cover(album_id):
    cover_path = COVERS_DIR / f"{album_id}.jpg"

    url = f"{COVER_URL}/release-group/{album_id}/front"

    try:
        response = requests.get(
            url,
            headers=HEADERS,
            timeout=20
        )

        if response.status_code == 404:
            return None

        response.raise_for_status()

        cover_path.write_bytes(response.content)

        return cover_path

    except requests.RequestException as error:
        return None





class AlbumApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Album of the Day")
        self.root.geometry("900x640")
        self.root.minsize(760, 560)
        self.root.configure(bg=BG)

        self.current_image = None
        self.loading = False

        self.setup_ui()
        self.root.protocol("WM_DELETE_WINDOW", self.close_app)
        self.discover_album()

    # ------------------------------------------------------------ UI

    def setup_ui(self):
        self.card = tk.Frame(
            self.root,
            bg=CARD,
            padx=18,
            pady=16,
        )
        self.card.pack(
            fill="both",
            expand=True,
            padx=12,
            pady=12,
        )

        self._build_header(self.card)
        self._divider(self.card).pack(fill="x", pady=14)

        tk.Label(
            self.card,
            text="TODAY'S PICK",
            bg=CARD,
            fg=MUTED,
            font=(FONT, 9, "bold"),
        ).pack(anchor="w", pady=(0, 10))

        self._build_hero(self.card)
        self._build_tracklist(self.card)

    def _divider(self, parent):
        return tk.Frame(parent, bg=BORDER, height=1)

    def _build_header(self, parent):
        header = tk.Frame(parent, bg=CARD)
        header.pack(fill="x")

        tk.Label(
            header,
            text="♫",
            bg=ACCENT,
            fg="#111111",
            font=("Segoe UI Symbol", 20, "bold"),
            width=3,
            height=1,
        ).pack(side="left")

        titles = tk.Frame(header, bg=CARD)
        titles.pack(side="left", padx=12)

        tk.Label(
            titles,
            text="ALBUM / DAY",
            bg=CARD,
            fg=TEXT,
            font=(FONT, 13, "bold"),
        ).pack(anchor="w")

        tk.Label(
            titles,
            text="YOUR DAILY MUSIC DISCOVERY",
            bg=CARD,
            fg=MUTED,
            font=(FONT, 8),
        ).pack(anchor="w")

        self.badge = tk.Label(
            header,
            text="DISCOVER",
            bg=BADGE_BG,
            fg=BADGE_FG,
            font=(FONT, 8, "bold"),
            padx=8,
            pady=4,
        )
        self.badge.pack(side="right", anchor="n", pady=4)

    def _build_hero(self, parent):
        self.hero = tk.Frame(parent, bg=CARD)
        self.hero.pack(fill="x")

        # Fixed-size cover container
        self.cover_box = tk.Frame(
            self.hero,
            bg=PANEL,
            width=COVER_SIZE,
            height=COVER_SIZE,
        )
        self.cover_box.pack(side="left", anchor="n", padx=(0, 18))
        self.cover_box.pack_propagate(False)

        self.cover_label = tk.Label(
            self.cover_box,
            text="Loading artwork...",
            bg=PANEL,
            fg=DIM,
            font=(FONT, 9),
            wraplength=COVER_SIZE - 20,
        )
        self.cover_label.pack(fill="both", expand=True)

        # Album information
        self.info = tk.Frame(self.hero, bg=CARD)
        self.info.pack(side="left", fill="both", expand=True)

        self.title_label = tk.Label(
            self.info,
            text="Discovering an album...",
            bg=CARD,
            fg=TEXT,
            font=(FONT, 16, "bold"),
            anchor="w",
            justify="left",
            wraplength=430,
        )
        self.title_label.pack(fill="x", pady=(0, 8))

        self.artist_label = tk.Label(
            self.info,
            text="",
            bg=CARD,
            fg=ACCENT,
            font=(FONT, 12, "bold"),
            anchor="w",
            justify="left",
            wraplength=430,
        )
        self.artist_label.pack(fill="x", pady=(0, 6))

        self.meta_label = tk.Label(
            self.info,
            text="",
            bg=CARD,
            fg=MUTED,
            font=(FONT, 10),
            anchor="w",
            justify="left",
            wraplength=430,
        )
        self.meta_label.pack(fill="x", pady=(0, 10))

        self._divider(self.info).pack(fill="x", pady=(0, 10))

        tk.Label(
            self.info,
            text="ALBUM DETAILS",
            bg=CARD,
            fg=TEXT,
            font=(FONT, 9, "bold"),
            anchor="w",
        ).pack(fill="x", pady=(0, 4))

        self.release_label = self._detail_label(
            self.info, "Release date: —"
        )
        self.label_label = self._detail_label(
            self.info, "Label: —"
        )
        self.count_label = self._detail_label(
            self.info, "Tracks: —"
        )

        # Button lives in the info column so it's always visible
        self._build_button(self.info)

        # Adapt text wrapping to the available window width.
        self.info.bind("<Configure>", self._resize_info_text)

    def _resize_info_text(self, event):
        wrap = max(180, event.width - 8)

        self.title_label.configure(wraplength=wrap)
        self.artist_label.configure(wraplength=wrap)
        self.meta_label.configure(wraplength=wrap)

    def _detail_label(self, parent, text):
        label = tk.Label(
            parent,
            text=text,
            bg=CARD,
            fg=MUTED,
            font=(FONT, 10),
            anchor="w",
            justify="left",
        )
        label.pack(fill="x", pady=2)
        return label

    def _build_tracklist(self, parent):
        self.track_panel = tk.Frame(
            parent,
            bg=PANEL,
            padx=14,
            pady=12,
        )
        self.track_panel.pack(
            fill="both",
            expand=True,
            pady=(16, 0),
        )

        head = tk.Frame(self.track_panel, bg=PANEL)
        head.pack(fill="x", pady=(0, 6))

        tk.Label(
            head,
            text="Tracklist",
            bg=PANEL,
            fg=TEXT,
            font=(FONT, 11, "bold"),
        ).pack(side="left")

        self.track_range_label = tk.Label(
            head,
            text="",
            bg=PANEL,
            fg=MUTED,
            font=(FONT, 9),
        )
        self.track_range_label.pack(side="right")

        body = tk.Frame(self.track_panel, bg=PANEL)
        body.pack(fill="both", expand=True)

        self.track_canvas = tk.Canvas(
            body,
            bg=PANEL,
            height=150,
            highlightthickness=0,
            bd=0,
        )

        self.track_scrollbar = tk.Scrollbar(
            body,
            orient="vertical",
            command=self.track_canvas.yview,
        )

        self.track_canvas.configure(
            yscrollcommand=self.track_scrollbar.set
        )

        self.track_canvas.pack(
            side="left",
            fill="both",
            expand=True,
        )
        self.track_scrollbar.pack(side="right", fill="y")

        self.track_frame = tk.Frame(
            self.track_canvas,
            bg=PANEL,
        )

        self.track_window = self.track_canvas.create_window(
            (0, 0),
            window=self.track_frame,
            anchor="nw",
        )

        self.track_frame.bind(
            "<Configure>",
            self._update_track_scrollregion,
        )
        self.track_canvas.bind(
            "<Configure>",
            self._resize_track_frame,
        )

        self.track_canvas.bind("<Enter>", self._bind_wheel)
        self.track_canvas.bind("<Leave>", self._unbind_wheel)

    def _update_track_scrollregion(self, _event=None):
        self.track_canvas.configure(
            scrollregion=self.track_canvas.bbox("all")
        )

    def _resize_track_frame(self, event):
        self.track_canvas.itemconfigure(
            self.track_window,
            width=event.width,
        )

    def _bind_wheel(self, _event=None):
        self.track_canvas.bind_all(
            "<MouseWheel>",
            self._on_wheel,
        )

    def _unbind_wheel(self, _event=None):
        self.track_canvas.unbind_all("<MouseWheel>")

    def _on_wheel(self, event):
        if event.delta:
            self.track_canvas.yview_scroll(
                int(-event.delta / 120),
                "units",
            )

    def _build_button(self, parent):
        self.discover_button = tk.Button(
            parent,
            text="⤮   Discover Another Album",
            command=self.discover_album,
            bg=ACCENT,
            fg="#111111",
            activebackground=ACCENT_HOVER,
            activeforeground="#111111",
            disabledforeground="#55603a",
            font=(FONT, 11, "bold"),
            relief="flat",
            bd=0,
            cursor="hand2",
            pady=12,
        )
        self.discover_button.pack(fill="x", pady=(14, 0))

        self.discover_button.bind(
            "<Enter>",
            self._button_hover,
        )
        self.discover_button.bind(
            "<Leave>",
            self._button_leave,
        )

    def _button_hover(self, _event):
        if str(self.discover_button["state"]) == "normal":
            self.discover_button.configure(bg=ACCENT_HOVER)

    def _button_leave(self, _event):
        self.discover_button.configure(bg=ACCENT)

    # -------------------------------------------------------- Track rows

    def _clear_tracks(self):
        for child in self.track_frame.winfo_children():
            child.destroy()

        self.track_canvas.yview_moveto(0)

    def _add_track_row(self, number, title, duration):
        row = tk.Frame(self.track_frame, bg=PANEL)
        row.pack(fill="x", pady=1)

        row.grid_columnconfigure(1, weight=1)

        number_text = (
            f"{int(number):02d}"
            if str(number).isdigit()
            else str(number)
        )

        tk.Label(
            row,
            text=number_text,
            bg=PANEL,
            fg=DIM,
            font=(FONT, 10),
            width=4,
            anchor="w",
        ).grid(
            row=0,
            column=0,
            padx=(4, 8),
            pady=7,
            sticky="w",
        )

        tk.Label(
            row,
            text=title or "Untitled track",
            bg=PANEL,
            fg=TEXT,
            font=(FONT, 10),
            anchor="w",
            justify="left",
            wraplength=500,
        ).grid(
            row=0,
            column=1,
            sticky="ew",
            pady=7,
        )

        tk.Label(
            row,
            text=duration or "--:--",
            bg=PANEL,
            fg=MUTED,
            font=(FONT, 9),
            anchor="e",
        ).grid(
            row=0,
            column=2,
            padx=(8, 6),
            sticky="e",
        )

    # --------------------------------------------------------- Discovery

    def discover_album(self):
        if self.loading:
            return

        self.loading = True

        self.discover_button.configure(
            state="disabled",
            text="Finding an album...",
        )
        self.badge.configure(
            text="LOADING",
            bg="#3b3210",
            fg=ACCENT,
        )

        self.title_label.configure(text="Discovering an album...")
        self.artist_label.configure(text="")
        self.meta_label.configure(text="")
        self.release_label.configure(text="Release date: —")
        self.label_label.configure(text="Label: —")
        self.count_label.configure(text="Tracks: —")
        self.track_range_label.configure(text="")
        self.cover_label.configure(
            image="",
            text="Loading artwork...",
        )
        self.current_image = None

        self._clear_tracks()

        threading.Thread(
            target=self.load_album,
            daemon=True,
        ).start()

    def load_album(self):
        try:
            album = get_random_album()
            cover_path = download_album_cover(album["id"])

            self.root.after(
                0,
                lambda a=album, c=cover_path:
                    self.display_album(a, c),
            )

        except Exception as error:
            self.root.after(
                0,
                lambda message=str(error):
                    self.show_error(message),
            )

    def display_album(self, album, cover_path):
        try:
            self.title_label.configure(
                text=album.get("title") or "Unknown album"
            )
            self.artist_label.configure(
                text=album.get("artist") or "Unknown artist"
            )

            first_release = str(
                album.get("first_release_date") or ""
            )
            year = first_release[:4] if first_release else "Unknown year"
            country = album.get("country") or "Unknown country"

            self.meta_label.configure(
                text=f"{year} · {country}"
            )

            tracks = album.get("tracks") or []

            self.release_label.configure(
                text=(
                    "Release date: "
                    f"{album.get('release_date') or 'Unknown'}"
                )
            )
            self.label_label.configure(
                text=f"Label: {album.get('label') or 'Unknown'}"
            )
            self.count_label.configure(
                text=f"Tracks: {len(tracks)}"
            )

            # Cover art
            self.current_image = None

            if cover_path:
                try:
                    with Image.open(cover_path) as source:
                        image = source.convert("RGB")
                        image.thumbnail(
                            (COVER_SIZE, COVER_SIZE),
                            Image.Resampling.LANCZOS,
                        )

                    self.current_image = ImageTk.PhotoImage(image)

                    self.cover_label.configure(
                        image=self.current_image,
                        text="",
                    )

                except (OSError, ValueError):
                    self._show_missing_cover()
            else:
                self._show_missing_cover()

            # Tracklist
            self._clear_tracks()

            if tracks:
                self.track_range_label.configure(
                    text=f"01 — {len(tracks):02d}"
                )

                for track in tracks:
                    self._add_track_row(
                        track.get("number", "—"),
                        track.get("title", "Untitled track"),
                        track.get("duration", "--:--"),
                    )
            else:
                self.track_range_label.configure(text="0 tracks")

                tk.Label(
                    self.track_frame,
                    text="No tracklist available.",
                    bg=PANEL,
                    fg=MUTED,
                    font=(FONT, 10),
                ).pack(anchor="w", padx=4, pady=8)

            self.badge.configure(
                text="DISCOVER",
                bg=BADGE_BG,
                fg=BADGE_FG,
            )

        except Exception as error:
            self.show_error(str(error))
            return

        finally:
            self.loading = False
            self.discover_button.configure(
                state="normal",
                text="⤮   Discover Another Album",
            )

    def _show_missing_cover(self):
        self.current_image = None
        self.cover_label.configure(
            image="",
            text="Artwork unavailable",
            bg=PANEL,
            fg=DIM,
        )

    def show_error(self, error):
        self.loading = False

        self.badge.configure(
            text="ERROR",
            bg="#401d22",
            fg="#ff8585",
        )
        self.discover_button.configure(
            state="normal",
            text="⤮   Try Again",
        )

        messagebox.showerror(
            "Album discovery failed",
            f"Could not retrieve an album.\n\n{error}",
            parent=self.root,
        )

    def close_app(self):
        self.track_canvas.unbind_all("<MouseWheel>")
        self.root.destroy()

        
if __name__ == "__main__":
    root = tk.Tk()
    app = AlbumApp(root)
    root.mainloop()
