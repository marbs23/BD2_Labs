import csv
import random
from dataclasses import dataclass

# P1

@dataclass
class Alumno:
    codigo: str
    nombre: str
    apellidos: str
    carrera: str
    ciclo: int
    mensualidad: float

NOMBRES = [
    "Ana", "Luis", "María", "Carlos", "Lucía", "Jorge", "Elena", "Mateo",
    "Camila", "Andrés", "Sofía", "Diego", "Valeria", "Pedro", "Daniela",
    "Renzo", "Ximena", "Alonso", "Paola", "Bruno", "Riki"]

APELLIDOS = [
    "García", "Pérez", "Sánchez", "Torres", "Flores", "Ramírez", "Vargas",
    "Castro", "Rojas", "Navarro", "Mendoza", "Silva", "Romero", "Salazar",
    "Ruiz", "Ortega", "Medina", "Herrera", "Chávez", "Morales", "Nishimura"]

CARRERAS = [
    "Computacion", "Industrial", "Mecatronica", "Bioingenieria",
    "Civil", "Quimica", "Electronica", "Negocios"]

def generar_alumnos(n: int = 110):

    alumnos = []
    for i in range(n):
        alumnos.append(Alumno(
            codigo=f"A{i + 1:04d}"[:5],
            nombre=random.choice(NOMBRES)[:11],
            apellidos=f"{random.choice(APELLIDOS)} {random.choice(APELLIDOS)}"[:20],
            carrera=random.choice(CARRERAS)[:15],
            ciclo=random.randint(1, 10),
            mensualidad=round(random.uniform(1000, 3000), 2)))
    return alumnos

# P2

def generar_csv_p2(filename="datos_p2.csv", n=100):
    codigos_base = ["INF", "MEC", "BIO", "CIV", "IND", "QUIM", "ELEC", "ADMIN", "NEG"]
    sufijos = ["-A", "-PRO", "-LAB", "-XYZ", ""]

    observaciones_pool = [
        "Sin observaciones.",
        "El alumno presenta una beca integral por excelencia deportiva y académica.",
        "Reingresante del periodo 2025-2.",
        "Documentación pendiente: Certificado de salud y copia de DNI legalizada.",
        "Pago fraccionado autorizado por finanzas.",
        "Participante del programa de intercambio con la Universidad de São Paulo.",
        "Ninguna.",
        "Requiere tutoría en el curso de Algoritmos."]

    try:
        with open(filename, mode='w', newline='', encoding='utf-8') as file:
            writer = csv.writer(file)
            writer.writerow(["codigo", "ciclo", "mensualidad", "observaciones"])

            for i in range(n):
                cod = f"{random.choice(codigos_base)}{random.choice(sufijos)}-{i + 1:03d}"
                ciclo = random.randint(1, 10)
                mensualidad = round(random.uniform(1000.50, 4800.00), 2)
                obs = random.choice(observaciones_pool)
                writer.writerow([cod, ciclo, mensualidad, obs])

        print(f"archivo '{filename}' generado con {n} registros exitosamente.")

    except IOError as e:
        print(f"error al crear el archivo: {e}")

if __name__ == "__main__":
    generar_csv_p2()