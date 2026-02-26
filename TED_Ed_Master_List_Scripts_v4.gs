/**
 * TED-Ed Master List - Google Apps Script
 * v5.0 - 2026-02-26
 *
 * FUNCTIONS:
 *   fillMissingData()                - Fills in everything it can from URLs you provide
 *   fillMissingDataWithTimestamps()  - Same as above, but transcripts include [M:SS] timestamps
 *   importCollectionsToMaster()      - Imports collection tab data to master list
 *   fixEncoding()                    - Fixes mojibake in ALL text columns
 *
 * fillMissingData() per row:
 *   1. If TED Lesson URL exists - scrapes YouTube URL, Description, Author, Category
 *   2. If YouTube URL exists - fetches Transcript directly from YouTube (no third-party API)
 *   Never guesses or fabricates URLs.
 *
 * TRANSCRIPT APPROACH (v5.0):
 *   Fetches the YouTube watch page HTML, extracts captionTracks from
 *   ytInitialPlayerResponse, fetches the timedtext XML, and parses segments.
 *   This is the same approach used by the python youtube-transcript-api library.
 *   Replaced the broken subtitles-api.vercel.app dependency from v4.x.
 *
 * WORKFLOW:
 *   1. Paste a TED-Ed collection into a new tab
 *   2. Run importCollectionsToMaster()
 *   3. Run fillMissingData() (or fillMissingDataWithTimestamps())
 *   4. Run fixEncoding() if you see weird characters
 *
 * Columns detected dynamically by header keywords (partial, case-insensitive):
 *   title, collection, author, duration, views,
 *   category, ted lesson, youtube, description, tags, transcript
 */


// ===================================================================
// SHARED HELPERS
// ===================================================================

/**
 * Reads row 1 of a sheet and returns { keyword: 1-based column index }.
 * Returns empty object if sheet is null, empty, or has no columns.
 */
function getColumnMap(sheet, keywords) {
  var map = {};
  if (!sheet) return map;

  var lastCol = sheet.getLastColumn();
  if (lastCol < 1) return map;

  var headers = sheet.getRange(1, 1, 1, lastCol).getValues()[0];

  for (var k = 0; k < keywords.length; k++) {
    var kw = keywords[k].toLowerCase();
    for (var c = 0; c < headers.length; c++) {
      if (String(headers[c]).toLowerCase().indexOf(kw) !== -1) {
        map[keywords[k]] = c + 1;
        break;
      }
    }
  }
  return map;
}

/**
 * Extracts 11-char YouTube video ID from various URL formats.
 */
