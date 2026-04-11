import os
import struct
from dataclasses import dataclass
from data import generar_alumnos

# configuración de formatos según indicaciones
# 5(string) + 11(string) + 20(string) + 15(string) + 4(int) + 4(float) = 59 bytes
RECORD_FORMAT = "5s11s20s15sif"
RECORD_SIZE = struct.calcsize(RECORD_FORMAT)

# total_records(int), active_records(int), pos_del(int)
PAGE_HEADER_FORMAT = "iii"
PAGE_HEADER_SIZE = struct.calcsize(PAGE_HEADER_FORMAT)

# num_pages, total_active_records
FILE_HEADER_FORMAT = "ii"
FILE_HEADER_SIZE = struct.calcsize(FILE_HEADER_FORMAT)

# tamaño de página definido
PAGE_SIZE = 256
RECORDS_PER_PAGE = (PAGE_SIZE - PAGE_HEADER_SIZE) // RECORD_SIZE

@dataclass
class AlumnoRecord:
    codigo: str
    nombre: str
    apellidos: str
    carrera: str
    ciclo: int
    mensualidad: float

    # convierte los datos a binario
    def pack(self) -> bytes:
        return struct.pack(
            RECORD_FORMAT,
            self.codigo.encode("utf-8").ljust(5, b"\x00"),
            self.nombre.encode("utf-8").ljust(11, b"\x00"),
            self.apellidos.encode("utf-8").ljust(20, b"\x00"),
            self.carrera.encode("utf-8").ljust(15, b"\x00"),
            self.ciclo,
            self.mensualidad)

    # toma los bytes y los convierte en un objeto de python
    @staticmethod
    def unpack(data: bytes) -> "AlumnoRecord":
        vals = struct.unpack(RECORD_FORMAT, data)
        return AlumnoRecord(
            vals[0].decode("utf-8").rstrip("\x00"),
            vals[1].decode("utf-8").rstrip("\x00"),
            vals[2].decode("utf-8").rstrip("\x00"),
            vals[3].decode("utf-8").rstrip("\x00"),
            vals[4],
            round(vals[5], 2))

class Page:
    def __init__(self, total=0, active=0, pos_del=-1, records=None):
        self.total_records = total
        self.active_records = active
        self.pos_del = pos_del # requerido por header
        self.records = records if records else []

    # crea un bloque de 256 bytes exactos (una página)
    def pack(self) -> bytes:
        data = bytearray(struct.pack(PAGE_HEADER_FORMAT, self.total_records, self.active_records, self.pos_del))
        for i in range(RECORDS_PER_PAGE):
            if i < len(self.records):
                data.extend(self.records[i].pack())
            else:
                data.extend(b"\x00" * RECORD_SIZE)
        return data.ljust(PAGE_SIZE, b"\x00")

    # lee un bloque de 256 bytes
    # extrae los registros activos basándose en el header
    @staticmethod
    def unpack(data: bytes) -> "Page":
        header = struct.unpack(PAGE_HEADER_FORMAT, data[:PAGE_HEADER_SIZE])
        # header se convierte en una tupla: (total_records, active_records, pos_del)
        records = []
        for i in range(header[1]): # solo leemos los activos
            # calcula matemáticamente dónde empieza el alumno número i dentro de los bytes
            start = PAGE_HEADER_SIZE + (i * RECORD_SIZE)
            records.append(AlumnoRecord.unpack(data[start: start + RECORD_SIZE]))
        return Page(header[0], header[1], header[2], records)

