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
        records = []
        for i in range(RECORDS_PER_PAGE):  # leer TODOS los slots físicos
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

        if self.mode == "FREE_LIST":
            for page_idx in range(num_pages):
                with open(self.filename, "r+b") as f:
                    f.seek(FILE_HEADER_SIZE + (page_idx * PAGE_SIZE))
                    page = Page.unpack(f.read(PAGE_SIZE))

                    if page.pos_del != -1:
                        free_slot = page.pos_del
                        offset = FILE_HEADER_SIZE + (page_idx * PAGE_SIZE) + PAGE_HEADER_SIZE + (free_slot * RECORD_SIZE)
                        f.seek(offset)
                        data = f.read(RECORD_SIZE)
                        next_free = struct.unpack("i", data[-4:])[0]
                        page.pos_del = next_free
                        f.seek(offset)
                        f.write(record.pack())
                        page.active_records += 1
                        f.seek(FILE_HEADER_SIZE + (page_idx * PAGE_SIZE))
                        f.write(struct.pack(PAGE_HEADER_FORMAT, page.total_records, page.active_records, page.pos_del))
                        self._set_headers(num_pages, total_active + 1)
                        return

        # inserción normal al final (usado por MTL siempre, y por FREE_LIST cuando no hay espacios libres)
        if num_pages == 0:
            page = Page(total=1, active=1, pos_del=-1,
                        records=[AlumnoRecord("", "", "", "", 0, 0.0)] * RECORDS_PER_PAGE)
            page.records[0] = record
            with open(self.filename, "ab") as f:
                f.write(page.pack())
            self._set_headers(1, 1)
        else:
            f = open(self.filename, "r+b")
            f.seek(FILE_HEADER_SIZE + (num_pages - 1) * PAGE_SIZE)
            page = Page.unpack(f.read(PAGE_SIZE))

            if page.total_records < RECORDS_PER_PAGE:  # usa total_records, no len()
                page.records[page.total_records] = record  # escribe en el slot correcto
                page.total_records += 1
                page.active_records += 1

                f.seek(FILE_HEADER_SIZE + (num_pages - 1) * PAGE_SIZE)
                f.write(page.pack())
                self._set_headers(num_pages, total_active + 1)
            else:
                new_page = Page(total=1, active=1, pos_del=-1,
                                records=[AlumnoRecord("", "", "", "", 0, 0.0)] * RECORDS_PER_PAGE)
                new_page.records[0] = record
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
            if slot_idx >= page.total_records:
                return None

            record = page.records[slot_idx]
            if self.mode == "FREE_LIST" and record.codigo == "":
                return None

        return record

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

    def remove_FL(self, pos: int): # O(1)
        num_pages, total_active = self._get_headers()
        if pos < 0 or pos >= total_active:
            return

        page_idx = pos // RECORDS_PER_PAGE
        slot_idx = pos % RECORDS_PER_PAGE

        with open(self.filename, "r+b") as f:
            f.seek(FILE_HEADER_SIZE + (page_idx * PAGE_SIZE))
            page = Page.unpack(f.read(PAGE_SIZE))

            # calcular offset del registro
            offset = FILE_HEADER_SIZE + (page_idx * PAGE_SIZE) + PAGE_HEADER_SIZE + (slot_idx * RECORD_SIZE)

            # guardar actual head de free list dentro del registro eliminado
            next_free = page.pos_del

            # escribimos basura + puntero al siguiente libre
            f.seek(offset)
            f.write(b"\x00" * (RECORD_SIZE - 4) + struct.pack("i", next_free))

            # actualizar cabeza de lista libre
            page.pos_del = slot_idx
            page.active_records -= 1

            # guardar solo el header de página, no sobrescribimos el registro libre
            f.seek(FILE_HEADER_SIZE + (page_idx * PAGE_SIZE))
            f.write(struct.pack(PAGE_HEADER_FORMAT, page.total_records, page.active_records, page.pos_del))

            # actualizar header global
            self._set_headers(num_pages, total_active - 1)

    def _update_record(self, pos, record):
        # calcula la página y la posición exacta del registro a cambiar
        page_idx = pos // RECORDS_PER_PAGE
        slot_idx = pos % RECORDS_PER_PAGE
        with open(self.filename, "r+b") as f:
            # se posiciona y lee toda la página
            f.seek(FILE_HEADER_SIZE + (page_idx * PAGE_SIZE))
            page = Page.unpack(f.read(PAGE_SIZE))

            # asegurar que la lista tiene suficientes slots
            while len(page.records) <= slot_idx:
                page.records.append(AlumnoRecord("", "", "", "", 0, 0.0))

            # actualiza el registro en la posición encontrada
            page.records[slot_idx] = record
            # guarda la página completa actualizada
            f.seek(FILE_HEADER_SIZE + (page_idx * PAGE_SIZE))
            f.write(page.pack())

    def remove(self, pos: int):
        if self.mode == "MOVE_THE_LAST":
            self.remove_MTL(pos)
        elif self.mode == "FREE_LIST":
            self.remove_FL(pos)

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
                # toma solo los registros válidos: los slots eliminados quedan con codigo vacío
                for record in page.records[:page.total_records]:
                    if record.codigo != "":
                        all_records.append(record)
        return all_records

if __name__ == "__main__":
    if os.path.exists("alumnos.bin"):
        os.remove("alumnos.bin")

    db = FixedRecord("alumnos.bin", mode="MOVE_THE_LAST")

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

    print("\n--- PRUEBAS FREE LIST ---")

    if os.path.exists("alumnos_fl.bin"):
        os.remove("alumnos_fl.bin")

    db_fl = FixedRecord("alumnos_fl.bin", mode="FREE_LIST")

    alumnos_fl = generar_alumnos(100)
    for a in alumnos_fl:
        db_fl.add(AlumnoRecord(a.codigo, a.nombre, a.apellidos, a.carrera, a.ciclo, a.mensualidad))

    print(f"registros cargados (FL): {len(db_fl.load())}")
    print(f"registro en pos 10 (FL): {db_fl.readRecord(10)}")

    print("\neliminando pos 10, 20, 30 (FREE LIST)...")
    db_fl.remove_FL(10)
    db_fl.remove_FL(20)
    db_fl.remove_FL(30)
    print(f"total después de 3 eliminaciones: {len(db_fl.load())}")

    # verificar None ANTES de reinsertar
    print(f"pos 10 eliminada devuelve None: {db_fl.readRecord(10)}")
    print(f"pos 20 eliminada devuelve None: {db_fl.readRecord(20)}")

    print("\ninsertando 3 nuevos registros (deben reusar espacios libres)...")
    nuevos = generar_alumnos(3)
    for a in nuevos:
        db_fl.add(AlumnoRecord(a.codigo, a.nombre, a.apellidos, a.carrera, a.ciclo, a.mensualidad))
    print(f"total después de reinsertar: {len(db_fl.load())}")
    print(f"pos 10 ahora tiene nuevo registro: {db_fl.readRecord(10)}")