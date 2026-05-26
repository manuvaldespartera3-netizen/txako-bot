"""
Integración Google Sheets.
"""
import json, logging
import gspread
from google.oauth2.service_account import Credentials
import google.generativeai as genai
import config

logger = logging.getLogger(__name__)

SCOPES = [
    'https://www.googleapis.com/auth/spreadsheets',
    'https://www.googleapis.com/auth/drive.readonly'
]

def get_sheet_client() -> gspread.Client:
    raw = config.GOOGLE_CREDENTIALS
    raw = raw.strip()
    # Quitar comillas externas si las hay
    if raw.startswith('"') and raw.endswith('"'):
        raw = raw[1:-1]
    # Reparar escapes dobles
    raw = raw.replace('\\"', '"').replace('\\\\n', '\\n')
    logger.info(f"CREDENTIALS inicio: {repr(raw[:30])}")
    creds_dict = json.loads(raw)
    creds = Credentials.from_service_account_info(creds_dict, scopes=SCOPES)
    return gspread.authorize(creds)

def get_spreadsheet():
    gc = get_sheet_client()
    return gc.open_by_key(config.SHEETS_ID)

def list_tabs() -> list[str]:
    try:
        sh = get_spreadsheet()
        return [ws.title for ws in sh.worksheets()]
    except Exception as e:
        logger.error(f"Error listando pestañas: {e}")
        return []

def find_cell(tab_name: str, student_name: str, test_name: str) -> dict | None:
    try:
        sh = get_spreadsheet()
        ws = sh.worksheet(tab_name)
        all_values = ws.get_all_values()
        if not all_values:
            return None
        headers = all_values[0]
        test_col = None
        test_found = None
        test_lower = test_name.lower().replace('/', '').replace('-', '').replace(' ', '')
        for i, h in enumerate(headers):
            h_lower = h.lower().replace('/', '').replace('-', '').replace(' ', '')
            if test_lower in h_lower or h_lower in test_lower:
                test_col = i
                test_found = h
                break
        student_row = None
        student_found = None
        student_lower = student_name.lower()
        for i, row in enumerate(all_values[1:], start=1):
            if row and student_lower in row[0].lower():
                student_row = i
                student_found = row[0]
                break
        if test_col is None or student_row is None:
            return None
        return {
            'row': student_row + 1,
            'col': test_col + 1,
            'student_found': student_found,
            'test_found': test_found,
            'tab': tab_name
        }
    except Exception as e:
        logger.error(f"Error buscando celda: {e}")
        return None

def write_grade(tab_name: str, row: int, col: int, grade: str) -> bool:
    try:
        sh = get_spreadsheet()
        ws = sh.worksheet(tab_name)
        ws.update_cell(row, col, grade)
        return True
    except Exception as e:
        logger.error(f"Error escribiendo nota: {e}")
        return False

def add_test_column(tab_name: str, test_name: str) -> int | None:
    try:
        sh = get_spreadsheet()
        ws = sh.worksheet(tab_name)
        headers = ws.row_values(1)
        col_idx = len(headers) + 1
        for i, h in enumerate(headers):
            if not h.strip():
                col_idx = i + 1
                break
        ws.update_cell(1, col_idx, test_name)
        return col_idx
    except Exception as e:
        logger.error(f"Error añadiendo columna: {e}")
        return None

async def parse_grade_command(text: str, available_tabs: list[str]) -> dict | None:
    model = genai.GenerativeModel('gemini-2.0-flash-exp')
    prompt = f"""Extrae la información de calificación del siguiente texto.
Pestañas disponibles en la hoja: {', '.join(available_tabs)}

Texto: "{text}"

Responde SOLO con JSON sin markdown:
{{
  "alumno": "nombre completo del alumno",
  "prueba": "nombre de la prueba tal como aparece o debería aparecer en la hoja",
  "nota": "la nota como número o texto exacto",
  "pestana": "nombre de la pestaña más probable de las disponibles",
  "valido": true
}}

Si no hay suficiente información, responde: {{"valido": false}}
La nota puede ser: 7, 6.5, "suspenso", "NP", etc.
"""
    try:
        response = model.generate_content(prompt)
        raw = response.text.strip().replace('```json','').replace('```','').strip()
        data = json.loads(raw)
        return data if data.get('valido') else None
    except Exception as e:
        logger.error(f"Error parseando nota: {e}")
        return None
