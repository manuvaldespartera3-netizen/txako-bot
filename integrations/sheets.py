"""
Integración Google Sheets.
"""
import json, logging, re
import gspread
from google.oauth2.service_account import Credentials
import config

logger = logging.getLogger(__name__)

SCOPES = [
    'https://www.googleapis.com/auth/spreadsheets',
    'https://www.googleapis.com/auth/drive.readonly'
]

def get_sheet_client() -> gspread.Client:
    raw = config.GOOGLE_CREDENTIALS
    raw = raw.strip()
    if raw.startswith('"') and raw.endswith('"'):
        raw = raw[1:-1]
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

def find_cell_all_tabs(student_name: str, test_name: str) -> dict | None:
    """Busca en todas las pestañas hasta encontrar alumno y prueba."""
    tabs = list_tabs()
    for tab in tabs:
        result = find_cell(tab, student_name, test_name)
        if result:
            return result
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

def parse_grade_command(text: str, available_tabs: list[str]) -> dict | None:
    """
    Parser simple sin IA. Formato esperado:
    "Nombre Apellido, prueba fecha, nota"
    o cualquier combinación con coma separando nombre, prueba y nota.
    """
    text = text.strip().rstrip('.')

    # Separar por comas
    partes = [p.strip() for p in text.split(',')]

    if len(partes) < 3:
        # Intentar separar por punto
        partes = [p.strip() for p in text.split('.')]

    if len(partes) < 3:
        logger.error(f"No se pudo parsear (menos de 3 partes): {text}")
        return None

    alumno = partes[0]
    prueba = partes[1]
    nota = partes[2]

    # Limpiar nota: quedarse solo con números, coma o punto
    nota_clean = re.sub(r'[^\d.,]', '', nota).replace(',', '.')
    if not nota_clean:
        nota_clean = nota.strip()

    # Detectar pestaña más probable
    pestana = available_tabs[0] if available_tabs else 'DATOS'
    prueba_lower = prueba.lower()
    for tab in available_tabs:
        if tab.lower() in prueba_lower or prueba_lower in tab.lower():
            pestana = tab
            break

    logger.info(f"Parseado → alumno:{alumno} prueba:{prueba} nota:{nota_clean} pestaña:{pestana}")

    return {
        'alumno': alumno,
        'prueba': prueba,
        'nota': nota_clean,
        'pestana': pestana,
        'valido': True
    }
