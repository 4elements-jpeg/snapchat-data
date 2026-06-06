# Snapchat Media Downloader

Download photos and videos from a Snapchat data export JSON file, then restore each file's original date from the export metadata.

When you request your data from Snapchat, the export includes download links for saved memories. This tool reads those links from a JSON file, downloads the media, and sets the file dates so your photos sort correctly in your photo library.

## Requirements

- Python 3.9 or later
- tkinter (included with most Python installations on macOS and Windows)

## Installation

1. Clone or download this repository.

2. Install dependencies:

```bash
pip3 install -r requirements.txt
```

Optionally, use a virtual environment:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Usage

Run the downloader:

```bash
python3 download_snapchat_media.py
```

A window will open with two fields:

1. **JSON file** — Browse to your Snapchat export JSON file.
2. **Save to** — Choose the folder where downloaded media will be saved (defaults to `~/Downloads/snapchat-media`).

Click **Download Media** to start. Progress appears in the log area. When finished, a summary shows how many files were downloaded, skipped, or failed.

## JSON format

The script expects a JSON file in the format Snapchat provides for saved media. It looks like this:

```json
{
  "Saved Media": [
    {
      "Date": "2021-02-02 13:02:59 UTC",
      "Media Type": "PHOTO",
      "Download Link": "https://app.snapchat.com/dmd/memories?uid=..."
    }
  ]
}
```

Each item in the `"Saved Media"` array can have:

| Field | Required | Description |
|-------|----------|-------------|
| `Download Link` | Yes | URL to download the media file |
| `Date` | No | Original capture date (used for file metadata) |
| `Media Type` | No | e.g. `PHOTO` or `VIDEO` (logged for reference) |

The script also accepts a top-level JSON array if your file is formatted that way instead of using a `"Saved Media"` wrapper.

Items without a `Download Link` are skipped. Items without a `Date` are still downloaded, but no date metadata is applied.

## How it works

### 1. Load the JSON file

The script reads the selected JSON file and extracts the list of media items from `"Saved Media"`.

### 2. Download each file

For each item with a `Download Link`, the script:

- Sends an HTTP request to Snapchat's servers
- Streams the response to disk
- Detects the file type from the response `Content-Type` header (`.jpg`, `.png`, `.webp`, `.heic`, `.mp4`, etc.)

### 3. Name the file

Files are saved using the date and a short ID from the download URL:

```
2021-02-02_13-02-59_7E77D22A.jpg
```

- `2021-02-02_13-02-59` — date and time from the JSON `Date` field
- `7E77D22A` — first 8 characters of the memory `sid` from the URL
- If two files would have the same name, an index suffix is added to avoid overwriting.

### 4. Set the date metadata

If a `Date` field is present, the script applies it in two ways:

**Filesystem timestamps** (all file types)

- Sets the file's created and modified times to match the `Date` value
- This is what most file browsers and photo apps use to sort files

**EXIF metadata** (JPEG only)

- Writes `DateTime`, `DateTimeOriginal`, and `DateTimeDigitized` EXIF tags
- Date format is converted from `2021-02-02 13:02:59 UTC` to EXIF format `2021:02:02 13:02:59`

## Getting your Snapchat data

1. Go to [accounts.snapchat.com](https://accounts.snapchat.com) and request a copy of your data.
2. When Snapchat emails you the download link, extract the archive.
3. Look for a JSON file containing your saved media entries (often under a `json` folder in the export).
4. Use that file with this tool.

## Limitations

- **Expired links** — Snapchat download links are signed and time-limited. Links from older exports may no longer work. Failed downloads are logged and counted in the summary.
- **Export quality** — If the JSON was copied manually or corrupted (broken line breaks, missing fields), some entries may be skipped or fail to download.
- **Date metadata on non-JPEG files** — PNG, WebP, HEIC, and video files get filesystem timestamps only. EXIF date tags are written for JPEG files.
- **No authentication** — The script uses the download links as-is. It does not log into Snapchat. If a link requires an active session, it will fail.

## Project files

| File | Description |
|------|-------------|
| `download_snapchat_media.py` | Main script with the tkinter GUI |
| `requirements.txt` | Python package dependencies |
| `test_media.json` | Example JSON for testing (gitignored) |

## Dependencies

| Package | Purpose |
|---------|---------|
| [requests](https://pypi.org/project/requests/) | HTTP downloads |
| [Pillow](https://pypi.org/project/Pillow/) | Image handling |
| [piexif](https://pypi.org/project/piexif/) | Reading and writing JPEG EXIF metadata |
