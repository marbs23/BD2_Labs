# FIRST
import struct
import data as d
import os

PAGE_SIZE = 512
HEADER_FMT = 'iii'
HEADER_SIZE = struct.calcsize(HEADER_FMT)

RECORD_FMT = '5s11s20s15sif'
RECORD_SIZE = struct.calcsize(RECORD_FMT)

RECORDS_PER_PAGE = (PAGE_SIZE - HEADER_SIZE) // RECORD_SIZE

def total_pages(file) -> int:
    file.seek(0,2)
    size = file.tell()
    return size // PAGE_SIZE

def unpack_record(data:bytes) -> d.Alumno:
    codigo, nombre, apellidos, carrera, ciclo, mensualidad = \
        struct.unpack(RECORD_FMT, data)
    return d.Alumno(
        codigo.decode("utf-8").rstrip('\x00').strip(),
        nombre.decode("utf-8").rstrip('\x00').strip(),
        apellidos.decode("utf-8").rstrip('\x00').strip(),
        carrera.decode("utf-8").rstrip('\x00').strip(),
        ciclo,
        round(mensualidad,2)
    )

def pack_record(alumno: d.Alumno) -> bytes:
    return struct.pack(
        RECORD_FMT,
        alumno.codigo.encode("utf-8").ljust(5, b"\x00"),
        alumno.nombre.encode("utf-8").ljust(11, b"\x00"),
        alumno.apellidos.encode("utf-8").ljust(20, b"\x00"),
        alumno.carrera.encode("utf-8").ljust(15, b"\x00"),
        alumno.ciclo,
        alumno.mensualidad
    )



class FixedRecordLastMove:
    def __init__(self, filename):
        self.filename = filename

    def _read_header(self, f, page_idx: int) -> tuple:
        f.seek(PAGE_SIZE * page_idx)
        return struct.unpack(HEADER_FMT, f.read(HEADER_SIZE))
    
    def _pack_header(self, total: int, active: int, free_ptr: int = -1) -> bytes:
        return struct.pack(HEADER_FMT, total, active, free_ptr);

    def load(self):
        records = []
        with open(self.filename, "rb") as file:
            n_pages = total_pages(file)
            for page in range(n_pages):
                total, active, free_ptr = self._read_header(file, page)
                slot = 0
                file.seek(PAGE_SIZE * page + HEADER_SIZE)
                while slot < active:
                    data = file.read(RECORD_SIZE)
                    #if len(data) < RECORD_SIZE:
                    #    break
                    record = unpack_record(data)
                    records.append(record)
                    slot += 1
        return records
    

    def add(self, record: d.Alumno):
            with open(self.filename, "r+b") as file:
                record_data = pack_record(record)
                n_pages = total_pages(file)
                target_page = -1

                for page in range(n_pages):
                    total, active, free_ptr = self._read_header(file, page)
                    if (active < total):
                        target_page = page
                        break

                if target_page == -1:
                    file.seek(0,2)
                    page_data = bytearray(PAGE_SIZE)
                    page_data[0:HEADER_SIZE] = self._pack_header(RECORDS_PER_PAGE, 1)
                    page_data[HEADER_SIZE:HEADER_SIZE+RECORD_SIZE] = record_data    
                    file.write(page_data)
                    return

                total, active, free_ptr = self._read_header(file, target_page)
                file.seek(PAGE_SIZE * target_page + HEADER_SIZE + active * RECORD_SIZE)
                file.write(record_data)
                file.seek(PAGE_SIZE * target_page)
                file.write(self._pack_header(total, active+1))

    def readRecord(self, pos: int) -> d.Alumno:
        with open(self.filename, "rb") as file:
            n_page = pos // RECORDS_PER_PAGE
            offset = pos % RECORDS_PER_PAGE
            file.seek(n_page * PAGE_SIZE + HEADER_SIZE + offset * RECORD_SIZE)
            data = file.read(RECORD_SIZE)
            return unpack_record(data)
        
    def remove(self, pos: int):
        with open(self.filename, "r+b") as file:

            n_pages = total_pages(file)
            last_page = -1
            active_last = -1
            total_last = -1
            for page in range(n_pages - 1, -1, -1):
                total, active, free_ptr = self._read_header(file, page)
                if active > 0:
                    last_page = page
                    total_last = total
                    active_last = active
                    break

            n_page = pos // RECORDS_PER_PAGE
            offset = pos % RECORDS_PER_PAGE

            if not(last_page == n_page and active_last - 1 == offset):
                file.seek(last_page * PAGE_SIZE + HEADER_SIZE + (active_last - 1) * RECORD_SIZE)
                data = file.read(RECORD_SIZE)
                file.seek(n_page * PAGE_SIZE + HEADER_SIZE + offset * RECORD_SIZE)
                file.write(data)

            file.seek(PAGE_SIZE * last_page)
            file.write(self._pack_header(total_last, active_last-1))


class FixedRecordFreeList:
    def __init__(self, filename):
        self.filename = filename

    def _read_header(self, file, page_idx) -> tuple:
        return
    
    def _pack_header(self, total, active, free_ptr = -1) -> bytes:
        return

    def load():
        return
    def add(record):
        return
    def readRecord(pos):
        return
    def remove(pos):
        return



if __name__ == '__main__':
    alumnos = d.generar_alumnos()