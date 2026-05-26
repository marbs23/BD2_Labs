import os
import math
import time
import heapq
import tempfile
import struct

from heap_file import (
    read_page, write_page, count_pages,
    PAGE_HEADER_FORMAT, PAGE_HEADER_SIZE,
    TABLE_META, PAGE_SIZE as DEFAULT_PAGE_SIZE,
)

# ──────────────────────────────────────────────────────────────────────────────
# Columnas por tabla (para saber el índice del sort_key en la tupla)
# ──────────────────────────────────────────────────────────────────────────────
COLUMN_INDEX = {
    "employee": {
        "id": 0, "birth_date": 1, "first_name": 2,
        "last_name": 3, "gender": 4, "hire_date": 5,
    },
    "department_employee": {
        "employee_id": 0, "dept_no": 1, "from_date": 2, "to_date": 3,
    },
}

TABLE = "employee"   # tabla que usamos en este ejercicio


# ──────────────────────────────────────────────────────────────────────────────
# Helpers de I/O sobre archivos de run temporales
# (mismo formato de página que heap_file, misma tabla)
# ──────────────────────────────────────────────────────────────────────────────

def _write_run(path: str, records: list[tuple], table: str, page_size: int) -> int:
    """
    Escribe una lista de registros en un archivo de run temporal con formato
    de heap paginado. Retorna el número de páginas escritas.
    """
    record_size, pack_fn, _ = TABLE_META[table]
    records_per_page = (page_size - PAGE_HEADER_SIZE) // record_size
    pages_written = 0

    with open(path, "wb") as f:
        for i in range(0, len(records), records_per_page):
            chunk = records[i: i + records_per_page]
            header = struct.pack(PAGE_HEADER_FORMAT, len(chunk))
            data   = bytearray(header)
            for r in chunk:
                data.extend(pack_fn(r))
            data.extend(b"\x00" * (page_size - len(data)))
            f.write(bytes(data))
            pages_written += 1

    return pages_written


def _read_run_page(path: str, page_id: int, table: str, page_size: int) -> list[tuple]:
    """Lee una página de un archivo de run temporal."""
    record_size, _, unpack_fn = TABLE_META[table]

    with open(path, "rb") as f:
        f.seek(page_id * page_size)
        raw = f.read(page_size)

    if not raw or len(raw) < PAGE_HEADER_SIZE:
        return []

    num_records = struct.unpack(PAGE_HEADER_FORMAT, raw[:PAGE_HEADER_SIZE])[0]
    records = []
    for i in range(num_records):
        start = PAGE_HEADER_SIZE + i * record_size
        records.append(unpack_fn(raw[start: start + record_size]))
    return records


def _count_run_pages(path: str, page_size: int) -> int:
    return os.path.getsize(path) // page_size


# ──────────────────────────────────────────────────────────────────────────────
# FASE 1: Generación de runs
# ──────────────────────────────────────────────────────────────────────────────

def generate_runs(
    heap_path: str,
    page_size: int,
    buffer_size: int,
    sort_key: str,
    table: str = TABLE,
) -> tuple[list[str], int, int]:
    """
    Lee B páginas a la vez, las ordena en memoria por sort_key y las escribe
    como archivos temporales de run ordenado.

    Retorna:
        (run_paths, pages_read, pages_written)

    Número de runs generados = ceil(total_pages / B)
    """
    B            = buffer_size // page_size          # páginas que caben en RAM
    total_pages  = count_pages(heap_path, page_size)
    key_idx      = COLUMN_INDEX[table][sort_key]
    run_paths    = []
    pages_read   = 0
    pages_written = 0

    print(f"[Fase 1] total_pages={total_pages}, B={B}, "
          f"runs esperados={math.ceil(total_pages / B)}")

    for start_page in range(0, total_pages, B):
        # ── cargar B páginas en el buffer de RAM ──────────────────────────────
        buffer = []
        for pid in range(start_page, min(start_page + B, total_pages)):
            buffer.extend(read_page(heap_path, pid, table, page_size))
            pages_read += 1

        # ── ordenar en memoria ────────────────────────────────────────────────
        buffer.sort(key=lambda r: r[key_idx])

        # ── escribir run ordenado en archivo temporal ─────────────────────────
        tmp = tempfile.NamedTemporaryFile(
            delete=False, suffix=".run", prefix="sort_run_"
        )
        tmp.close()
        pw = _write_run(tmp.name, buffer, table, page_size)
        pages_written += pw
        run_paths.append(tmp.name)

        print(f"  run {len(run_paths):>3}: {len(buffer):>6} registros, "
              f"{pw} páginas  → {os.path.basename(tmp.name)}")

    return run_paths, pages_read, pages_written