function extractVideoId(url) {
  if (!url) return null;
  var regExp = /^.*((youtu\.be\/)|(v\/)|(\/u\/\w\/)|(embed\/)|(watch\?))\??v?=?([^#&?]*).*/;
  var match = url.match(regExp);
  return (match && match[7] && match[7].length === 11) ? match[7] : null;
}

function formatTime(dateVal) {
  if (!(dateVal instanceof Date)) return String(dateVal);
  var h = dateVal.getHours();
  var m = dateVal.getMinutes();
  if (h > 0) return pad(h) + ":" + pad(m);
  var s = dateVal.getSeconds();
  return pad(m) + ":" + pad(s);
}

function pad(n) {
  return n < 10 ? "0" + n : String(n);
}

function getString(arr, idx) {
  if (idx >= arr.length) return "";
  var val = arr[idx];
  if (val === null || val === undefined) return "";
  if (val instanceof Date) return "";
  return String(val).trim();
}

/**
 * Fixes UTF-8 mojibake in a string.
 * All patterns use \u escapes so this .gs file has no raw multi-byte chars in code.
 */
function fixMojibake(text) {
  if (!text || typeof text !== "string" || text.length < 3) return text;

  // Pass 1: 3-byte mojibake (curly quotes, dashes, bullets)
  var multiByteMap = [
    ["\u00E2\u0080\u0099", "\u2019"],
    ["\u00E2\u0080\u0098", "\u2018"],
    ["\u00E2\u0080\u009C", "\u201C"],
    ["\u00E2\u0080\u009D", "\u201D"],
    ["\u00E2\u0080\u0094", "\u2014"],
    ["\u00E2\u0080\u0093", "\u2013"],
    ["\u00E2\u0080\u00A6", "\u2026"],
    ["\u00E2\u0080\u00A2", "\u2022"],
    ["\u00C2\u00A0", " "],
    ["\u00C2\u00B7", "\u00B7"]
  ];
  for (var i = 0; i < multiByteMap.length; i++) {
    text = text.split(multiByteMap[i][0]).join(multiByteMap[i][1]);
  }

  // Pass 2: 2-byte mojibake (accented Latin chars)
  var twoByteMap = [
    ["\u00C3\u00A1","\u00E1"],["\u00C3\u00A0","\u00E0"],["\u00C3\u00A2","\u00E2"],
    ["\u00C3\u00A3","\u00E3"],["\u00C3\u00A4","\u00E4"],["\u00C3\u00A5","\u00E5"],
    ["\u00C3\u00A6","\u00E6"],["\u00C3\u00A7","\u00E7"],["\u00C3\u00A8","\u00E8"],
    ["\u00C3\u00A9","\u00E9"],["\u00C3\u00AA","\u00EA"],["\u00C3\u00AB","\u00EB"],
    ["\u00C3\u00AC","\u00EC"],["\u00C3\u00AD","\u00ED"],["\u00C3\u00AE","\u00EE"],
    ["\u00C3\u00AF","\u00EF"],["\u00C3\u00B0","\u00F0"],["\u00C3\u00B1","\u00F1"],
    ["\u00C3\u00B2","\u00F2"],["\u00C3\u00B3","\u00F3"],["\u00C3\u00B4","\u00F4"],
    ["\u00C3\u00B5","\u00F5"],["\u00C3\u00B6","\u00F6"],["\u00C3\u00B8","\u00F8"],
    ["\u00C3\u00B9","\u00F9"],["\u00C3\u00BA","\u00FA"],["\u00C3\u00BB","\u00FB"],
    ["\u00C3\u00BC","\u00FC"],["\u00C3\u00BD","\u00FD"],["\u00C3\u00BF","\u00FF"],
    ["\u00C3\u0096","\u00D6"],["\u00C3\u009C","\u00DC"],["\u00C3\u0084","\u00C4"],
    ["\u00C3\u009F","\u00DF"]
  ];
  for (var j = 0; j < twoByteMap.length; j++) {
    text = text.split(twoByteMap[j][0]).join(twoByteMap[j][1]);
  }

  // Pass 3: stray \u00C2 prefix artifacts
  text = text.replace(/\u00C2(?=[^\s])/g, "");
  return text;
}

/**
 * Fetches a URL and returns HTML as UTF-8 string. Returns null on failure.
 */
function fetchPage(url) {
  try {
    var response = UrlFetchApp.fetch(url, {
      muteHttpExceptions: true,
      followRedirects: true
    });
    if (response.getResponseCode() !== 200) return null;
    return response.getContentText("UTF-8");
  } catch (e) {
    Logger.log("  fetchPage error: " + e.message);
    return null;
  }
}

/**
 * Decodes common HTML entities.
 */
function decodeHtmlEntities(str) {
  if (!str) return str;
  return str
    .replace(/&amp;/g, "&").replace(/&lt;/g, "<").replace(/&gt;/g, ">")
    .replace(/&quot;/g, '"').replace(/&#39;/g, "'").replace(/&#x27;/g, "'")
    .replace(/&apos;/g, "'").replace(/&#8217;/g, "\u2019")
    .replace(/&#8216;/g, "\u2018").replace(/&#8220;/g, "\u201C")
    .replace(/&#8221;/g, "\u201D").replace(/&#8212;/g, "\u2014")
    .replace(/&#8211;/g, "\u2013").replace(/&#8230;/g, "\u2026");
}


// ===================================================================
// TED-Ed PAGE SCRAPING
// ===================================================================

/**
 * Scrapes a TED-Ed lesson page. Returns:
 * { youtubeUrl, description, author, category } - any field may be null.
 */
function scrapeTedPage(tedUrl) {
  var result = { youtubeUrl: null, description: null, author: null, category: null };
  var html = fetchPage(tedUrl);
  if (!html) return result;

  // -- YouTube URL --
  var embedMatch = html.match(/youtube\.com\/embed\/([a-zA-Z0-9_-]{11})/);
  if (embedMatch) {
    result.youtubeUrl = "https://www.youtube.com/watch?v=" + embedMatch[1];
  }
  if (!result.youtubeUrl) {
    var watchMatch = html.match(/youtube\.com\/watch\?v=([a-zA-Z0-9_-]{11})/);
    if (watchMatch) {
      result.youtubeUrl = "https://www.youtube.com/watch?v=" + watchMatch[1];
    }
  }
  if (!result.youtubeUrl) {
    var shortMatch = html.match(/youtu\.be\/([a-zA-Z0-9_-]{11})/);
    if (shortMatch) {
      result.youtubeUrl = "https://www.youtube.com/watch?v=" + shortMatch[1];
    }
  }
  if (!result.youtubeUrl) {
    var dataMatch = html.match(/["']video_id["']\s*:\s*["']([a-zA-Z0-9_-]{11})["']/);
    if (dataMatch) {
      result.youtubeUrl = "https://www.youtube.com/watch?v=" + dataMatch[1];
    }
  }

  // -- Description --
  var metaMatch = html.match(/<meta\s+name=["']description["']\s+content=["']([^"']+)["']/i);
  if (metaMatch) {
    result.description = metaMatch[1];
  }
  if (!result.description) {
    var ogMatch = html.match(/<meta\s+property=["']og:description["']\s+content=["']([^"']+)["']/i);
    if (ogMatch) result.description = ogMatch[1];
  }
  if (!result.description) {
    var revMatch = html.match(/<meta\s+content=["']([^"']+)["']\s+name=["']description["']/i);
    if (revMatch) result.description = revMatch[1];
  }
  if (result.description) {
    result.description = fixMojibake(decodeHtmlEntities(result.description)).replace(/\s+/g, " ").trim();
  }

  // -- Author --
  var authorMeta = html.match(/<meta\s+name=["']author["']\s+content=["']([^"']+)["']/i);
  if (authorMeta) {
    result.author = decodeHtmlEntities(authorMeta[1]).trim();
  }
  if (!result.author) {
    var ogTitle = html.match(/<meta\s+property=["']og:title["']\s+content=["']([^"']+)["']/i);
    if (ogTitle) {
      var parts = ogTitle[1].split(" - ");
      if (parts.length >= 2) {
        var possibleAuthor = parts[parts.length - 1].trim();
        if (possibleAuthor.split(/\s+/).length <= 5 && !possibleAuthor.match(/TED-Ed|Lesson|Riddle/i)) {
          result.author = decodeHtmlEntities(possibleAuthor);
        }
      }
    }
  }

  // -- Category --
  var categoryMatch = html.match(/["']category["']\s*:\s*["']([^"']+)["']/i);
  if (categoryMatch) {
    result.category = decodeHtmlEntities(categoryMatch[1]).trim();
  }

  return result;
}


// ===================================================================
// YOUTUBE TRANSCRIPT FETCHING (direct, no third-party API)
// ===================================================================

/**
 * Fallback: fetch caption tracks via YouTube's Innertube API.
 * This is the POST-based internal API that youtube-transcript-api uses
 * in newer versions. More reliable than page scraping when YouTube
 * serves consent pages or changes HTML structure.
 *
 * Returns an array of caption track objects (same format as page-embedded
 * captionTracks), or null on failure.
 */
function fetchCaptionTracksViaInnertube(videoId) {
  var apiUrl = "https://www.youtube.com/youtubei/v1/player?key=AIzaSyA8eiZmM1FaDVjRy-df2KTyQ_vz_yYM39w";
  var payload = {
    "context": {
      "client": {
        "clientName": "WEB",
        "clientVersion": "2.20240101.00.00"
      }
    },
    "videoId": videoId
  };

  try {
    var response = UrlFetchApp.fetch(apiUrl, {
      method: "post",
      contentType: "application/json",
      payload: JSON.stringify(payload),
      muteHttpExceptions: true
    });

    if (response.getResponseCode() !== 200) {
      Logger.log("    Innertube API returned HTTP " + response.getResponseCode());
      return null;
    }

    var data = JSON.parse(response.getContentText("UTF-8"));

    if (data && data.captions &&
        data.captions.playerCaptionsTracklistRenderer &&
        data.captions.playerCaptionsTracklistRenderer.captionTracks) {
      var tracks = data.captions.playerCaptionsTracklistRenderer.captionTracks;
      Logger.log("    Innertube returned " + tracks.length + " caption track(s)");
      return tracks;
    }

    Logger.log("    Innertube response has no caption tracks");
    return null;
  } catch (e) {
    Logger.log("    Innertube API error: " + e.message);
    return null;
  }
}


/**
 * Fetches a YouTube transcript by scraping the watch page for caption track
 * URLs, then fetching the timedtext XML. This is the same approach used by
 * the python youtube-transcript-api library.
 *
 * If page scraping fails, falls back to the Innertube POST API.
 *
 * Returns { text: string, segments: [{text, start}] } or null if unavailable.
 * The segments array preserves timing data for optional timestamp support.
 */
function fetchTranscriptFromYouTube(videoId) {
  // Step 1: Fetch the YouTube watch page
  var watchUrl = "https://www.youtube.com/watch?v=" + videoId;
  Logger.log("    Fetching YouTube page: " + watchUrl);

  var response;
  try {
    response = UrlFetchApp.fetch(watchUrl, {
      muteHttpExceptions: true,
      followRedirects: true,
      headers: {
        "Accept-Language": "en-US,en;q=0.9",
        "Cookie": "CONSENT=YES+cb.20210328-17-p0.en+FX+999"
      }
    });
  } catch (e) {
    Logger.log("    Failed to fetch YouTube page: " + e.message);
    return null;
  }

  if (response.getResponseCode() !== 200) {
    Logger.log("    YouTube page returned HTTP " + response.getResponseCode());
    return null;
  }

  var html = response.getContentText("UTF-8");

  // Step 2: Extract captionTracks from ytInitialPlayerResponse
  // The JSON array is embedded in the page source
  var tracks = null;
  var captionMatch = html.match(/"captionTracks"\s*:\s*(\[.*?\])\s*[,\}]/);
  if (captionMatch) {
    try {
      tracks = JSON.parse(captionMatch[1]);
    } catch (e) {
      Logger.log("    Failed to parse captionTracks JSON from page: " + e.message);
    }
  }

  // Step 2b: Fallback to Innertube API if page scraping didn't find tracks
  // This is the same endpoint youtube-transcript-api uses internally
  if (!tracks || tracks.length === 0) {
    Logger.log("    Page scraping found no tracks, trying Innertube API...");
    tracks = fetchCaptionTracksViaInnertube(videoId);
  }

  if (!tracks || tracks.length === 0) {
    Logger.log("    No caption tracks found via any method");
    return null;
  }

  Logger.log("    Found " + tracks.length + " caption track(s)");

  // Step 3: Find the best English track (prefer manual captions over ASR)
  var track = null;
  // First pass: manual English captions
  for (var i = 0; i < tracks.length; i++) {
    if (tracks[i].languageCode === "en" && tracks[i].kind !== "asr") {
      track = tracks[i];
      Logger.log("    Using manual English captions");
      break;
    }
  }
  // Second pass: auto-generated English
  if (!track) {
    for (var j = 0; j < tracks.length; j++) {
      if (tracks[j].languageCode === "en") {
        track = tracks[j];
        Logger.log("    Using auto-generated English captions");
        break;
      }
    }
  }
  // Fallback: first available track
  if (!track) {
    track = tracks[0];
    Logger.log("    No English track found, using: " + (track.languageCode || "unknown"));
  }

  // Step 4: Fetch the timedtext XML from the caption track baseUrl
  var baseUrl = track.baseUrl;
  if (!baseUrl) {
    Logger.log("    Caption track has no baseUrl");
    return null;
  }
  // Decode escaped ampersands that may appear in the JSON
  baseUrl = baseUrl.replace(/\\u0026/g, "&").replace(/&amp;/g, "&");

  var xmlResponse;
  try {
    xmlResponse = UrlFetchApp.fetch(baseUrl, { muteHttpExceptions: true });
  } catch (e) {
    Logger.log("    Failed to fetch timedtext: " + e.message);
    return null;
  }

  if (xmlResponse.getResponseCode() !== 200) {
    Logger.log("    Timedtext returned HTTP " + xmlResponse.getResponseCode());
    return null;
  }

  var xml = xmlResponse.getContentText("UTF-8");

  // Step 5: Parse the XML to extract text segments with timing
  var segments = [];
  var re = /<text[^>]*start="([^"]*)"[^>]*>([\s\S]*?)<\/text>/g;
  var m;
  while ((m = re.exec(xml)) !== null) {
    var startSec = parseFloat(m[1]) || 0;
    var text = m[2]
      .replace(/&amp;/g, "&")
      .replace(/&lt;/g, "<")
      .replace(/&gt;/g, ">")
      .replace(/&quot;/g, '"')
      .replace(/&#39;/g, "'")
      .replace(/\n/g, " ")
      .trim();
    if (text) {
      segments.push({ text: text, start: startSec });
    }
  }

  if (segments.length === 0) {
    Logger.log("    Parsed 0 text segments from timedtext XML");
    return null;
  }

  // Join all text segments into a single string
  var fullText = [];
  for (var k = 0; k < segments.length; k++) {
    fullText.push(segments[k].text);
  }

  Logger.log("    Parsed " + segments.length + " segments (" + fullText.join(" ").length + " chars)");

  return {
    text: fullText.join(" "),
    segments: segments
  };
}

/**
 * Formats transcript segments with [M:SS] timestamps.
 * Used by fillMissingDataWithTimestamps().
 */
function formatTranscriptWithTimestamps(segments) {
  var lines = [];
  for (var i = 0; i < segments.length; i++) {
    var s = segments[i];
    var minutes = Math.floor(s.start / 60);
    var seconds = Math.floor(s.start % 60);
    lines.push("[" + minutes + ":" + pad(seconds) + "] " + s.text);
  }
  return lines.join("\n");
}


// ===================================================================
// 1. FILL MISSING DATA
// ===================================================================

/**
 * For each row, fills in whatever is missing using ONLY URLs you provide.
 *
 *   TED Lesson URL present -> YouTube URL, Description, Author, Category
 *   YouTube URL present    -> Transcript
 *   Both URLs              -> fills everything above
 *
 * Run this on the master list tab.
 */
function fillMissingData() {
  var sheet = SpreadsheetApp.getActiveSpreadsheet().getActiveSheet();
  var sheetName = sheet.getName();

  // Validate sheet has data
  if (sheet.getLastRow() < 2 || sheet.getLastColumn() < 1) {
    Logger.log("ERROR: Sheet '" + sheetName + "' appears empty. Select the master list tab and try again.");
    return;
  }

  var cols = getColumnMap(sheet, [
    "title", "collection", "author", "duration", "views",
    "category", "ted lesson", "youtube", "description",
    "tags", "transcript"
  ]);

  Logger.log("Column map for '" + sheetName + "': " + JSON.stringify(cols));

  if (!cols["title"]) {
    Logger.log("ERROR: No 'Title' column found in '" + sheetName + "'. Is this the master list tab?");
    return;
  }

  var lastRow = sheet.getLastRow();
  var stats = { ytUrl: 0, desc: 0, author: 0, category: 0, transcript: 0, skipped: 0, errors: 0 };

  for (var i = 2; i <= lastRow; i++) {
    var title = cols["title"] ? sheet.getRange(i, cols["title"]).getValue().toString().trim() : "";
    if (!title) { stats.skipped++; continue; }

    var tedUrl = cols["ted lesson"] ? sheet.getRange(i, cols["ted lesson"]).getValue().toString().trim() : "";
    var ytUrl = cols["youtube"] ? sheet.getRange(i, cols["youtube"]).getValue().toString().trim() : "";
    var desc = cols["description"] ? sheet.getRange(i, cols["description"]).getValue().toString().trim() : "";
    var author = cols["author"] ? sheet.getRange(i, cols["author"]).getValue().toString().trim() : "";
    var category = cols["category"] ? sheet.getRange(i, cols["category"]).getValue().toString().trim() : "";
    var transcript = cols["transcript"] ? sheet.getRange(i, cols["transcript"]).getValue().toString().trim() : "";

    Logger.log("Row " + i + ": " + title);

    // -- Step 1: Scrape TED page if we have a URL and need anything from it --
    var needFromTed = (!ytUrl && cols["youtube"]) ||
                      (!desc && cols["description"]) ||
                      (!author && cols["author"]) ||
                      (!category && cols["category"]);

    if (tedUrl && tedUrl.match(/^https?:\/\//) && needFromTed) {
      Logger.log("  Scraping TED page...");
      var tedPageData = scrapeTedPage(tedUrl);
      Utilities.sleep(1000);

      if (!ytUrl && cols["youtube"] && tedPageData.youtubeUrl) {
        ytUrl = tedPageData.youtubeUrl;
        sheet.getRange(i, cols["youtube"]).setValue(ytUrl);
        stats.ytUrl++;
        Logger.log("  Found YouTube URL: " + ytUrl);
      }

      if (!desc && cols["description"] && tedPageData.description) {
        desc = tedPageData.description;
        sheet.getRange(i, cols["description"]).setValue(desc);
        stats.desc++;
        Logger.log("  Got description (" + desc.length + " chars)");
      }

      if (!author && cols["author"] && tedPageData.author) {
        author = tedPageData.author;
        sheet.getRange(i, cols["author"]).setValue(author);
        stats.author++;
        Logger.log("  Got author: " + author);
      }

      if (!category && cols["category"] && tedPageData.category) {
        category = tedPageData.category;
        sheet.getRange(i, cols["category"]).setValue(category);
        stats.category++;
        Logger.log("  Got category: " + category);
      }
    }

    // -- Step 2: Fetch transcript if missing and we have a YouTube URL --
    if (!transcript && cols["transcript"] && ytUrl) {
      var videoId = extractVideoId(ytUrl);
      if (videoId) {
        Logger.log("  Fetching transcript for " + videoId + "...");
        try {
          var result = fetchTranscriptFromYouTube(videoId);
          if (result && result.text) {
            var fullText = fixMojibake(result.text);
            sheet.getRange(i, cols["transcript"]).setValue(fullText.substring(0, 49000));
            stats.transcript++;
            Logger.log("  Got transcript (" + fullText.length + " chars)");
          } else {
            Logger.log("  No transcript available for " + videoId);
          }
        } catch (e) {
          Logger.log("  Transcript error: " + e.message);
          stats.errors++;
        }
        Utilities.sleep(1000); // Rate limit YouTube page fetches
      }
    }

  }

  Logger.log("");
  Logger.log("===================================");
  Logger.log("fillMissingData complete!");
  Logger.log("  YouTube URLs found:    " + stats.ytUrl);
  Logger.log("  Descriptions scraped:  " + stats.desc);
  Logger.log("  Authors found:         " + stats.author);
  Logger.log("  Categories found:      " + stats.category);
  Logger.log("  Transcripts fetched:   " + stats.transcript);
  Logger.log("  Rows skipped (empty):  " + stats.skipped);
  Logger.log("  Errors:                " + stats.errors);
  Logger.log("===================================");
}


/**
 * Same as fillMissingData() but writes transcripts with [M:SS] timestamps.
 * Each line becomes: [0:05] Ideas change everything
 * Useful for finding specific moments in the video.
 * Note: timestamped transcripts use more characters per cell.
 */
function fillMissingDataWithTimestamps() {
  var sheet = SpreadsheetApp.getActiveSpreadsheet().getActiveSheet();
  var sheetName = sheet.getName();

  if (sheet.getLastRow() < 2 || sheet.getLastColumn() < 1) {
    Logger.log("ERROR: Sheet '" + sheetName + "' appears empty. Select the master list tab and try again.");
    return;
  }

  var cols = getColumnMap(sheet, ["title", "youtube", "transcript"]);

  if (!cols["title"]) {
    Logger.log("ERROR: No 'Title' column found in '" + sheetName + "'.");
    return;
  }
  if (!cols["transcript"]) {
    Logger.log("ERROR: No 'Transcript' column found in '" + sheetName + "'.");
    return;
  }

  var lastRow = sheet.getLastRow();
  var fetched = 0;
  var errors = 0;

  for (var i = 2; i <= lastRow; i++) {
    var title = sheet.getRange(i, cols["title"]).getValue().toString().trim();
    if (!title) continue;

    var ytUrl = cols["youtube"] ? sheet.getRange(i, cols["youtube"]).getValue().toString().trim() : "";
    var transcript = sheet.getRange(i, cols["transcript"]).getValue().toString().trim();

    if (transcript || !ytUrl) continue;

    var videoId = extractVideoId(ytUrl);
    if (!videoId) continue;

    Logger.log("Row " + i + ": " + title);
    Logger.log("  Fetching transcript with timestamps for " + videoId + "...");

    try {
      var result = fetchTranscriptFromYouTube(videoId);
      if (result && result.segments && result.segments.length > 0) {
        var timestamped = formatTranscriptWithTimestamps(result.segments);
        timestamped = fixMojibake(timestamped);
        sheet.getRange(i, cols["transcript"]).setValue(timestamped.substring(0, 49000));
        fetched++;
        Logger.log("  Got timestamped transcript (" + timestamped.length + " chars, " + result.segments.length + " segments)");
      } else {
        Logger.log("  No transcript available for " + videoId);
      }
    } catch (e) {
      Logger.log("  Transcript error: " + e.message);
      errors++;
    }
    Utilities.sleep(1000);
  }

  Logger.log("");
  Logger.log("===================================");
  Logger.log("fillMissingDataWithTimestamps complete!");
  Logger.log("  Transcripts fetched: " + fetched);
  Logger.log("  Errors:              " + errors);
  Logger.log("===================================");
}


// ===================================================================
// 2. IMPORT COLLECTIONS TO MASTER
// ===================================================================

/**
 * Scans every tab for TED-Ed Collection data and appends new rows
 * to the master list tab, skipping duplicates by Title.
 */
function importCollectionsToMaster() {
  var ss = SpreadsheetApp.getActiveSpreadsheet();
  var masterName = "TED-Ed Riddles Master List";
  var masterSheet = ss.getSheetByName(masterName);

  if (!masterSheet) {
    Logger.log("ERROR: Master sheet '" + masterName + "' not found. Check the tab name and try again.");
    return;
  }

  if (masterSheet.getLastColumn() < 1) {
    Logger.log("ERROR: Master sheet '" + masterName + "' has no columns. Add headers first.");
    return;
  }

  var cols = getColumnMap(masterSheet, [
    "title", "collection", "author", "duration", "views",
    "category", "ted lesson", "youtube", "description",
    "tags", "transcript"
  ]);

  Logger.log("Detected master columns: " + JSON.stringify(cols));

  if (!cols["title"]) {
    Logger.log("ERROR: No 'Title' column found in master sheet header.");
    return;
  }

  var titleCol = cols["title"];
  var totalCols = masterSheet.getLastColumn();

  var masterData = masterSheet.getDataRange().getValues();
  var existingTitles = {};
  for (var i = 1; i < masterData.length; i++) {
    var title = String(masterData[i][titleCol - 1]).trim().toLowerCase();
    if (title) existingTitles[title] = true;
  }
  Logger.log("Master list has " + Object.keys(existingTitles).length + " existing titles.");

  var allSheets = ss.getSheets();
  var totalAdded = 0;

  for (var s = 0; s < allSheets.length; s++) {
    var tab = allSheets[s];
    var tabName = tab.getName();
    if (tabName === masterName || tabName === "Summary") continue;

    var maxRow = tab.getLastRow();
    if (maxRow < 7) continue;

    var vals = tab.getRange("A1:A4").getValues();
    var isCollection =
      String(vals[0][0]).trim() === "TED-Ed Collections" &&
      String(vals[2][0]).trim() === "Collection";

    if (!isCollection) {
      Logger.log("Skipping '" + tabName + "' - not a collection tab.");
      continue;
    }

    var collectionName = String(vals[3][0]).trim();
    Logger.log("Processing collection: '" + collectionName + "' (tab: " + tabName + ")");

    var colA = tab.getRange(1, 1, maxRow, 1).getValues();
    var colAFlat = [];
    for (var r = 0; r < colA.length; r++) colAFlat.push(colA[r][0]);

    var lessons = [];
    var idx = 6;

    while (idx < colAFlat.length) {
      var cellVal = colAFlat[idx];

      if (cellVal instanceof Date) {
        var duration = formatTime(cellVal);
        var category = getString(colAFlat, idx + 1);
        var lessonTitle = getString(colAFlat, idx + 2);

        var views = "";
        for (var j = idx + 3; j < Math.min(idx + 8, colAFlat.length); j++) {
          var v = String(colAFlat[j] || "");
          if (v.match(/[\d,]+\s*Views/i)) {
            views = v.replace(/\s*Views\s*/i, "").trim();
            break;
          }
        }

        if (lessonTitle) {
          lessons.push({
            title: lessonTitle,
            collection: collectionName,
            duration: duration,
            views: views,
            category: category
          });
        }

        idx += 5;
        continue;
      }
      idx++;
    }

    Logger.log("  Found " + lessons.length + " lessons in '" + collectionName + "'.");

    var addedFromTab = 0;
    for (var l = 0; l < lessons.length; l++) {
      var lesson = lessons[l];
      var titleKey = lesson.title.trim().toLowerCase();
      if (existingTitles[titleKey]) {
        Logger.log("  Already exists: '" + lesson.title + "'");
        continue;
      }

      var row = [];
      for (var c = 0; c < totalCols; c++) row.push("");

      if (cols["title"])      row[cols["title"] - 1]      = lesson.title;
      if (cols["collection"]) row[cols["collection"] - 1] = lesson.collection;
      if (cols["duration"])   row[cols["duration"] - 1]   = lesson.duration;
      if (cols["views"])      row[cols["views"] - 1]      = lesson.views;
      if (cols["category"])   row[cols["category"] - 1]   = lesson.category;
      if (cols["tags"])       row[cols["tags"] - 1]       = lesson.category;

      masterSheet.appendRow(row);
      existingTitles[titleKey] = true;
      addedFromTab++;
      Logger.log("  Added: '" + lesson.title + "'");
    }

    totalAdded += addedFromTab;
    Logger.log("  Added " + addedFromTab + " new rows from '" + collectionName + "'.");
  }

  Logger.log("Import done! Total new rows added: " + totalAdded);
}


// ===================================================================
// 3. EXPORT MASTER LIST TO CSV
// ===================================================================

/**
 * Exports the master list as a CSV string and saves it to Google Drive.
 * The CSV can then be committed to GitHub manually or via automation.
 *
 * This enables:
 *   - Version-controlled snapshots of the database in GitHub
 *   - Other tools (Python scripts, web apps) to read the data without Sheets API auth
 *   - Google Sheets IMPORTDATA() from the GitHub raw URL for read-only copies
 *
 * The exported file is saved to the root of Google Drive as "ted_ed_master_list.csv".
 * After running, download the file and commit it to the GitHub repository.
 */
function exportMasterListToCSV() {
  var ss = SpreadsheetApp.getActiveSpreadsheet();
  var masterName = "TED-Ed Riddles Master List";
  var masterSheet = ss.getSheetByName(masterName);

  if (!masterSheet) {
    masterSheet = ss.getActiveSheet();
    Logger.log("Using active sheet: " + masterSheet.getName());
  }

  var lastRow = masterSheet.getLastRow();
  var lastCol = masterSheet.getLastColumn();

  if (lastRow < 1 || lastCol < 1) {
    Logger.log("ERROR: Sheet is empty.");
    return;
  }

  var data = masterSheet.getRange(1, 1, lastRow, lastCol).getValues();
  var csvLines = [];

  for (var r = 0; r < data.length; r++) {
    var row = [];
    for (var c = 0; c < data[r].length; c++) {
      var val = data[r][c];
      if (val instanceof Date) {
        val = formatTime(val);
      }
      val = String(val === null || val === undefined ? "" : val);
      // CSV escaping: quote fields that contain commas, quotes, or newlines
      if (val.indexOf(",") !== -1 || val.indexOf('"') !== -1 || val.indexOf("\n") !== -1) {
        val = '"' + val.replace(/"/g, '""') + '"';
      }
      row.push(val);
    }
    csvLines.push(row.join(","));
  }

  var csvContent = csvLines.join("\n");
  var fileName = "ted_ed_master_list.csv";

  // Save to Google Drive
  var existingFiles = DriveApp.getFilesByName(fileName);
  if (existingFiles.hasNext()) {
    var file = existingFiles.next();
    file.setContent(csvContent);
    Logger.log("Updated existing file: " + fileName + " (" + csvContent.length + " bytes)");
    Logger.log("File URL: " + file.getUrl());
  } else {
    var newFile = DriveApp.createFile(fileName, csvContent, "text/csv");
    Logger.log("Created new file: " + fileName + " (" + csvContent.length + " bytes)");
    Logger.log("File URL: " + newFile.getUrl());
  }

  Logger.log("Export complete! " + lastRow + " rows, " + lastCol + " columns.");
  Logger.log("Download the file from Google Drive and commit to GitHub.");
}


// ===================================================================
// 4. FIX ENCODING IN ALL TEXT COLUMNS
// ===================================================================

/**
 * Scans ALL cells in the active sheet and fixes UTF-8 mojibake.
 * Works on any column, auto-expands if you add columns.
 * Safe to run repeatedly - leaves clean text untouched.
 */
function fixEncoding() {
  var sheet = SpreadsheetApp.getActiveSpreadsheet().getActiveSheet();
  var sheetName = sheet.getName();
  var lastRow = sheet.getLastRow();
  var lastCol = sheet.getLastColumn();

  if (lastRow < 2 || lastCol < 1) {
    Logger.log("ERROR: Sheet '" + sheetName + "' appears empty.");
    return;
  }

  var range = sheet.getRange(2, 1, lastRow - 1, lastCol);
  var data = range.getValues();
  var fixedCells = 0;
  var changed = false;

  for (var r = 0; r < data.length; r++) {
    for (var c = 0; c < data[r].length; c++) {
      var val = data[r][c];
      if (typeof val !== "string" || val.length < 3) continue;

      var fixed = fixMojibake(val);
      if (fixed !== val) {
        data[r][c] = fixed;
        fixedCells++;
        changed = true;
      }
    }
  }

  if (changed) {
    range.setValues(data);
    Logger.log("Fixed encoding in " + fixedCells + " cells across '" + sheetName + "'.");
  } else {
    Logger.log("No mojibake found - all cells in '" + sheetName + "' are clean.");
  }
}
