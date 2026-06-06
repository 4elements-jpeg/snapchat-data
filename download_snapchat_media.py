#!/usr/bin/env python3
"""Download Snapchat saved media from a JSON export and set image dates."""

import json
import os
import tkinter as tk
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Tuple
from tkinter import filedialog, messagebox, scrolledtext
from urllib.parse import parse_qs, urlparse

import piexif
import requests

DATE_FORMAT = "%Y-%m-%d %H:%M:%S"
EXIF_DATE_FORMAT = "%Y:%m:%d %H:%M:%S"


def parse_snapchat_date(date_str: str) -> datetime:
    """Parse a Snapchat date string like '2021-02-02 13:02:59 UTC'."""
    cleaned = date_str.strip().removesuffix(" UTC").strip()
    return datetime.strptime(cleaned, DATE_FORMAT).replace(tzinfo=timezone.utc)


def date_to_exif_string(dt: datetime) -> str:
    return dt.strftime(EXIF_DATE_FORMAT)


def sid_from_url(url: str) -> Optional[str]:
    parsed = urlparse(url)
    params = parse_qs(parsed.query)
    sid_values = params.get("sid")
    return sid_values[0] if sid_values else None


def safe_filename(date_str: Optional[str], index: int, sid: Optional[str], extension: str) -> str:
    if date_str:
        dt = parse_snapchat_date(date_str)
        prefix = dt.strftime("%Y-%m-%d_%H-%M-%S")
    else:
        prefix = f"unknown-date_{index:03d}"

    suffix = sid[:8] if sid else f"{index:03d}"
    return f"{prefix}_{suffix}{extension}"


def extension_from_response(response: requests.Response, fallback: str = ".jpg") -> str:
    content_type = response.headers.get("Content-Type", "").lower()
    if "jpeg" in content_type or "jpg" in content_type:
        return ".jpg"
    if "png" in content_type:
        return ".png"
    if "webp" in content_type:
        return ".webp"
    if "heic" in content_type or "heif" in content_type:
        return ".heic"
    if "video" in content_type or "mp4" in content_type:
        return ".mp4"
    return fallback


def set_image_metadata(path: Path, dt: datetime) -> None:
    """Set EXIF dates for JPEG images and filesystem timestamps for all files."""
    timestamp = dt.timestamp()
    os.utime(path, (timestamp, timestamp))

    if path.suffix.lower() not in {".jpg", ".jpeg"}:
        return

    exif_date = date_to_exif_string(dt)
    try:
        exif_dict = piexif.load(str(path))
    except piexif.InvalidImageDataError:
        exif_dict = {"0th": {}, "Exif": {}, "GPS": {}, "1st": {}, "thumbnail": None}

    exif_dict["0th"][piexif.ImageIFD.DateTime] = exif_date
    exif_dict["Exif"][piexif.ExifIFD.DateTimeOriginal] = exif_date
    exif_dict["Exif"][piexif.ExifIFD.DateTimeDigitized] = exif_date

    exif_bytes = piexif.dump(exif_dict)
    piexif.insert(exif_bytes, str(path))


def download_file(url: str, destination: Path, session: requests.Session) -> requests.Response:
    response = session.get(url, stream=True, timeout=60)
    response.raise_for_status()

    with open(destination, "wb") as file:
        for chunk in response.iter_content(chunk_size=8192):
            if chunk:
                file.write(chunk)

    return response


def load_media_items(json_path: Path) -> list[dict]:
    with open(json_path, encoding="utf-8") as file:
        data = json.load(file)

    if isinstance(data, dict) and "Saved Media" in data:
        items = data["Saved Media"]
    elif isinstance(data, list):
        items = data
    else:
        raise ValueError('JSON must contain a "Saved Media" array or be a top-level array.')

    if not isinstance(items, list):
        raise ValueError('Expected "Saved Media" to be an array.')

    return items


