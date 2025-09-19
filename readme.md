Separador de PDFs con n8n → GitHub Actions → Google Drive (OAuth de usuario)

Descripción:
Este repositorio ejecuta un workflow de GitHub Actions que:

Descarga un PDF de tu Google Drive personal,

Lo divide en varios PDFs (por rangos o por página),

Sube cada resultado a una carpeta de tu Drive.
No usa Service Accounts ni Unidades compartidas. Funciona con cuentas personales usando OAuth 2.0 de usuario (refresh token).

Arquitectura (vista rápida):
n8n (HTTP Request → repository_dispatch) → GitHub Actions → split_pdf.py → Google Drive (tu cuenta)

Estructura del repositorio:
.
├─ split_pdf.py Script principal (usa OAuth de usuario)
├─ requirements.txt Dependencias (pypdf y Google APIs)
└─ .github/workflows/
└─ pdf_splitter.yml Workflow que instala deps y ejecuta el script

Requisitos previos:

Cuenta personal de Google (Gmail).

Proyecto en Google Cloud con Google Drive API habilitada.

Pantalla de consentimiento OAuth configurada (tipo External) con tu email como Test user.

OAuth client (Desktop app) para obtener client_id y client_secret.

Refresh token generado una sola vez.

Repo con GitHub Actions habilitado.

Activar Google Drive API:
En Google Cloud Console, selecciona o crea un proyecto.
Ir a “APIs & Services → Library”.
Buscar “Google Drive API” y pulsar “Enable”.

Configurar pantalla de consentimiento OAuth:
Ir a “APIs & Services → OAuth consent screen”.
Elegir User type: External.
Completar App name y Developer contact information.
En “Test users”, añadir tu email de Google (el que usarás).
Guardar.
Nota: en modo Testing, los refresh tokens pueden caducar en ~7 días. Para evitarlo, más adelante puedes Publicar la app (In production).

Crear credenciales OAuth (Desktop):
Ir a “APIs & Services → Credentials → Create Credentials → OAuth client ID”.
Application type: Desktop app.
Guardar Client ID y Client Secret.

Obtener el refresh token (una vez):
Crea un entorno local y ejecuta este script para autorizar tu cuenta y obtener el refresh token.

Archivo: oauth_get_refresh_token.py
Contenido:
from google_auth_oauthlib.flow import InstalledAppFlow

CLIENT_ID = "TU_CLIENT_ID"
CLIENT_SECRET = "TU_CLIENT_SECRET"

CLIENT_CONFIG = {
"installed": {
"client_id": CLIENT_ID,
"client_secret": CLIENT_SECRET,
"redirect_uris": ["http://localhost"],
"auth_uri": "https://accounts.google.com/o/oauth2/auth
",
"token_uri": "https://oauth2.googleapis.com/token
"
}
}

