"""
Google Drive / Docs / Sheets / Slides MCP server.
"""

import json
import logging
import os
from pathlib import Path

import googleapiclient.discovery
logging.getLogger("googleapiclient.discovery_cache").setLevel(logging.ERROR)

from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from mcp.server.fastmcp import FastMCP

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

BASE_DIR = Path(__file__).parent
CREDENTIALS_FILE = BASE_DIR / "credentials.json"
TOKEN_FILE = BASE_DIR / "token.json"
DEFAULT_FOLDER_ID = os.getenv("GDRIVE_DEFAULT_FOLDER_ID", "")  # set in .env, or pass folder_id explicitly per call

SCOPES = [
    "https://www.googleapis.com/auth/drive",
    "https://www.googleapis.com/auth/documents",
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/presentations",
]

# ---------------------------------------------------------------------------
# Google API clients
# ---------------------------------------------------------------------------

def _clients():
    creds = None
    if TOKEN_FILE.exists():
        creds = Credentials.from_authorized_user_file(str(TOKEN_FILE), SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(str(CREDENTIALS_FILE), SCOPES)
            creds = flow.run_local_server(port=0)
        TOKEN_FILE.write_text(creds.to_json())
    drive = build("drive", "v3", credentials=creds)
    docs = build("docs", "v1", credentials=creds)
    sheets = build("sheets", "v4", credentials=creds)
    slides = build("slides", "v1", credentials=creds)
    return drive, docs, sheets, slides

# ---------------------------------------------------------------------------
# MCP server
# ---------------------------------------------------------------------------

mcp = FastMCP("gdrive")

# --- Drive ---

@mcp.tool()
def list_drive_files(folder_id: str = DEFAULT_FOLDER_ID, mime_filter: str = "") -> str:
    """List all files in a Drive folder. Returns JSON array of {id, name, mimeType}."""
    drive, _, _, _ = _clients()
    # Escape single quotes in user-supplied values to prevent Drive query injection.
    safe_folder_id = folder_id.replace("'", "\\'")
    query = f"'{safe_folder_id}' in parents and trashed = false"
    if mime_filter:
        safe_mime = mime_filter.replace("'", "\\'")
        query += f" and mimeType = '{safe_mime}'"

    files = []
    page_token = None
    while True:
        params = dict(q=query, pageSize=100, fields="nextPageToken, files(id, name, mimeType)", supportsAllDrives=True, includeItemsFromAllDrives=True)
        if page_token:
            params["pageToken"] = page_token
        res = drive.files().list(**params).execute()
        files.extend(res.get("files", []))
        page_token = res.get("nextPageToken")
        if not page_token:
            break

    return json.dumps(files, indent=2)


@mcp.tool()
def read_drive_file(file_id: str) -> str:
    """Export a Google Workspace file (Doc, Sheet, Slides) as plain text, extract text from a PDF, or download a binary file."""
    import io
    from googleapiclient.http import MediaIoBaseDownload

    drive, _, _, _ = _clients()
    meta = drive.files().get(fileId=file_id, fields="mimeType, name", supportsAllDrives=True).execute()
    mime = meta["mimeType"]

    export_map = {
        "application/vnd.google-apps.document": "text/plain",
        "application/vnd.google-apps.spreadsheet": "text/csv",
        "application/vnd.google-apps.presentation": "text/plain",
    }

    if mime in export_map:
        buf = io.BytesIO()
        req = drive.files().export_media(fileId=file_id, mimeType=export_map[mime])
        downloader = MediaIoBaseDownload(buf, req)
        done = False
        while not done:
            _, done = downloader.next_chunk()
        return buf.getvalue().decode("utf-8", errors="replace")

    # Download the file as bytes
    buf = io.BytesIO()
    req = drive.files().get_media(fileId=file_id)
    downloader = MediaIoBaseDownload(buf, req)
    done = False
    while not done:
        _, done = downloader.next_chunk()

    # Extract text from PDFs
    if mime == "application/pdf":
        from pypdf import PdfReader
        buf.seek(0)
        reader = PdfReader(buf)
        pages = []
        for i, page in enumerate(reader.pages, 1):
            text = page.extract_text() or ""
            if text.strip():
                pages.append(f"--- Page {i} ---\n{text}")
        return "\n\n".join(pages)

    return buf.getvalue().decode("utf-8", errors="replace")


# --- Docs ---

@mcp.tool()
def read_doc_text(doc_id: str) -> str:
    """Extract and return the plain text body of a Google Doc."""
    _, docs, _, _ = _clients()
    doc = docs.documents().get(documentId=doc_id).execute()
    parts = []
    for element in doc.get("body", {}).get("content", []):
        for pe in element.get("paragraph", {}).get("elements", []):
            text = pe.get("textRun", {}).get("content", "")
            if text:
                parts.append(text)
    return "".join(parts)


@mcp.tool()
def create_doc(title: str, folder_id: str = DEFAULT_FOLDER_ID) -> str:
    """Create a blank Google Doc in the specified Drive folder. Returns the new document ID."""
    drive, _, _, _ = _clients()
    file_metadata = {
        "name": title,
        "mimeType": "application/vnd.google-apps.document",
        "parents": [folder_id],
    }
    doc_res = drive.files().create(body=file_metadata, fields="id").execute()
    return doc_res["id"]


@mcp.tool()
def create_doc_from_markdown(title: str, markdown: str, folder_id: str = DEFAULT_FOLDER_ID) -> str:
    """Create a formatted Google Doc from Markdown content.

    Uses the Drive API to upload the Markdown as text/markdown and convert it
    to a native Google Doc (application/vnd.google-apps.document), preserving
    headings, bold, italic, lists, code blocks, and other Markdown formatting.

    title: display name for the new document
    markdown: full Markdown content to convert (encoded as UTF-8)
    folder_id: Drive folder ID where the doc will be created (defaults to DEFAULT_FOLDER_ID)

    Returns the new document ID.
    """
    import io
    from googleapiclient.http import MediaIoBaseUpload

    drive, _, _, _ = _clients()
    file_metadata = {
        "name": title,
        "mimeType": "application/vnd.google-apps.document",
        "parents": [folder_id],
    }
    media = MediaIoBaseUpload(
        io.BytesIO(markdown.encode("utf-8")),
        mimetype="text/markdown",
        resumable=False,
    )
    doc_res = drive.files().create(
        body=file_metadata,
        media_body=media,
        fields="id",
    ).execute()
    return doc_res["id"]


@mcp.tool()
def export_doc_as_markdown(doc_id: str) -> str:
    """Export a Google Doc as Markdown text.

    Uses the Drive API Files:export method with mimeType text/markdown to return
    the document content as a Markdown string.

    doc_id: the Google Doc file ID (from the URL or a prior create/list call)

    Returns the document content as a Markdown string. Invalid UTF-8 bytes are
    replaced with the Unicode replacement character rather than raising an error.
    """
    import io
    from googleapiclient.http import MediaIoBaseDownload

    drive, _, _, _ = _clients()
    buf = io.BytesIO()
    req = drive.files().export_media(fileId=doc_id, mimeType="text/markdown")
    downloader = MediaIoBaseDownload(buf, req)
    done = False
    while not done:
        status, done = downloader.next_chunk()
        if status:
            logging.debug("export_doc_as_markdown: download %d%%", int(status.progress() * 100))
    return buf.getvalue().decode("utf-8", errors="replace")


@mcp.tool()
def write_doc(doc_id: str, content: str) -> str:
    """Replace the entire body of a Google Doc with new plain text content."""
    _, docs, _, _ = _clients()

    # Clear existing content
    doc = docs.documents().get(documentId=doc_id).execute()
    body_content = doc.get("body", {}).get("content", [])
    end_index = body_content[-1]["endIndex"] if body_content else 1
    if end_index > 2:
        docs.documents().batchUpdate(
            documentId=doc_id,
            body={"requests": [{"deleteContentRange": {"range": {"startIndex": 1, "endIndex": end_index - 1}}}]},
        ).execute()

    # Insert content in chunks to avoid request size limits
    chunk_size = 40000
    chunks = [content[i:i + chunk_size] for i in range(0, len(content), chunk_size)]
    insert_index = 1
    for chunk in chunks:
        docs.documents().batchUpdate(
            documentId=doc_id,
            body={"requests": [{"insertText": {"location": {"index": insert_index}, "text": chunk}}]},
        ).execute()
        insert_index += len(chunk)

    return "ok"


@mcp.tool()
def append_doc(doc_id: str, content: str) -> str:
    """Append text to the end of a Google Doc."""
    _, docs, _, _ = _clients()
    doc = docs.documents().get(documentId=doc_id).execute()
    body_content = doc.get("body", {}).get("content", [])
    end_index = body_content[-1]["endIndex"] if body_content else 1

    docs.documents().batchUpdate(
        documentId=doc_id,
        body={"requests": [{"insertText": {"location": {"index": end_index - 1}, "text": content}}]},
    ).execute()
    return "ok"


@mcp.tool()
def get_doc_structure(doc_id: str) -> str:
    """Return the paragraph structure of a Google Doc as JSON.

    Use this after write_doc to get the exact character indices of each paragraph
    before applying formatting with batch_update_doc.
    Returns a JSON array of {startIndex, endIndex, text} for each paragraph.
    """
    _, docs, _, _ = _clients()
    doc = docs.documents().get(documentId=doc_id).execute()
    body_content = doc.get("body", {}).get("content", [])
    simplified = []
    for element in body_content:
        para = element.get("paragraph")
        if para:
            text = "".join(
                pe.get("textRun", {}).get("content", "")
                for pe in para.get("elements", [])
            )
            simplified.append({
                "startIndex": element.get("startIndex"),
                "endIndex": element.get("endIndex"),
                "text": text,
            })
    return json.dumps(simplified, indent=2)


@mcp.tool()
def batch_update_doc(doc_id: str, requests: list) -> str:
    """Apply a list of Google Docs API batchUpdate requests to a document.

    Use this to apply rich formatting after inserting text with write_doc.
    Each item in `requests` is a dict matching the Google Docs API batchUpdate
    request schema, e.g. updateParagraphStyle, updateTextStyle, createParagraphBullets.

    Returns the raw API response as JSON.
    """
    _, docs, _, _ = _clients()
    response = docs.documents().batchUpdate(
        documentId=doc_id,
        body={"requests": requests},
    ).execute()
    return json.dumps(response, indent=2)


@mcp.tool()
def get_doc_images(doc_id: str, output_dir: str = "/tmp") -> str:
    """Extract all embedded images from a Google Doc and save them to output_dir.

    Exports the doc as HTML (which embeds images as base64 data URIs), decodes
    each image, writes it to a file, and returns metadata for each image.

    Returns a JSON array of objects, one per image, with:
      - file_path: absolute path of the saved PNG file
      - size_bytes: file size in bytes
      - preceding_text: up to 300 chars of plain text immediately before the image
      - following_text: up to 300 chars of plain text immediately after the image

    Use preceding_text and following_text to identify the correct insertion point
    in the converted DocBook XML when building the <mediaobject> block.
    """
    import io, re, base64
    from googleapiclient.http import MediaIoBaseDownload

    drive, _, _, _ = _clients()

    buf = io.BytesIO()
    req = drive.files().export_media(fileId=doc_id, mimeType="text/html")
    downloader = MediaIoBaseDownload(buf, req)
    done = False
    while not done:
        _, done = downloader.next_chunk()
    html = buf.getvalue().decode("utf-8", errors="replace")

    def strip_tags(s):
        return re.sub(r"<[^>]+>", "", s).strip()

    img_pattern = re.compile(
        r'src="data:image/(?:png|jpeg|gif|webp);base64,([A-Za-z0-9+/=]+)"'
    )
    parts = img_pattern.split(html)
    img_count = (len(parts) - 1) // 2

    out_path = Path(output_dir)
    out_path.mkdir(parents=True, exist_ok=True)

    results = []
    for i in range(img_count):
        b64 = parts[i * 2 + 1]
        preceding_html = parts[i * 2][-3000:]
        following_html = parts[i * 2 + 2][:3000] if i * 2 + 2 < len(parts) else ""

        img_bytes = base64.b64decode(b64)
        file_path = out_path / f"doc-image-{i}.png"
        file_path.write_bytes(img_bytes)

        results.append({
            "file_path": str(file_path),
            "size_bytes": len(img_bytes),
            "preceding_text": strip_tags(preceding_html)[-300:],
            "following_text": strip_tags(following_html)[:300],
        })

    return json.dumps(results, indent=2)


# --- Sheets ---

@mcp.tool()
def read_sheet(spreadsheet_id: str, range: str = "Sheet1") -> str:
    """Read values from a Google Sheet range. Returns JSON 2-D array."""
    _, _, sheets, _ = _clients()
    res = sheets.spreadsheets().values().get(
        spreadsheetId=spreadsheet_id, range=range
    ).execute()
    return json.dumps(res.get("values", []), indent=2)


@mcp.tool()
def write_sheet(spreadsheet_id: str, range: str, values: list) -> str:
    """Write values to a Google Sheet range. values is a 2-D array."""
    _, _, sheets, _ = _clients()
    res = sheets.spreadsheets().values().update(
        spreadsheetId=spreadsheet_id,
        range=range,
        valueInputOption="USER_ENTERED",
        body={"values": values},
    ).execute()
    return json.dumps(res, indent=2)


# --- Slides ---

@mcp.tool()
def read_slides_text(presentation_id: str) -> str:
    """Extract all visible text from a Google Slides presentation."""
    _, _, _, slides = _clients()
    pres = slides.presentations().get(presentationId=presentation_id).execute()
    parts = []
    for i, slide in enumerate(pres.get("slides", []), 1):
        parts.append(f"--- Slide {i} ---")
        for element in slide.get("pageElements", []):
            for text_el in element.get("shape", {}).get("text", {}).get("textElements", []):
                text = text_el.get("textRun", {}).get("content", "")
                if text:
                    parts.append(text)
    return "\n".join(parts)


# ---------------------------------------------------------------------------

if __name__ == "__main__":
    mcp.run()
    