# ──────────────────────────────────────────────────────────────────────────────
# FASE 2: Multiway Merge (k-way merge con min-heap)
# ──────────────────────────────────────────────────────────────────────────────

def multiway_merge(
    run_paths: list[str],
    output_path: str,
    page_size: int,
    buffer_size: int,
    sort_key: str,
    table: str = TABLE,
) -> tuple[int, int]:
    """
    Realiza un k-way merge de los runs usando un min-heap de Python.

    - Usa B-1 buffers de entrada (uno por run) y 1 buffer de salida.
    - Cuando el buffer de entrada de un run se agota, carga la siguiente página.
    - Cuando el buffer de salida se llena, lo escribe a disco y lo vacía.

    Retorna:
        (pages_read, pages_written)
    """
    B        = buffer_size // page_size
    key_idx  = COLUMN_INDEX[table][sort_key]
    k        = len(run_paths)

    # Estado por run: {run_id: {'buf': [...], 'next_page': int, 'path': str}}
    run_state = {}
    for rid, path in enumerate(run_paths):
        buf = _read_run_page(path, 0, table, page_size)
        run_state[rid] = {"buf": buf, "next_page": 1, "path": path}

    pages_read    = sum(1 for _ in run_paths)   # primera página de cada run
    pages_written = 0
    out_buffer    = []

    record_size, pack_fn, _ = TABLE_META[table]
    records_per_page = (page_size - PAGE_HEADER_SIZE) // record_size

    # ── inicializar el min-heap ───────────────────────────────────────────────
    # Cada entrada: (sort_value, run_id, record)
    heap = []
    for rid, state in run_state.items():
        if state["buf"]:
            rec = state["buf"].pop(0)
            heapq.heappush(heap, (rec[key_idx], rid, rec))

    # ── merge ─────────────────────────────────────────────────────────────────
    with open(output_path, "wb") as out_f:

        def flush_output():
            nonlocal pages_written
            header = struct.pack(PAGE_HEADER_FORMAT, len(out_buffer))
            data   = bytearray(header)
            for r in out_buffer:
                data.extend(pack_fn(r))
            data.extend(b"\x00" * (page_size - len(data)))
            out_f.write(bytes(data))
            pages_written += 1
            out_buffer.clear()

        while heap:
            key_val, rid, rec = heapq.heappop(heap)
            out_buffer.append(rec)

            # flush salida cuando el buffer de salida está lleno
            if len(out_buffer) == records_per_page:
                flush_output()

            # reponer desde el run correspondiente
            state = run_state[rid]
            if state["buf"]:
                nxt = state["buf"].pop(0)
                heapq.heappush(heap, (nxt[key_idx], rid, nxt))
            else:
                # cargar siguiente página de ese run
                next_pg = state["next_page"]
                new_buf = _read_run_page(state["path"], next_pg, table, page_size)
                if new_buf:
                    pages_read += 1
                    state["next_page"] += 1
                    state["buf"] = new_buf
                    nxt = state["buf"].pop(0)
                    heapq.heappush(heap, (nxt[key_idx], rid, nxt))
                # si new_buf está vacío, ese run se agotó → no reponemos

        # flush registros restantes en el buffer de salida
        if out_buffer:
            flush_output()

    return pages_read, pages_written


# ──────────────────────────────────────────────────────────────────────────────
# Función principal: external_sort
# ──────────────────────────────────────────────────────────────────────────────

