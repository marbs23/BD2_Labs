"""Archivo secuencial con área auxiliar.

- Cabecera: struct 'ii' -> (ordered_count, aux_count)
  - ordered_count: número de registros en la parte ordenada inicial
  - aux_count: número de registros en el área auxiliar (insertados al final)

Los registros están ordenados por id en la parte ordenada. Los nuevos
registros se agregan al final del archivo (área auxiliar). Cuando aux_count
supera un umbral k, se debe reconstruir el archivo mezclando la parte ordenada
con los registros auxiliares para producir un único archivo ordenado.

Opcionalmente, puede implementar la estrategia de punteros para gestionar mejor los eliminados.
"""
from dataclasses import dataclass
from typing import Optional, List, Tuple
import struct
import os


@dataclass
class Record:
    id: int
    name: str
    age: int
    country: str
    department: str
    pos: str
    salary: float
    joining_Date: str

class SequentialFile:
    
    HEADER_FORMAT = 'ii'
    RECORD_FORMAT = 'i30si20s20s20sf10s'

    HEADER_SIZE = struct.calcsize(HEADER_FORMAT)
    RECORD_SIZE = struct.calcsize(RECORD_FORMAT)

    def __init__(self, filename: str, k_threshold: int = 100):
        self.filename = filename
        self.k_threshold = k_threshold

        if not os.path.exists(filename):
            self.file = open(filename, 'w+b')
            self._write_header(0, 0)
        else:
            self.file = open(filename, 'r+b')

    @classmethod
    def from_csv(cls, filename: str, csv_path: str, k_threshold: int = 100) -> 'SequentialFile':
        import csv

        records: List[Record] = []

        with open(csv_path, newline='', encoding='utf-8') as f:
            reader = csv.reader(f, delimiter=';')
            next(reader)

            for row in reader:
                records.append(Record(
                    id=int(row[0]),
                    name=row[1],
                    age=int(row[2]),
                    country=row[3],
                    department=row[4],
                    pos=row[5],
                    salary=float(row[6]),
                    joining_Date=row[7]
                ))

        records.sort(key=lambda r: r.id)

        # crear archivo
        self = cls(filename, k_threshold)

        self.file.seek(self.HEADER_SIZE)
        self.file.truncate()

        # escribir
        for rec in records:
            self.file.write(self._pack_record(rec))

        # actualizar cabecera
        self._write_header(len(records), 0)

        return self

    def _read_header(self) -> Tuple[int, int]:
        self.file.seek(0)
        return struct.unpack(self.HEADER_FORMAT,
                                self.file.read(self.HEADER_SIZE))

    def _write_header(self, ordered_count: int, aux_count: int) -> None:
        self.file.seek(0)
        self.file.write(struct.pack(self.HEADER_FORMAT,
                                   ordered_count, aux_count))
        self.file.flush()

    def _pack_record(self, rec: Record) -> bytes:
        return struct.pack(
            self.RECORD_FORMAT,
            rec.id,
            rec.name.encode("utf-8")[:30].ljust(30, b"\x00"),
            rec.age,
            rec.country.encode("utf-8")[:20].ljust(20, b"\x00"),
            rec.department.encode("utf-8")[:20].ljust(20, b"\x00"),
            rec.pos.encode("utf-8")[:20].ljust(20, b"\x00"),
            rec.salary,
            rec.joining_Date.encode("utf-8")[:10].ljust(10, b"\x00"),
        )

    def _unpack_record(self, data: bytes) -> Record:
        id, name, age, country, department, pos, salary, joining_Date = struct.unpack(SequentialFile.RECORD_FORMAT, data)
        return Record(
            id,
            name.decode("utf-8").rstrip('\x00').strip(),
            age,
            country.decode("utf-8").rstrip('\x00').strip(),
            department.decode("utf-8").rstrip('\x00').strip(),
            pos.decode("utf-8").rstrip('\x00').strip(),
            round(salary,3),
            joining_Date.decode("utf-8").rstrip('\x00').strip(),
            )
    def _offset(self, index: int) -> int:
        return self.HEADER_SIZE + index * self.RECORD_SIZE

    def _read_record(self, index: int) -> Record:
        self.file.seek(self._offset(index))
        return self._unpack_record(self.file.read(self.RECORD_SIZE))

    def _write_record(self, index: int, rec: Record):
        self.file.seek(self._offset(index))
        self.file.write(self._pack_record(rec))

    def binary_search(self, id_key: int) -> Tuple[Optional[Record], int]:
        ordered_count, _ = self._read_header()
        beg = 0
        end = ordered_count-1
        while (beg <= end):
            mid = (beg+end)//2
            midRecord = self._read_record(mid)
            if  midRecord.id == -1:
                beg = mid + 1
                continue
            if midRecord.id == id_key:
                return midRecord, mid
            if midRecord.id <= id_key:
                beg = mid + 1
            else:
                end = mid - 1
        return None, -1


    def search(self, id_key: int) -> Optional[Record]:
        ordered_count, aux_count = self._read_header()
        result, _ = self.binary_search(id_key)
        if (result is not None):
            return result
        
        for i in range(aux_count):
            result = self._read_record(ordered_count+i)
            if result.id == id_key:
                return result
        return None

    def insert(self, rec: Record) -> int:
            ordered_count, aux_count = self._read_header()
            index = ordered_count + aux_count
            self._write_record(index, rec)
            aux_count += 1
            self._write_header(ordered_count, aux_count)
            if aux_count > self.k_threshold:
                self._rebuild()
            return index

    def delete(self, id_key: int) -> bool:
            ordered_count, aux_count = self._read_header()
            rec, idx = self.binary_search(id_key)
            if rec is not None:
                rec.id = -1
                self._write_record(idx, rec)
                return True

            for i in range(ordered_count, ordered_count + aux_count):
                rec = self._read_record(i)
                if rec.id == id_key:
                    rec.id = -1
                    self._write_record(i, rec)
                    return True

            return False
    
    def range_search(self, low_id: int, high_id: int) -> List[Record]:
        ordered_count, aux_count = self._read_header()
        results: List[Record] = []

        beg, end, start = 0, ordered_count - 1, 0
        while beg <= end:
            mid = (beg + end) // 2
            mid_id = self._read_record(mid).id
            if mid_id == -1 or mid_id < low_id:
                beg = mid + 1
            else:
                start = mid
                end = mid - 1

        for i in range(start, ordered_count + aux_count):
            rec = self._read_record(i)
            if rec.id != -1 and low_id <= rec.id <= high_id:
                results.append(rec)

        return results
    
    def _rebuild(self) -> None:
        ordered_count, aux_count = self._read_header()
        aux: List[Record] = []

        for i in range(ordered_count, ordered_count + aux_count):
            rec = self._read_record(i)
            if rec.id != -1:
                aux.append(rec)

        aux.sort(key=lambda r: r.id)

        tmp_path = self.filename + ".tmp"

        with open(tmp_path, 'wb') as tmp:
            tmp.write(struct.pack(self.HEADER_FORMAT, 0, 0))

            i = j = merged_count = 0

            while i < ordered_count and j < len(aux):
                rec_ord = self._read_record(i)
                if rec_ord.id == -1:
                    i += 1
                    continue
                if rec_ord.id <= aux[j].id:
                    tmp.write(self._pack_record(rec_ord))
                    i += 1
                else:
                    tmp.write(self._pack_record(aux[j]))
                    j += 1
                merged_count += 1

            while i < ordered_count:
                rec_ord = self._read_record(i)
                i += 1
                if rec_ord.id == -1:
                    continue
                tmp.write(self._pack_record(rec_ord))
                merged_count += 1

            while j < len(aux):
                tmp.write(self._pack_record(aux[j]))
                j += 1
                merged_count += 1


            tmp.seek(0)
            tmp.write(struct.pack(self.HEADER_FORMAT, merged_count, 0))
        self.file.close()
        os.replace(tmp_path, self.filename)
        self.file = open(self.filename, 'r+b')


    def close(self) -> None:
        self.file.flush()
        self.file.close()


def main():
    # Cargar desde CSV
    sf = SequentialFile.from_csv("employees.bin", "employee.csv", k_threshold=5)

    # Buscar
    rec = sf.search(17648)
    print(rec)

    # Insertar
    nuevo = Record(
        id=99999,
        name="John Doe",
        age=30,
        country="USA",
        department="IT",
        pos="Manager",
        salary=90000.0,
        joining_Date="01/01/2024"
    )
    sf.insert(nuevo)
    print(sf.search(99999))

    # Eliminar
    sf.delete(16986)
    print(sf.search(16986))  # debe retornar None

    # Range search
    resultados = sf.range_search(16000, 16004)
    for r in resultados:
        print(r)

    sf.close()

if __name__ == "__main__":
    main()
