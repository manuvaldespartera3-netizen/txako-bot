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
    """
    Busca un alumno por nombre flexible.
    Acepta: 'Noel', 'Esteban', 'Noel Esteban', 'Esteban Noel', 'ESTEBAN, NOEL'
    Devuelve (fila_1based, nombre_encontrado) o (None, None)
    """
    name_lower = name.lower().replace(',', '').strip()
    name_parts = name_lower.split()

    for i, row in enumerate(all_values[1:], start=1):
        if not row or not row[0]:
            continue
        cell_lower = row[0].lower().replace(',', '').strip()
        cell_parts = cell_lower.split()

        # Coincidencia exacta
        if name_lower == cell_lower:
            return i, row[0]

        # Todos los fragmentos del input están en la celda
        if all(part in cell_parts for part in name_parts):
            return i, row[0]

        # Al menos un fragmento coincide si solo hay un nombre
        if len(name_parts) == 1 and name_parts[0] in cell_parts:
            return i, row[0]

    return None, None

def find_test_col(headers: list, test_name: str) -> tuple:
    """
    Busca columna de prueba de forma flexible.
    Devuelve (col_0based, nombre_encontrado) o (None, None)
    """
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

def find_cell_all_tabs(student_name: str, test_name: str) -> dict | None:
    """Busca en todas las pestañas."""
    tabs = list_tabs()
    for tab in tabs:
        result = find_cell(tab, student_name, test_name)
        if result:
            return result
    return None

def create_test_column(tab_name: str, test_name: str) -> int | None:
    """Crea una nueva columna con el nombre de la prueba. Devuelve col (1-based)."""
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
        logger.info(f"Columna creada: '{test_name}' en col {col_idx}")
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

def write_grades_batch(tab_name: str, grades: list[dict]) -> tuple[int, int]:
    """
    Escribe múltiples notas de una vez.
    grades = [{'student': str, 'test': str, 'grade': str}, ...]
    Devuelve (ok, fallos)
    """
    try:
        sh = get_spreadsheet()
        ws = sh.worksheet(tab_name)
        all_values = ws.get_all_values()
        headers = all_values[0]

        ok = 0
        fallos = 0
        for g in grades:
            test_col, _ = find_test_col(headers, g['test'])
            student_row, _ = find_student_row(all_values, g['student'])
            if test_col is not None and student_row is not None:
                ws.update_cell(student_row + 1, test_col + 1, g['grade'])
                ok += 1
            else:
                fallos += 1
                logger.warning(f"No encontrado: {g['student']} / {g['test']}")
        return ok, fallos
    except Exception as e:
        logger.error(f"Error en batch: {e}")
        return 0, len(grades)

def parse_grade_command(text: str, available_tabs: list[str]) -> dict | None:
    """Parser simple. Formato: Nombre, prueba, nota"""
    text = text.strip().rstrip('.')
    partes = [p.strip() for p in text.split(',')]
    if len(partes) < 3:
        partes = [p.strip() for p in text.split('.')]
    if len(partes) < 3:
        logger.error(f"No se pudo parsear: {text}")
        return None

    alumno = partes[0]
    prueba = partes[1]
    nota = partes[2]

    nota_clean = re.sub(r'[^\d.,]', '', nota).replace(',', '.')
    if not nota_clean:
        nota_clean = nota.strip()

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

def parse_batch_grades(text: str) -> tuple[str, str, list[dict]] | None:
    """
    Parsea formato batch: "Cálculo 26 mayo. Alicia 5,5; Sofía 7; Rodrigo 9"
    Devuelve (prueba, pestaña_probable, lista_de_notas) o None
    """
    # Separar prueba del resto
    if '.' in text:
        parts = text.split('.', 1)
        prueba = parts[0].strip()
        resto = parts[1].strip()
    elif '\n' in text:
        parts = text.split('\n', 1)
        prueba = parts[0].strip()
        resto = parts[1].strip()
    else:
        return None

    # Parsear "Nombre nota; Nombre nota; ..."
    grades = []
    # Separar por ; o por coma si hay punto y coma
    if ';' in resto:
        items = [i.strip() for i in resto.split(';')]
    else:
        items = [i.strip() for i in resto.split(',')]

    for item in items:
        item = item.strip().rstrip('.')
        if not item:
            continue
        # Último token es la nota, el resto es el nombre
        tokens = item.rsplit(' ', 1)
        if len(tokens) == 2:
            nombre = tokens[0].strip()
            nota = tokens[1].strip().replace(',', '.')
            nota_clean = re.sub(r'[^\d.]', '', nota)
            if nombre and nota_clean:
                grades.append({'student': nombre, 'test': prueba, 'grade': nota_clean})

    if not grades:
        return None

    return prueba, 'DATOS', grades