def external_sort(
    heap_path: str,
    output_path: str,
    page_size: int,
    buffer_size: int,
    sort_key: str,
    table: str = TABLE,
) -> dict:
    """
    Ejecuta TPMMS completo y retorna métricas:
    {
        'runs_generated'  : int,
        'pages_read'      : int,
        'pages_written'   : int,
        'time_phase1_sec' : float,
        'time_phase2_sec' : float,
        'time_total_sec'  : float,
    }
    """
    B = buffer_size // page_size
    print(f"\n{'='*60}")
    print(f"External Sort  |  buffer={buffer_size//1024} KB  |  B={B} páginas/run")
    print(f"{'='*60}")

    total_pages_read    = 0
    total_pages_written = 0

    # ── Fase 1 ────────────────────────────────────────────────────────────────
    t0 = time.perf_counter()
    run_paths, pr1, pw1 = generate_runs(heap_path, page_size, buffer_size, sort_key, table)
    t1 = time.perf_counter()
    total_pages_read    += pr1
    total_pages_written += pw1

    # ── Fase 2 ────────────────────────────────────────────────────────────────
    print(f"\n[Fase 2] k-way merge de {len(run_paths)} runs con B-1={B-1} buffers de entrada")
    pr2, pw2 = multiway_merge(run_paths, output_path, page_size, buffer_size, sort_key, table)
    t2 = time.perf_counter()
    total_pages_read    += pr2
    total_pages_written += pw2

    # ── limpiar archivos temporales ───────────────────────────────────────────
    for path in run_paths:
        os.remove(path)

    metrics = {
        "runs_generated":   len(run_paths),
        "pages_read":       total_pages_read,
        "pages_written":    total_pages_written,
        "time_phase1_sec":  round(t1 - t0, 4),
        "time_phase2_sec":  round(t2 - t1, 4),
        "time_total_sec":   round(t2 - t0, 4),
    }

    print(f"\n{'─'*60}")
    print(f"  Runs generados : {metrics['runs_generated']}")
    print(f"  Páginas leídas : {metrics['pages_read']}")
    print(f"  Páginas escritas: {metrics['pages_written']}")
    print(f"  Fase 1         : {metrics['time_phase1_sec']} s")
    print(f"  Fase 2         : {metrics['time_phase2_sec']} s")
    print(f"  Total          : {metrics['time_total_sec']} s")
    print(f"{'─'*60}\n")

    return metrics


# ──────────────────────────────────────────────────────────────────────────────
# Demo / análisis de rendimiento (sección 2.4 del lab)
# ──────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    HEAP_PATH = "employee.bin"
    PAGE_SIZE = 4096

    results = []
    for kb in [64, 128, 256]:
        buffer_size = kb * 1024
        output_path = f"employee_sorted_{kb}kb.bin"
        metrics = external_sort(HEAP_PATH, output_path, PAGE_SIZE, buffer_size, "hire_date")
        metrics["buffer_kb"] = kb
        results.append(metrics)

        # verificación rápida: mostrar primeros 5 registros ordenados
        print(f"Primeros 5 registros ordenados por hire_date ({kb} KB buffer):")
        for rec in read_page(output_path, 0, TABLE, PAGE_SIZE)[:5]:
            print(f"  id={rec[0]:>6}  hire_date={rec[5]}")
        print()

    # tabla resumen para el informe
    print(f"\n{'BUFFER':>10} {'B(págs)':>8} {'Runs':>6} "
          f"{'T-Fase1':>10} {'T-Fase2':>10} {'T-Total':>10} {'I/O':>8}")
    print("-" * 70)
    for r in results:
        B = (r['buffer_kb'] * 1024) // PAGE_SIZE
        print(f"{r['buffer_kb']:>8} KB {B:>8} {r['runs_generated']:>6} "
              f"{r['time_phase1_sec']:>9.3f}s {r['time_phase2_sec']:>9.3f}s "
              f"{r['time_total_sec']:>9.3f}s {r['pages_read']+r['pages_written']:>8}")