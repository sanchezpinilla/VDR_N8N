import os
import json
from io import BytesIO
from pypdf import PdfReader, PdfWriter
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload, MediaFileUpload

def main():
    # Cargar variables desde GitHub Actions
    gdrive_sa_key = os.environ.get("GDRIVE_SA_KEY")
    file_id = os.environ.get("FILE_ID")
    start_pages_json = os.environ.get("START_PAGES")
    output_folder_id = os.environ.get("OUTPUT_FOLDER_ID")

    # Validar entradas
    if not all([gdrive_sa_key, file_id, start_pages_json, output_folder_id]):
        raise ValueError("Faltan variables de entorno.")

    start_pages = json.loads(start_pages_json)
    
    # Autenticar con Google Drive
    creds = Credentials.from_service_account_info(json.loads(gdrive_sa_key))
    service = build('drive', 'v3', credentials=creds)

    # Descargar el PDF original en memoria
    request = service.files().get_media(fileId=file_id)
    fh = BytesIO()
    downloader = MediaIoBaseDownload(fh, request)
    done = False
    while done is False:
        status, done = downloader.next_chunk()
    fh.seek(0)
    
    reader = PdfReader(fh)
    total_pages = len(reader.pages)
    source_name = service.files().get(fileId=file_id, fields='name').execute().get('name', 'file').replace('.pdf', '')

    # Bucle para dividir y subir cada nuevo PDF
    for i, start in enumerate(start_pages):
        start_index = start - 1
        end_index = (start_pages[i + 1] - 1) if i + 1 < len(start_pages) else total_pages

        writer = PdfWriter()
        for page_num in range(start_index, end_index):
            writer.add_page(reader.pages[page_num])
        
        output_pdf_stream = BytesIO()
        writer.write(output_pdf_stream)
        output_pdf_stream.seek(0)

        new_file_name = f"{source_name}_{start}-{end_index}.pdf"
        media = MediaFileUpload(output_pdf_stream, mimetype='application/pdf', resumable=True)
        file_metadata = {'name': new_file_name, 'parents': [output_folder_id]}
        
        service.files().create(body=file_metadata, media_body=media, fields='id').execute()
        print(f"Subido: {new_file_name}")

if __name__ == "__main__":
    main()