class FixedRecord:
    def __init__(self, filename: str, mode: str = "MOVE_THE_LAST"):
        self.filename = filename
        self.mode = mode
        if not os.path.exists(self.filename):
            with open(self.filename, "wb") as f:
                f.write(struct.pack(FILE_HEADER_FORMAT, 0, 0))

    def _get_headers(self):
        with open(self.filename, "rb") as f:
            return struct.unpack(FILE_HEADER_FORMAT, f.read(FILE_HEADER_SIZE))

    def _set_headers(self, pages, total):
        with open(self.filename, "r+b") as f:
            f.seek(0)
            f.write(struct.pack(FILE_HEADER_FORMAT, pages, total))

    def add(self, record: AlumnoRecord): # O(1)
        num_pages, total_active = self._get_headers()
        if num_pages == 0:
            page = Page()
            page.records.append(record)
            page.total_records = 1
            page.active_records = 1
            with open(self.filename, "ab") as f:
                f.write(page.pack())
            self._set_headers(1, 1)
        else:
            # leer última página
            f = open(self.filename, "r+b")
            # buscar dónde empieza la ultima página
            f.seek(FILE_HEADER_SIZE + (num_pages - 1) * PAGE_SIZE)
            # lee los 256 y los convierte en un objeto de python para poder revisar si está llena
            page = Page.unpack(f.read(PAGE_SIZE))
            if len(page.records) < RECORDS_PER_PAGE: # si sí hay espacio en la última página
                page.records.append(record)
                page.total_records += 1
                page.active_records += 1
                # busca el inicio y actualiza la página ya con el nuevo registro
                f.seek(FILE_HEADER_SIZE + (num_pages - 1) * PAGE_SIZE)
                f.write(page.pack())
                # actualiza la información del header global
                self._set_headers(num_pages, total_active + 1)
            else:
                # crear nueva página
                new_page = Page(1, 1, -1, [record])
                f.seek(0, 2)
                f.write(new_page.pack())
                self._set_headers(num_pages + 1, total_active + 1)
            f.close()

    def readRecord(self, pos: int): # O(1)
        num_pages, total_active = self._get_headers()
        if pos < 0 or pos >= total_active:
            return None
        # calcula en qué página está el registro
        page_idx = pos // RECORDS_PER_PAGE
        # calcula la posición dentro de la página
        slot_idx = pos % RECORDS_PER_PAGE
        with open(self.filename, "rb") as f:
            # pone el cursor en donde empieza la página
            f.seek(FILE_HEADER_SIZE + (page_idx * PAGE_SIZE))
            # convierte a un objeto de python esa página
            page = Page.unpack(f.read(PAGE_SIZE))
            # revuelve solo el registro en la posición que encontramos
            return page.records[slot_idx]

    # téctica MOVE_THE_LAST
    def remove_MTL(self, pos: int): # O(1) con MOVE THE LAST
        num_pages, total_active = self._get_headers()
        if pos < 0 or pos >= total_active: return
        last_pos = total_active - 1
        if pos != last_pos:
            # lee el contenido del último registro
            ultimo = self.readRecord(last_pos)
            # sobreescribe el último registro en la posición que queríamos eliminar
            self._update_record(pos, ultimo)
        # eliminar el último físicamente (reducir contador)
        self._pop_last_record()

    def _update_record(self, pos, record):
        # calcula la página y la posición exacta del registro a cambiar
        page_idx = pos // RECORDS_PER_PAGE
        slot_idx = pos % RECORDS_PER_PAGE
        with open(self.filename, "r+b") as f:
            # se posiciona y lee toda la página
            f.seek(FILE_HEADER_SIZE + (page_idx * PAGE_SIZE))
            page = Page.unpack(f.read(PAGE_SIZE))
            # actualiza el registro en la posición encontrada
            page.records[slot_idx] = record
            # guarda la página completa actualizada
            f.seek(FILE_HEADER_SIZE + (page_idx * PAGE_SIZE))
            f.write(page.pack())

    def _pop_last_record(self):
        num_pages, total_active = self._get_headers()
        # ubica la última página
        last_page_idx = num_pages - 1
        with open(self.filename, "r+b") as f:
            # busca la última página y la convierte en un objeto de python
            f.seek(FILE_HEADER_SIZE + (last_page_idx * PAGE_SIZE))
            page = Page.unpack(f.read(PAGE_SIZE))
            # quita el último elemento de la lista de memoria
            page.records.pop()
            # acualiza los contadores del header
            page.total_records -= 1
            page.active_records -= 1
            if page.active_records == 0: # si la página quedó vacía
                # corta el archivo físicamente
                f.truncate(FILE_HEADER_SIZE + (last_page_idx * PAGE_SIZE))
                # actualiza el header global
                self._set_headers(num_pages - 1, total_active - 1)
            else: # si aún quedan registros en esa página
                # guardar la página actualizada
                f.seek(FILE_HEADER_SIZE + (last_page_idx * PAGE_SIZE))
                f.write(page.pack())
                # restar solo al contador de total de registros
                self._set_headers(num_pages, total_active - 1)

    def load(self):
        num_pages, _ = self._get_headers()
        all_records = []
        with open(self.filename, "rb") as f:
            # salta al header global para ir directo a los datos
            f.seek(FILE_HEADER_SIZE)
            for _ in range(num_pages): # por cada página
                # lee una página a la vez
                page = Page.unpack(f.read(PAGE_SIZE))
                # toma todos los registros de esa página y los añade a la lista
                all_records.extend(page.records)
        return all_records

if __name__ == "__main__":
    db = FixedRecord("alumnos.bin")

    # pruebas funcionales MOVE THE LAST
    alumnos_iniciales = generar_alumnos(100)
    for a in alumnos_iniciales:
        db.add(AlumnoRecord(a.codigo, a.nombre, a.apellidos, a.carrera, a.ciclo, a.mensualidad))

    print(f"registros cargados: {len(db.load())}")
    print(f"registro en pos 5: {db.readRecord(5)}")

    print("\neliminando pos 5 (MOVE THE LAST)...")
    db.remove_MTL(5)
    print(f"nuevo registro en pos 5: {db.readRecord(5)}")
    print(f"total después de eliminar: {len(db.load())}")