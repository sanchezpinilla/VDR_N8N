import os, json, re
from io import BytesIO
from typing import List
from pypdf import PdfReader, PdfWriter
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload, MediaIoBaseUpload
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request

def user_drive():
    client_id     = os.environ["GOOGLE_CLIENT_ID"]
    client_secret = os.environ["GOOGLE_CLIENT_SECRET"]
    refresh_token = os.environ["GOOGLE_REFRESH_TOKEN"]
    creds = Credentials(
        token=None,
        refresh_token=refresh_token,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=client_id,
        client_secret=client_secret,
        scopes=["https://www.googleapis.com/auth/drive"],
    )
    creds.refresh(Request())
    return build("drive", "v3", credentials=creds, cache_discovery=False)

def parse_start_pages(val: str) -> List[int]:
    if not val: return []
    s = val.strip()
    if s.startswith("["):
        try:
            arr = json.loads(s)
        except Exception:
            arr = re.split(r"[^\d]+", s)
    else:
        arr = re.split(r"[,\s;|]+", s)
    arr = [int(x) for x in arr if str(x).isdigit()]
    arr = sorted(set([n for n in arr if n > 0]))
    return arr

def main():
    file_id = os.environ["FILE_ID"]
    output_folder_id = os.environ["OUTPUT_FOLDER_ID"]
    start_pages_raw = os.environ.get("START_PAGES","")
    name_prefix = os.environ.get("NAME_PREFIX","").strip()

    drive = user_drive()

    meta = drive.files().get(fileId=file_id, fields="id,name,parents").execute()
    source_name = meta.get("name","documento.pdf")
    if not name_prefix:
        name_prefix = re.sub(r"\.pdf$", "", source_name, flags=re.I)

    buf = BytesIO()
    req = drive.files().get_media(fileId=file_id)
    dl = MediaIoBaseDownload(buf, req)
    done = False
    while not done:
        status, done = dl.next_chunk()
    buf.seek(0)

    reader = PdfReader(buf)
    total = len(reader.pages)

    start_pages = parse_start_pages(start_pages_raw) or [1]
    start_pages = [p for p in start_pages if 1 <= p <= total]
    if 1 not in start_pages:
        start_pages = [1] + start_pages
    start_pages = sorted(set(start_pages))

    ranges = []
    for i, start in enumerate(start_pages):
        end = total if i == len(start_pages)-1 else start_pages[i+1]-1
        if start <= end:
            ranges.append((start, end))

    print(f"Origen: {source_name} ({total} páginas). Rangos: {ranges}")

    for (start, end) in ranges:
        writer = PdfWriter()
        for idx in range(start-1, end):
            writer.add_page(reader.pages[idx])

        out = BytesIO()
        writer.write(out)
        out.seek(0)

        new_name = f"{name_prefix}_{start}-{end}.pdf"
        media = MediaIoBaseUpload(out, mimetype="application/pdf", resumable=False)
        meta = {"name": new_name, "parents":[output_folder_id], "mimeType":"application/pdf"}
        created = drive.files().create(body=meta, media_body=media, fields="id,name").execute()
        print("Subido:", created.get("name"), created.get("id"))

if __name__ == "__main__":
    main()

