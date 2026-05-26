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

def find_student_row(all_values: list, name: str) -> tuple:
    name_lower = name.lower().replace(',', '').strip()
    name_parts = set(name_lower.split())
    for i, row in enumerate(all_values[1:], start=1):
        if not row or not row[0]:
            continue
        cell_lower = row[0].lower().replace(',', '').strip()
        cell_parts = set(cell_lower.split())
        if name_lower == cell_lower:
            return i, row[0]
        if name_parts and name_parts.issubset(cell_parts):
            return i, row[0]
        if len(name_parts) == 1 and name_parts.issubset(cell_parts):
            return i, row[0]
    return None, None

def find_test_col(headers: list, test_name: str) -> tuple:
    test_lower = test_name.lower().replace('/', '').replace('-', '').replace(' ', '')
    for i, h in enumerate(headers):
        h_lower = h.lower().replace('/', '').replace('-', '').replace(' ', '')
        if test_lower in h_lower or h_lower in test_lower:
            return i, h
    return None, None

def find_cell(tab_name: str, student_name: str, test_name: str) -> dict | None:
    try:
        sh = get_spreadsheet()
        ws = sh.worksheet(tab_name)
        all_values = ws.get_all_values()
        if not all_values:
            return None
        headers = all_values[0]
        test_col, test_found = find_test_col(headers, test_name)
        student_row, student_found = find_student_row(all_values, student_name)
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

def find_student_in_tab(tab_name: str, student_name: str) -> dict | None:
    try:
        sh = get_spreadsheet()
        ws = sh.worksheet(tab_name)
        all_values = ws.get_all_values()
        if not all_values:
            return None
        student_row, student_found = find_student_row(all_values, student_name)
        if student_row is None:
            return None
        return {'row': student_row + 1, 'student_found': student_found, 'tab': tab_name}
    except Exception as e:
        logger.error(f"Error buscando alumno: {e}")
        return None

def find_cell_all_tabs(student_name: str, test_name: str) -> dict | None:
    tabs = list_tabs()
    for tab in tabs:
        result = find_cell(tab, student_name, test_name)
        if result:
            return result
    return None

def create_test_column(tab_name: str, test_name: str) -> int | None:
    try:
        sh = get_spreadsheet()
        ws = sh.worksheet(tab_name)
        headers = ws.row_values(1)
        col_idx = len([h for h in headers if h.strip()]) + 1
        ws.update_cell(1, col_idx, test_name)
        logger.info(f"Columna creada: '{test_name}' en col {col_idx} de {tab_name}")
        return col_idx
    except Exception as e:
        logger.error(f"Error creando columna: {e}")
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

def write_grades_batch(tab_name: str, col: int, grades: list[dict]) -> tuple[int, int, list]:
    try:
        sh = get_spreadsheet()
        ws = sh.worksheet(tab_name)
        all_values = ws.get_all_values()
        ok = 0
        fallos = 0
        no_encontrados = []
        for g in grades:
            student_row, student_found = find_student_row(all_values, g['student'])
            if student_row is not None:
                ws.update_cell(student_row + 1, col, g['grade'])
                ok += 1
            else:
                fallos += 1
                no_encontrados.append(g['student'])
        return ok, fallos, no_encontrados
    except Exception as e:
        logger.error(f"Error en batch: {e}")
        return 0, len(grades), []

def normalizar_nota(nota_str: str) -> str:
    nota_str = nota_str.strip().replace(',', '.')
    try:
        valor = float(nota_str)
        if valor == int(valor):
            return str(int(valor))
        return f"{valor:.2f}".rstrip('0').rstrip('.').replace('.', ',')
    except Exception:
        return nota_str

def es_numero(s: str) -> bool:
    try:
        float(s.replace(',', '.'))
        return True
    except Exception:
        return False

def parse_grade_command(text: str, available_tabs: list[str]) -> dict | None:
    text = text.strip().rstrip('.')
    tab_idx = 0
    match = re.match(r'^(\d+)\s+', text)
    if match:
        tab_idx = int(match.group(1)) - 1
        text = text[match.end():]
    partes = [p.strip() for p in text.split(',')]
    if len(partes) < 3:
        partes = [p.strip() for p in text.split('.')]
    if len(partes) < 3:
        return None
    alumno = partes[0]
    prueba = partes[1]
    nota = normalizar_nota(partes[2])
    if available_tabs:
        tab_idx = max(0, min(tab_idx, len(available_tabs) - 1))
        pestana = available_tabs[tab_idx]
    else:
        pestana = 'DATOS'
    logger.info(f"Parseado → alumno:{alumno} prueba:{prueba} nota:{nota} pestaña:{pestana}")
    return {
        'alumno': alumno,
        'prueba': prueba,
        'nota': nota,
        'pestana': pestana,
        'valido': True
    }

def parse_batch_grades(text: str, available_tabs: list[str]) -> tuple | None:
    """
    Parsea texto continuo sin separadores claros.
    Formato Whisper: 'cálculo 26 de mayo Sofía 7 Rodrigo 9 Noel 8,25 África 5,25'
    También acepta puntos, punto y coma, dos puntos como separadores.
    """
    text = text.strip()

    # Número de pestaña al inicio
    tab_idx = 0
    match = re.match(r'^(\d+)\s+', text)
    if match:
        tab_idx = int(match.group(1)) - 1
        text = text[match.end():]

    # Tokenizar por espacios
    tokens = text.replace(';', ' ').replace(':', ' ').split()
    tokens = [t.strip('.,') for t in tokens if t.strip('.,')]

    # Encontrar primer token numérico — todo antes es la prueba
    prueba_tokens = []
    resto_tokens = []
    encontrado_numero = False
    for i, t in enumerate(tokens):
        if not encontrado_numero and es_numero(t):
            # El token anterior a este número es el último del nombre del primer alumno
            # Los tokens hasta i-1 inclusive son prueba + primer nombre
            # Retroceder: el último token antes del número es parte del primer nombre
            encontrado_numero = True
            # prueba = todo hasta i-2, primer_nombre = tokens[i-1]
            resto_tokens = tokens[i-1:]  # desde el primer nombre
            prueba_tokens = tokens[:i-1]
            break
        if not encontrado_numero:
            prueba_tokens.append(t)

    if not encontrado_numero or not prueba_tokens:
        return None

    prueba = ' '.join(prueba_tokens)

    # Ahora parsear resto_tokens: nombre nota nombre nota...
    # Los números son notas, las palabras entre números son nombres
    grades = []
    nombre_actual = []
    for t in resto_tokens:
        if es_numero(t):
            if nombre_actual:
                nombre = ' '.join(nombre_actual)
                nota = normalizar_nota(t)
                grades.append({'student': nombre, 'grade': nota})
                nombre_actual = []
        else:
            nombre_actual.append(t)

    if not grades:
        return None

    if available_tabs:
        tab_idx = max(0, min(tab_idx, len(available_tabs) - 1))
        tab_name = available_tabs[tab_idx]
    else:
        tab_name = 'DATOS'

    logger.info(f"Batch → prueba:{prueba} tab:{tab_name} alumnos:{[g['student'] for g in grades]}")
    return prueba, tab_name, grades
