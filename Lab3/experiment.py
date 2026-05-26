import time
import csv
import os
import random
import matplotlib.pyplot as plt
from sequential import SequentialFile, Record
from bst import BSTFile, Node


# utilidades

def load_csv(csv_path: str):
    records = []
    with open(csv_path, newline='', encoding='utf-8') as f:
        reader = csv.reader(f, delimiter=';')
        next(reader)
        for row in reader:
            records.append(Record(
                id=int(row[0]), name=row[1], age=int(row[2]),
                country=row[3], department=row[4], pos=row[5],
                salary=float(row[6]), joining_Date=row[7]))
    return records


def to_node(r: Record) -> Node:
    return Node(
        id=r.id, name=r.name, age=r.age, country=r.country,
        department=r.department, pos=r.pos, salary=r.salary,
        joining_date=r.joining_Date)


# experimentos

def run_full_experiment():
    # fijamos la semilla para que los IDs elegidos sean siempre los mismos
    random.seed(42)
    all_records = load_csv("employee.csv")
    total = len(all_records)

    # definimos los tamaños N de manera uniforme
    sample_sizes = [int(total * p) for p in [0.10, 0.25, 0.50, 0.75]]

    results = {
        "Insert": ([], []), "Search": ([], []),
        "Range": ([], []), "Delete": ([], [])}

    for n in sample_sizes:
        print(f"\n>>> Iniciando pruebas para N = {n} registros")

        # 1. PREPARACIÓN DE DATOS (uniforme para ambos)
        initial_data = all_records[:n]
        # seleccionamos los mismos objetivos para ambas estructuras
        target_ids = [r.id for r in random.sample(initial_data, 50)]
        ids_to_delete = [r.id for r in random.sample(initial_data, 20)]
        extra_records = all_records[n: n + 20]
        low_range = random.choice(target_ids)
        high_range = low_range + 1000

        # sequential file -------
        f_seq = f"data_{n}.seq"
        if os.path.exists(f_seq): os.remove(f_seq)

        sf = SequentialFile(f_seq, k_threshold=n//4)
        for r in initial_data: sf.insert(r)

        # medir search seq
        start = time.time()
        for i in target_ids: sf.search(i)
        results["Search"][0].append((time.time() - start) / 50)

        # medir range seq
        start = time.time()
        sf.range_search(low_range, high_range)
        results["Range"][0].append(time.time() - start)

        # medir delete seq
        start = time.time()
        for i in ids_to_delete: sf.delete(i)
        results["Delete"][0].append((time.time() - start) / 20)

        # medir insert seq
        start = time.time()
        for r in extra_records: sf.insert(r)
        results["Insert"][0].append((time.time() - start) / 20)

        sf.close()

        # avl file -------
        f_avl = f"data_{n}.avl"
        if os.path.exists(f_avl): os.remove(f_avl)

        bst = BSTFile(f_avl)
        for r in initial_data: bst.insert(to_node(r))

        # medir search avl
        start = time.time()
        for i in target_ids: bst.search(i)
        results["Search"][1].append((time.time() - start) / 50)

        # medir range avl
        start = time.time()
        bst.range_search(low_range, high_range)
        results["Range"][1].append(time.time() - start)

        # medir delete avl
        start = time.time()
        for i in ids_to_delete: bst.delete(i)
        results["Delete"][1].append((time.time() - start) / 20)

        # medir insert avl
        start = time.time()
        for r in extra_records: bst.insert(to_node(r))
        results["Insert"][1].append((time.time() - start) / 20)

        bst.close()

        # limpieza física de archivos para no afectar el espacio en disco/N siguiente
        os.remove(f_seq)
        os.remove(f_avl)

    return sample_sizes, results


# gráficos

def plot_results(sizes, res):
    fig, axs = plt.subplots(2, 2, figsize=(15, 10))
    fig.suptitle('Comparativa Uniforme: Sequential File vs AVL File', fontsize=16)

    metrics = [
        ("Insert", 0, 0, "Tiempo Promedio Inserción (s)"),
        ("Search", 0, 1, "Tiempo Promedio Búsqueda (s)"),
        ("Range", 1, 0, "Tiempo Total Búsqueda Rango (s)"),
        ("Delete", 1, 1, "Tiempo Promedio Eliminación (s)")]

    for key, r, c, ylabel in metrics:
        axs[r, c].plot(sizes, res[key][0], 'o-', label='Sequential', color='blue')
        axs[r, c].plot(sizes, res[key][1], 's-', label='AVL', color='red')
        axs[r, c].set_title(f"Operación: {key}")
        axs[r, c].set_xlabel("Registros en archivo (N)")
        axs[r, c].set_ylabel(ylabel)
        axs[r, c].legend()
        axs[r, c].grid(True, alpha=0.3)

    plt.tight_layout(rect=[0, 0.03, 1, 0.95])
    plt.savefig("resultados_uniformes.png")
    plt.show()


if __name__ == "__main__":
    sizes, res = run_full_experiment()
    plot_results(sizes, res)