SCOPES = ["https://www.googleapis.com/auth/drive
"]

flow = InstalledAppFlow.from_client_config(CLIENT_CONFIG, SCOPES)
creds = flow.run_local_server(port=0, access_type="offline", prompt="consent")
print("REFRESH_TOKEN:", creds.refresh_token)

Pasos rápidos:

Crear carpeta de trabajo.

Crear y activar venv (opcional).

Instalar “google-auth-oauthlib”.

Ejecutar “python oauth_get_refresh_token.py”, autorizar en el navegador y guardar el valor REFRESH_TOKEN.

Añadir Secrets en GitHub:
En el repo: Settings → Secrets and variables → Actions → New repository secret.
Crear:
GOOGLE_CLIENT_ID = tu Client ID
GOOGLE_CLIENT_SECRET = tu Client Secret
GOOGLE_REFRESH_TOKEN = tu refresh token

Dependencias (requirements.txt):
pypdf>=4,<5
google-api-python-client>=2,<3
google-auth>=2,<3
google-auth-oauthlib>=1,<2

Workflow de GitHub (archivo .github/workflows/pdf_splitter.yml):
name: Dividir PDF (OAuth usuario)

on:
repository_dispatch:
types: [split-pdf]

jobs:
split:
runs-on: ubuntu-latest
steps:
- name: Checkout
uses: actions/checkout@v4
- name: Setup Python
uses: actions/setup-python@v5
with:
python-version: '3.11'
- name: Install deps from requirements.txt
run: |
python -m pip install --upgrade pip
pip install -r requirements.txt
- name: Run splitter
env:
GOOGLE_CLIENT_ID: ${{ secrets.GOOGLE_CLIENT_ID }}
GOOGLE_CLIENT_SECRET: ${{ secrets.GOOGLE_CLIENT_SECRET }}
GOOGLE_REFRESH_TOKEN: ${{ secrets.GOOGLE_REFRESH_TOKEN }}
FILE_ID: ${{ github.event.client_payload.fileId }}
START_PAGES: ${{ toJSON(github.event.client_payload.startPages) }}
OUTPUT_FOLDER_ID: ${{ github.event.client_payload.outputFolderId }}
NAME_PREFIX: ${{ github.event.client_payload.namePrefix }}
run: python split_pdf.py

Script principal (split_pdf.py):
import os, json, re
from io import BytesIO
from typing import List
from pypdf import PdfReader, PdfWriter
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload, MediaIoBaseUpload
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request

def user_drive():
client_id = os.environ["GOOGLE_CLIENT_ID"]
client_secret = os.environ["GOOGLE_CLIENT_SECRET"]
refresh_token = os.environ["GOOGLE_REFRESH_TOKEN"]
creds = Credentials(
token=None,
refresh_token=refresh_token,
token_uri="https://oauth2.googleapis.com/token
",
client_id=client_id,
client_secret=client_secret,
scopes=["https://www.googleapis.com/auth/drive
"],
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


if name == "main":
main()

Disparar desde n8n (repository_dispatch):
Nodo HTTP Request:

Method: POST

URL: https://api.github.com/repos/
<owner>/<repo>/dispatches

Authentication: Predefined Credential Type → GitHub API

Headers:
Accept: application/vnd.github+json

Body (JSON → Expression). Ejemplo mínimo de prueba (reemplaza TU_FILE_ID y TU_FOLDER_ID):
={{ JSON.stringify({
event_type: 'split-pdf',
client_payload: {
fileId: 'TU_FILE_ID',
startPages: [1],
outputFolderId: 'TU_FOLDER_ID',
namePrefix: 'prueba'
}
}) }}
Notas:
El endpoint devuelve 204 No Content; por eso n8n muestra un item vacío ([{}]). Comprueba la ejecución en la pestaña Actions del repo.

Body dinámico (opcional) leyendo tus nodos de n8n:
Usa una expresión que:

Tome fileId del nodo de descarga del PDF.

Convierta start_pages (array o string) en array de enteros ordenado/único.

Use namePrefix desde el nombre del archivo.

Use outputFolderId desde un nodo Set o constante.

Ejemplo base (adáptalo a los nombres de tus nodos):
={{ JSON.stringify((() => {
const fileId = $('2. Descargar PDF Original').item?.json?.id ?? $json.fileId;
const src = $('5. IA para Detectar Inicio de Documentos').item?.json ?? {};
const raw = src?.message?.content?.start_pages ?? src?.start_pages ?? $json.start_pages ?? [];
let arr;
if (Array.isArray(raw)) arr = raw;
else if (typeof raw === 'string') {
const s = raw.trim();
if (s.startsWith('[')) { try { arr = JSON.parse(s); } catch { arr = s.split(/[^\d]+/).filter(Boolean); } }
else { arr = s.split(/[,\s;|]+/).filter(Boolean); }
} else arr = [];
arr = Array.from(new Set(arr.map(n => parseInt(n,10)).filter(n => Number.isFinite(n) && n > 0))).sort((a,b)=>a-b);
const outputFolderId = $json.outputFolderId || 'TU_FOLDER_ID';
const namePrefix = (
$('2. Descargar PDF Original').item?.binary?.data?.fileName || 'documento.pdf'
).replace(/.pdf$/i, '');
return {
event_type: 'split-pdf',
client_payload: { fileId, startPages: arr, outputFolderId, namePrefix }
};
})()) }}

Solución de problemas:

invalid_grant en Actions: el refresh token caducó (app en Testing) o se revocó. Genera otro y actualiza el Secret.

File not found: revisa FILE_ID; abre el PDF en Drive y copia el ID de la URL.

No arranca el run: revisa URL /dispatches, header Accept, nombre del repo (guion correcto) y la credencial GitHub API.

Se sube en otra carpeta: revisa OUTPUT_FOLDER_ID.

Quiero 1 PDF por página: genera startPages como [1,2,3,...] o usa tu IA para detectar inicios.

Seguridad:
Guarda GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET y GOOGLE_REFRESH_TOKEN solo en GitHub Secrets.
Evita imprimir tokens en logs.
Mantén requirements.txt con rangos estables.

Licencia:
Uso personal.




