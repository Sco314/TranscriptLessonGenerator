"""YouTube transcript fetching with multiple fallback methods.

Method 1: youtube-transcript-api library (most robust, actively maintained)
Method 2: Direct watch page scraping (port of the .gs fetchTranscriptFromYouTube)
Method 3: Innertube POST API (port of the .gs fetchCaptionTracksViaInnertube)
"""

from __future__ import annotations

import json
import logging
import re
import xml.etree.ElementTree as ET
from html import unescape

from .http_client import HttpClient

log = logging.getLogger(__name__)


def fetch_transcript(video_id: str, client: HttpClient) -> dict:
    """Fetch transcript for a YouTube video.

    Returns:
        {
            "text": str,           # full transcript as prose
            "segments": list,      # [{text, start}, ...] with timing
            "status": str,         # "ok" | "unavailable" | "failed"
            "error": str,          # error message if failed
        }
    """
    if not video_id:
        return {"text": "", "segments": [], "status": "failed", "error": "No video ID"}

    # Method 1: youtube-transcript-api library
    result = _fetch_via_library(video_id)
    if result["status"] == "ok":
        return result
    if result["status"] == "unavailable":
        return result  # no captions exist — don't retry other methods
    log.info("Library method failed for %s: %s. Trying page scrape...", video_id, result["error"])

    # Method 2: Direct watch page scraping
    result = _fetch_via_page_scrape(video_id, client)
    if result["status"] == "ok":
        return result
    if result["status"] == "unavailable":
        return result
    log.info("Page scrape failed for %s: %s. Trying Innertube...", video_id, result["error"])

    # Method 3: Innertube POST API
    result = _fetch_via_innertube(video_id, client)
    return result


