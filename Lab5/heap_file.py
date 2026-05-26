import os
import struct
import csv

# ── Formato de registro: employee ──────────────────────────────────────────────
# id(int64) + birth_date(10s) + first_name(14s) + last_name(16s) + gender(1s) + hire_date(10s)
# = 8 + 10 + 14 + 16 + 1 + 10 = 59 bytes
EMPLOYEE_FORMAT = "q10s14s16s1s10s"
EMPLOYEE_SIZE   = struct.calcsize(EMPLOYEE_FORMAT)  # 59 bytes

# ── Formato de registro: department_employee ───────────────────────────────────
# employee_id(int64) + dept_no(4s) + from_date(10s) + to_date(10s)
# = 8 + 4 + 10 + 10 = 32 bytes
DEPT_EMP_FORMAT = "q4s10s10s"
DEPT_EMP_SIZE   = struct.calcsize(DEPT_EMP_FORMAT)

# ── Header de página: num_records (int) ────────────────────────────────────────
PAGE_HEADER_FORMAT = "i"
PAGE_HEADER_SIZE   = struct.calcsize(PAGE_HEADER_FORMAT)  # 4 bytes

PAGE_SIZE = 4096  # bytes por defecto (configurable al llamar las funciones)

def _pack_employee(row: tuple) -> bytes:
    emp_id, birth_date, first_name, last_name, gender, hire_date = row
    return struct.pack(
        EMPLOYEE_FORMAT,
        int(emp_id),
        str(birth_date).encode().ljust(10, b"\x00")[:10],
        str(first_name).encode().ljust(14, b"\x00")[:14],
        str(last_name).encode().ljust(16, b"\x00")[:16],
        str(gender).encode().ljust(1,  b"\x00")[:1],
        str(hire_date).encode().ljust(10, b"\x00")[:10],
    )

def _unpack_employee(data: bytes) -> tuple:
    vals = struct.unpack(EMPLOYEE_FORMAT, data)
    return (
        vals[0],
        vals[1].decode().rstrip("\x00"),
        vals[2].decode().rstrip("\x00"),
        vals[3].decode().rstrip("\x00"),
        vals[4].decode().rstrip("\x00"),
        vals[5].decode().rstrip("\x00"),
    )

def _pack_dept_emp(row: tuple) -> bytes:
    emp_id, dept_no, from_date, to_date = row
    return struct.pack(
        DEPT_EMP_FORMAT,
        int(emp_id),
        str(dept_no).encode().ljust(4,  b"\x00")[:4],
        str(from_date).encode().ljust(10, b"\x00")[:10],
        str(to_date).encode().ljust(10,  b"\x00")[:10],
    )

def _unpack_dept_emp(data: bytes) -> tuple:
    vals = struct.unpack(DEPT_EMP_FORMAT, data)
    return (
        vals[0],
        vals[1].decode().rstrip("\x00"),
        vals[2].decode().rstrip("\x00"),
        vals[3].decode().rstrip("\x00"),
    )

# Mapa tabla → (record_size, pack_fn, unpack_fn)
TABLE_META = {
    "employee":            (EMPLOYEE_SIZE,  _pack_employee,  _unpack_employee),
    "department_employee": (DEPT_EMP_SIZE,  _pack_dept_emp,  _unpack_dept_emp),
}


# ──────────────────────────────────────────────────────────────────────────────
# API principal
# ──────────────────────────────────────────────────────────────────────────────

def export_to_heap(csv_path: str, heap_path: str, table: str, page_size: int = PAGE_SIZE):
    """
    Exporta un CSV a un heap file binario paginado.

    Formato de página:
        [num_records : 4 bytes] [record_0] [record_1] ... [padding hasta page_size]
    """
    record_size, pack_fn, _ = TABLE_META[table]
    records_per_page = (page_size - PAGE_HEADER_SIZE) // record_size

    with open(csv_path, newline="", encoding="utf-8") as csv_file:
        reader = csv.reader(csv_file)
        next(reader)  # saltar cabecera

        with open(heap_path, "wb") as heap:
            page_records = []

            def flush_page(records):
                header = struct.pack(PAGE_HEADER_FORMAT, len(records))
                data   = bytearray(header)
                for r in records:
                    data.extend(pack_fn(r))
                # padding para completar page_size exacto
                data.extend(b"\x00" * (page_size - len(data)))
                heap.write(bytes(data))

            for row in reader:
                page_records.append(tuple(row))
                if len(page_records) == records_per_page:
                    flush_page(page_records)
                    page_records = []

            if page_records:          # última página (puede quedar incompleta)
                flush_page(page_records)

    print(f"[export_to_heap] '{heap_path}' creado. "
          f"Registros/página: {records_per_page}, "
          f"Páginas: {count_pages(heap_path, page_size)}")


def read_page(heap_path: str, page_id: int, table: str, page_size: int = PAGE_SIZE) -> list[tuple]:
    """Lee una página del heap file y retorna sus registros como lista de tuplas."""
    record_size, _, unpack_fn = TABLE_META[table]

    with open(heap_path, "rb") as f:
        f.seek(page_id * page_size)
        raw = f.read(page_size)

    if not raw:
        return []

    num_records = struct.unpack(PAGE_HEADER_FORMAT, raw[:PAGE_HEADER_SIZE])[0]
    records = []
    for i in range(num_records):
        start = PAGE_HEADER_SIZE + i * record_size
        records.append(unpack_fn(raw[start: start + record_size]))
    return records


def write_page(heap_path: str, page_id: int, records: list[tuple],
               table: str, page_size: int = PAGE_SIZE):
    """Escribe una lista de registros en la página indicada (sobrescribe)."""
    record_size, pack_fn, _ = TABLE_META[table]

    header = struct.pack(PAGE_HEADER_FORMAT, len(records))
    data   = bytearray(header)
    for r in records:
        data.extend(pack_fn(r))
    data.extend(b"\x00" * (page_size - len(data)))

    with open(heap_path, "r+b") as f:
        f.seek(page_id * page_size)
        f.write(bytes(data))


def count_pages(heap_path: str, page_size: int = PAGE_SIZE) -> int:
    """Retorna el número total de páginas del heap file."""
    return os.path.getsize(heap_path) // page_size


# ──────────────────────────────────────────────────────────────────────────────
# Demo rápida
# ──────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    # Ajusta las rutas a tus CSV exportados desde PostgreSQL
    export_to_heap("employee.csv",            "employee.bin",            "employee")
    export_to_heap("department_employee.csv", "department_employee.bin", "department_employee")

    # Verificar leyendo la primera página de cada archivo
    print("\n--- Primera página de employee.bin ---")
    for rec in read_page("employee.bin", 0, "employee")[:3]:
        print(rec)

    print("\n--- Primera página de department_employee.bin ---")
    for rec in read_page("department_employee.bin", 0, "department_employee")[:3]:
        print(rec)