from pathlib import Path
import time
import requests
import random
import tkinter as tk
from PIL import Image, ImageTk

BASE_URL = "https://musicbrainz.org/ws/2"

HEADERS = {
    "User-Agent": "AlbumOfTheDay/1.0 (ayoubgourstan@gmail.com)"
}

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


def download_album_cover(release_group_id):
    covers_dir = Path("covers")
    covers_dir.mkdir(exist_ok=True)

    cover_path = covers_dir / f"{release_group_id}.jpg"

    url = (
        f"https://coverartarchive.org/"
        f"release-group/{release_group_id}/front"
    )

    try:
        response = requests.get(
            url,
            headers=HEADERS,
            timeout=20
        )

        if response.status_code == 404:
            print("No cover art available for this album")
            return None

        response.raise_for_status()

        cover_path.write_bytes(response.content)

        print(f"Cover saved to : {cover_path}")
        return cover_path

    except requests.RequestException as error:
        print(f"Could not download album cover: {error}")
        return None

def show_cover(cover_path):
    if cover_path is None:
        return

    root = tk.Tk()
    root.title("Album of the Day")
    root.geometry("500x500")

    image = Image.open(cover_path)
    image.thumbnail((400, 400))

    photo = ImageTk.PhotoImage(image)

    cover_label = tk.Label(root, image=photo)
    cover_label.pack(pady=20)

    root.mainloop()


def get_random_album():
    albums = mb_request("release-group/", {
            "query": "primarytype:album AND status:official",
            "fmt": "json",
            "limit": 100,
            "offset": random.randint(0, 100),
        }).get("release-groups", [])

    if not albums:
        raise RuntimeError("No albums found. Try again.")

    album = random.choice(albums)
    album_id = album["id"]

    cover_path = download_album_cover(album_id)

    releases = mb_request("release/", {
            "release-group": album_id,
            "fmt": "json",
            "limit": 10
        }).get("releases", [])

    if releases:
        release = random.choice(releases)
        release_id = release["id"]

        release = mb_request(f"/release/{release_id}",  {
                "inc": "recordings+artists+labels",
                "fmt": "json",
            })
    else:
        release = {}

    print("\n" + "=" * 45)
    print("ALBUM:", album.get("title", "Unknown"))
    print("ARTIST:", ", ".join(
        artist["artist"]["name"]
        for artist in album.get("artist-credit", [])
        if isinstance(artist, dict) and artist.get("artist")
    ) or "Unknown")
    print("FIRST RELEASE:", album.get("first-release-date", "Unknown"))

    if release:
        print("RELEASE COUNTRY:", release.get("country", "Unknown"))
        print("RELEASE DATE:", release.get("date", "Unknown"))
        print("FORMAT:", ", ".join(
            medium.get("format", "Unknown")
            for medium in release.get("media", [])
        ) or "Unknown")

        print("\nTRACKLIST:")
        for medium in release.get("media", []):
            for track in medium.get("tracks", []):
                recording = track.get("recording", {})
                title = recording.get("title", track.get("title", "Unknown"))
                duration = recording.get("length", track.get("length"))

                if duration:
                    duration = f"{duration // 60000}:{(duration // 1000) % 60:02d}"
                else:
                    duration = "Unknown"

                print(f"{track.get('position', '?')}. {title} ({duration})")

    print("=" * 45)

    show_cover(cover_path)


    
if __name__ == "__main__":
    try:
        get_random_album()
    except requests.RequestException as error:
        print("Network/API error: ", error)
    except (RuntimeError, ValueError) as error:
        print("Error: ", error)