def format_with_timestamps(segments: list) -> str:
    """Format segments as timestamped lines: [M:SS] text"""
    lines = []
    for seg in segments:
        start = seg.get("start", 0)
        minutes = int(start // 60)
        seconds = int(start % 60)
        text = seg.get("text", "").strip()
        if text:
            lines.append(f"[{minutes}:{seconds:02d}] {text}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Method 1: youtube-transcript-api library
# ---------------------------------------------------------------------------

def _fetch_via_library(video_id: str) -> dict:
    """Use the youtube-transcript-api Python library."""
    try:
        from youtube_transcript_api import YouTubeTranscriptApi
        ytt = YouTubeTranscriptApi()
        transcript = ytt.fetch(video_id)

        segments = []
        texts = []
        for snippet in transcript:
            text = snippet.text.strip()
            if not text:
                continue
            segments.append({"text": text, "start": snippet.start})
            texts.append(text)

        if not texts:
            return {"text": "", "segments": [], "status": "unavailable",
                    "error": "Transcript returned empty"}

        return {
            "text": " ".join(texts),
            "segments": segments,
            "status": "ok",
            "error": "",
        }

    except ImportError:
        return {"text": "", "segments": [], "status": "failed",
                "error": "youtube-transcript-api not installed"}
    except Exception as e:
        msg = str(e).lower()
        if "disabled" in msg or "no transcript" in msg or "not found" in msg:
            return {"text": "", "segments": [], "status": "unavailable",
                    "error": str(e)}
        return {"text": "", "segments": [], "status": "failed",
                "error": str(e)}


# ---------------------------------------------------------------------------
# Method 2: Direct watch page scraping (port of .gs)
# ---------------------------------------------------------------------------

def _fetch_via_page_scrape(video_id: str, client: HttpClient) -> dict:
    """Scrape the YouTube watch page for captionTracks, then fetch timedtext XML."""
    watch_url = f"https://www.youtube.com/watch?v={video_id}"

    resp = client.get(watch_url, headers={
        "Cookie": "CONSENT=YES+cb.20210328-17-p0.en+FX+999",
    })
    if resp.status_code != 200:
        return {"text": "", "segments": [], "status": "failed",
                "error": f"YouTube page returned HTTP {resp.status_code}"}

    resp.encoding = "utf-8"
    html = resp.text

    # Extract captionTracks JSON from ytInitialPlayerResponse
    cap_match = re.search(r'"captionTracks"\s*:\s*(\[.*?\])\s*[,}]', html)
    if not cap_match:
        if '"captions"' not in html:
            return {"text": "", "segments": [], "status": "unavailable",
                    "error": "No captions available for this video"}
        return {"text": "", "segments": [], "status": "failed",
                "error": "Could not find captionTracks in page source"}

    try:
        tracks = json.loads(cap_match.group(1))
    except json.JSONDecodeError as e:
        return {"text": "", "segments": [], "status": "failed",
                "error": f"Failed to parse captionTracks: {e}"}

    return _fetch_from_tracks(tracks, client)


# ---------------------------------------------------------------------------
# Method 3: Innertube POST API (port of .gs)
# ---------------------------------------------------------------------------

def _fetch_via_innertube(video_id: str, client: HttpClient) -> dict:
    """Use YouTube's internal Innertube player API to get caption tracks."""
    api_url = "https://www.youtube.com/youtubei/v1/player?key=AIzaSyA8eiZmM1FaDVjRy-df2KTyQ_vz_yYM39w"
    payload = {
        "context": {
            "client": {
                "clientName": "WEB",
                "clientVersion": "2.20240101.00.00",
            }
        },
        "videoId": video_id,
    }

    try:
        resp = client.post(api_url, json=payload)
        if resp.status_code != 200:
            return {"text": "", "segments": [], "status": "failed",
                    "error": f"Innertube returned HTTP {resp.status_code}"}

        data = resp.json()
        captions = data.get("captions", {})
        renderer = captions.get("playerCaptionsTracklistRenderer", {})
        tracks = renderer.get("captionTracks", [])

        if not tracks:
            return {"text": "", "segments": [], "status": "unavailable",
                    "error": "Innertube response has no caption tracks"}

        return _fetch_from_tracks(tracks, client)

    except Exception as e:
        return {"text": "", "segments": [], "status": "failed",
                "error": f"Innertube API error: {e}"}


# ---------------------------------------------------------------------------
# Shared: fetch timedtext XML from caption tracks
# ---------------------------------------------------------------------------

def _fetch_from_tracks(tracks: list, client: HttpClient) -> dict:
    """Given captionTracks array, find best English track and fetch transcript."""
    # Prefer manual English captions over ASR
    best_url = None
    for track in tracks:
        lang = track.get("languageCode", "")
        kind = track.get("kind", "")
        if lang.startswith("en") and kind != "asr":
            best_url = track.get("baseUrl", "")
            break

    # Fall back to any English track (including ASR)
    if not best_url:
        for track in tracks:
            if track.get("languageCode", "").startswith("en"):
                best_url = track.get("baseUrl", "")
                break

    # Fall back to first track of any language
    if not best_url and tracks:
        best_url = tracks[0].get("baseUrl", "")

    if not best_url:
        return {"text": "", "segments": [], "status": "failed",
                "error": "No usable caption track URL found"}

    # Fetch the timedtext XML
    resp = client.get(best_url, use_cache=False)
    if resp.status_code != 200:
        return {"text": "", "segments": [], "status": "failed",
                "error": f"Timedtext XML returned HTTP {resp.status_code}"}

    resp.encoding = "utf-8"
    return _parse_timedtext_xml(resp.text)


def _parse_timedtext_xml(xml_text: str) -> dict:
    """Parse YouTube timedtext XML into segments."""
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as e:
        return {"text": "", "segments": [], "status": "failed",
                "error": f"XML parse error: {e}"}

    segments = []
    texts = []
    for elem in root.iter("text"):
        raw = elem.text or ""
        text = unescape(raw).strip()
        if not text:
            continue
        start = float(elem.get("start", "0"))
        segments.append({"text": text, "start": start})
        texts.append(text)

    if not texts:
        return {"text": "", "segments": [], "status": "unavailable",
                "error": "Timedtext XML contained no text segments"}

    return {
        "text": " ".join(texts),
        "segments": segments,
        "status": "ok",
        "error": "",
    }