def process_media(json_path: Path, output_dir: Path, log) -> Tuple[int, int, int]:
    items = load_media_items(json_path)
    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            )
        }
    )

    downloaded = 0
    skipped = 0
    failed = 0

    for index, item in enumerate(items, start=1):
        if not isinstance(item, dict):
            log(f"[{index}] Skipping invalid item (not an object).")
            skipped += 1
            continue

        download_link = item.get("Download Link")
        if not download_link:
            log(f"[{index}] Skipping item without Download Link.")
            skipped += 1
            continue

        date_str = item.get("Date")
        media_type = item.get("Media Type", "UNKNOWN")
        sid = sid_from_url(download_link)

        temp_path = None
        try:
            log(f"[{index}] Downloading {media_type}...")
            temp_name = safe_filename(date_str, index, sid, ".download")
            temp_path = output_dir / temp_name

            response = download_file(download_link, temp_path, session)

            extension = extension_from_response(
                response,
                fallback=Path(urlparse(download_link).path).suffix or ".jpg",
            )

            final_name = safe_filename(date_str, index, sid, extension)
            final_path = output_dir / final_name

            if final_path.exists():
                stem = final_path.stem
                final_path = output_dir / f"{stem}_{index}{extension}"

            temp_path.rename(final_path)
            temp_path = None

            if date_str:
                dt = parse_snapchat_date(date_str)
                set_image_metadata(final_path, dt)
                log(f"[{index}] Saved {final_path.name} with date {date_str}")
            else:
                log(f"[{index}] Saved {final_path.name} (no date in JSON)")

            downloaded += 1
        except Exception as error:
            failed += 1
            log(f"[{index}] Failed: {error}")
            if temp_path and temp_path.exists():
                temp_path.unlink()

    return downloaded, skipped, failed


class DownloaderApp:
    def __init__(self) -> None:
        self.root = tk.Tk()
        self.root.title("Snapchat Media Downloader")
        self.root.geometry("720x480")

        self.json_path = tk.StringVar()
        self.output_dir = tk.StringVar(value=str(Path.home() / "Downloads" / "snapchat-media"))

        self._build_ui()

    def _build_ui(self) -> None:
        padding = {"padx": 12, "pady": 6}

        frame = tk.Frame(self.root)
        frame.pack(fill="x", **padding)

        tk.Label(frame, text="JSON file:").grid(row=0, column=0, sticky="w")
        tk.Entry(frame, textvariable=self.json_path, width=70).grid(row=0, column=1, sticky="we")
        tk.Button(frame, text="Browse...", command=self.select_json).grid(row=0, column=2, padx=(8, 0))

        tk.Label(frame, text="Save to:").grid(row=1, column=0, sticky="w", pady=(8, 0))
        tk.Entry(frame, textvariable=self.output_dir, width=70).grid(row=1, column=1, sticky="we", pady=(8, 0))
        tk.Button(frame, text="Browse...", command=self.select_output_dir).grid(
            row=1, column=2, padx=(8, 0), pady=(8, 0)
        )

        frame.columnconfigure(1, weight=1)

        button_frame = tk.Frame(self.root)
        button_frame.pack(fill="x", **padding)
        tk.Button(button_frame, text="Download Media", command=self.run_download).pack(side="left")
        tk.Button(button_frame, text="Quit", command=self.root.destroy).pack(side="right")

        self.log_box = scrolledtext.ScrolledText(self.root, height=20, state="disabled")
        self.log_box.pack(fill="both", expand=True, padx=12, pady=(0, 12))

    def log(self, message: str) -> None:
        self.log_box.configure(state="normal")
        self.log_box.insert("end", message + "\n")
        self.log_box.see("end")
        self.log_box.configure(state="disabled")
        self.root.update_idletasks()

    def select_json(self) -> None:
        path = filedialog.askopenfilename(
            title="Select Snapchat JSON file",
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")],
        )
        if path:
            self.json_path.set(path)

    def select_output_dir(self) -> None:
        path = filedialog.askdirectory(title="Select folder to save downloaded media")
        if path:
            self.output_dir.set(path)

    def run_download(self) -> None:
        json_path = self.json_path.get().strip()
        output_dir = self.output_dir.get().strip()

        if not json_path:
            messagebox.showerror("Missing file", "Please select a JSON file.")
            return

        if not output_dir:
            messagebox.showerror("Missing folder", "Please select an output folder.")
            return

        json_file = Path(json_path)
        save_dir = Path(output_dir)

        if not json_file.is_file():
            messagebox.showerror("Invalid file", f"File not found:\n{json_file}")
            return

        try:
            save_dir.mkdir(parents=True, exist_ok=True)
            self.log(f"Reading {json_file}")
            self.log(f"Saving files to {save_dir}")
            downloaded, skipped, failed = process_media(json_file, save_dir, self.log)
            summary = (
                f"Done.\n\nDownloaded: {downloaded}\nSkipped: {skipped}\nFailed: {failed}"
            )
            self.log(summary.replace("\n\n", "\n"))
            messagebox.showinfo("Complete", summary)
        except Exception as error:
            self.log(f"Error: {error}")
            messagebox.showerror("Error", str(error))


def main() -> None:
    app = DownloaderApp()
    app.root.mainloop()


if __name__ == "__main__":
    main()
