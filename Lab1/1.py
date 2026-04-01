# FIRST
import struct
import data as d

PAGE_SIZE = 512
HEADER_FMT = 'iii'
HEADER_SIZE = struct.calcsize(HEADER_FMT)

RECORD_FMT = '5s11s20s15sif1s'
RECORD_SIZE = struct.calcsize(RECORD_FMT)

RECORDS_PER_PAGE = (PAGE_SIZE - HEADER_SIZE) // RECORD_SIZE

ACTIVE  = b'A'
DELETED = b'D'


def total_pages(file) -> int:
    file.seek(0,2)
    size = file.tell()
    return size // PAGE_SIZE

def unpack_record(data:bytes) -> dict | None:
    codigo, nombre, apellidos, carrera, ciclo, mensualidad, flag = \
        struct.unpack(RECORD_FMT, data)
    deleted = (flag == DELETED)
    return {
        'codigo'     : codigo.decode().rstrip('\x00').strip(),
        'nombre'     : nombre.decode().rstrip('\x00').strip(),
        'apellidos'  : apellidos.decode().rstrip('\x00').strip(),
        'carrera'    : carrera.decode().rstrip('\x00').strip(),
        'ciclo'      : ciclo,
        'mensualidad': mensualidad,
        'deleted'    : deleted,
    }

class FixedRecord:
    def __init__(self, filename, mode):
        self.filename = filename
        self.mode = mode
        self.format = RECORD_FMT
        self.size = struct.calcsize(self.format)

    def _read_header(self, f, page_idx:int) -> tuple:
        f.seek(PAGE_SIZE * page_idx)
        return struct.unpack(HEADER_FMT, f.read(HEADER_SIZE))

    def load(self):
        records = []
        with open(self.filename, "rb") as file:
            n_pages = total_pages(file)
            for page in range(n_pages):
                total, active, d_pointer = self._read_header(file, page)
                for slot in range(total):
                    raw = file.seek(PAGE_SIZE * page + HEADER_SIZE + slot * RECORD_SIZE)
                    record = unpack_record(raw)
                    if not record['deleted']:
                        record['_page'] = page
                        record['_slot'] = slot
                        records.append(record)
        return records

