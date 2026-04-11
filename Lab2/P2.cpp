#include <iostream>
#include <fstream>
#include <sstream>
#include <vector>
#include <string>
#include <cstring>
#include <iomanip>

const int PAGE_SIZE    = 4096;
const int HEADER_SIZE  = 8;    // num_slots(4) + free_ptr(4)
const int SLOT_SIZE    = 8;    // offset(4) + length(4)
const int DELETED      = -1;

struct Matricula {
    std::string codigo;
    int         ciclo;
    double      mensualidad;
    std::string observaciones;
};

//  Serializar Formato: [len_cod(2)][cod][ciclo(4)][mens(8)][len_obs(2)][obs]
std::vector<char> serializar(const Matricula& m) {
    int16_t lc = m.codigo.size();
    int16_t lo = m.observaciones.size();
    int total  = 2 + lc + 4 + 8 + 2 + lo;

    std::vector<char> buf(total);
    int p = 0;

    memcpy(buf.data() + p, &lc, 2);                           p += 2;
    memcpy(buf.data() + p, m.codigo.data(), lc);              p += lc;
    memcpy(buf.data() + p, &m.ciclo, 4);                      p += 4;
    memcpy(buf.data() + p, &m.mensualidad, 8);                p += 8;
    memcpy(buf.data() + p, &lo, 2);                           p += 2;
    memcpy(buf.data() + p, m.observaciones.data(), lo);

    return buf;
}

Matricula deserializar(const char* buf) {
    Matricula m;
    int p = 0;

    int16_t lc; memcpy(&lc, buf + p, 2);         p += 2;
    m.codigo.assign(buf + p, lc);                 p += lc;
    memcpy(&m.ciclo, buf + p, 4);                 p += 4;
    memcpy(&m.mensualidad, buf + p, 8);           p += 8;
    int16_t lo; memcpy(&lo, buf + p, 2);          p += 2;
    m.observaciones.assign(buf + p, lo);

    return m;
}

//  SlottedPage (en memoria, buffer de PAGE_SIZE bytes)
struct SlottedPage {
    char buf[PAGE_SIZE];

    void init() {
        memset(buf, 0, PAGE_SIZE);
        setNumSlots(0);
        setFreePtr(0);
    }

    int  getNumSlots() const  { int v; memcpy(&v, buf,     4); return v; }
    int  getFreePtr()  const  { int v; memcpy(&v, buf + 4, 4); return v; }
    void setNumSlots(int v)   { memcpy(buf,     &v, 4); }
    void setFreePtr(int v)    { memcpy(buf + 4, &v, 4); }

    void getSlot(int i, int& offset, int& length) const {
        int base = HEADER_SIZE + i * SLOT_SIZE;
        memcpy(&offset, buf + base,     4);
        memcpy(&length, buf + base + 4, 4);
    }
    void setSlot(int i, int offset, int length) {
        int base = HEADER_SIZE + i * SLOT_SIZE;
        memcpy(buf + base,     &offset, 4);
        memcpy(buf + base + 4, &length, 4);
    }

    int freeSpace() const {
        int header_end = HEADER_SIZE + getNumSlots() * SLOT_SIZE;
        int data_start = PAGE_SIZE   - getFreePtr();
        return data_start - header_end;
    }

    int insert(const std::vector<char>& rec) {
        int recLen = rec.size();
        if (freeSpace() < recLen + SLOT_SIZE) return -1;

        // Escribir datos desde el final hacia arriba
        int newFreePtr = getFreePtr() + recLen;
        int tupleOffset = PAGE_SIZE - newFreePtr;
        memcpy(buf + tupleOffset, rec.data(), recLen);

        // Registrar slot en el directorio
        int slotId = getNumSlots();
        setSlot(slotId, tupleOffset, recLen);
        setNumSlots(slotId + 1);
        setFreePtr(newFreePtr);

        return slotId;
    }

    // Leer registro por slot_id ──
    Matricula readRecord(int slotId) const {
        int offset, length;
        getSlot(slotId, offset, length);
        if (length == DELETED) throw std::runtime_error("registro eliminado");
        return deserializar(buf + offset);
    }

    // Eliminar: marca el slot como muerto (dead tuple) ──
    void remove(int slotId) {
        int offset, length;
        getSlot(slotId, offset, length);
        if (length == DELETED) throw std::runtime_error("registro ya eliminado");
        setSlot(slotId, offset, DELETED);
    }

    bool isAlive(int slotId) const {
        int offset, length;
        getSlot(slotId, offset, length);
        return length != DELETED;
    }
};

struct RID { int pageId, slotId; };

class HeapFile {
    std::string filename;

    int numPages() const {
        std::ifstream f(filename, std::ios::binary | std::ios::ate);
        if (!f) return 0;
        return f.tellg() / PAGE_SIZE;
    }

    SlottedPage readPage(int pageId) const {
        SlottedPage pg;
        std::ifstream f(filename, std::ios::binary);
        f.seekg(pageId * PAGE_SIZE);
        f.read(pg.buf, PAGE_SIZE);
        return pg;
    }

    void writePage(int pageId, const SlottedPage& pg) {
        std::fstream f(filename, std::ios::binary | std::ios::in | std::ios::out);
        f.seekp(pageId * PAGE_SIZE);
        f.write(pg.buf, PAGE_SIZE);
    }

    int appendPage() {
        int pid = numPages();   // id ANTES de agregar
        SlottedPage pg; pg.init();
        std::ofstream f(filename, std::ios::binary | std::ios::app);
        f.write(pg.buf, PAGE_SIZE);
        return pid;
    }

public:
    HeapFile(const std::string& fname) : filename(fname) {
        std::ifstream test(filename, std::ios::binary);
        if (!test) std::ofstream(filename, std::ios::binary); // crear si no existe
    }

    // add: inserta un registro; O(1) ──
    RID add(const Matricula& m) {
        auto rec = serializar(m);
        int np = numPages();

        // buscar la última página con espacio suficiente
        for (int pid = np - 1; pid >= 0; --pid) {
            SlottedPage pg = readPage(pid);
            int sid = pg.insert(rec);
            if (sid != -1) {
                writePage(pid, pg);
                return {pid, sid};
            }
        }

        // no hay espacio: crear página nueva
        int pid = appendPage();
        SlottedPage pg = readPage(pid);
        int sid = pg.insert(rec);
        writePage(pid, pg);
        return {pid, sid};
    }

    // readRecord: acceso directo por RID; O(1) ──
    Matricula readRecord(RID rid) const {
        SlottedPage pg = readPage(rid.pageId);
        return pg.readRecord(rid.slotId);
    }

    // remove: eliminación lógica; O(1) -1 si esta muerto
    void remove(RID rid) {
        SlottedPage pg = readPage(rid.pageId);
        pg.remove(rid.slotId);
        writePage(rid.pageId, pg);
    }

    // load: devuelve todos los registros válidos ──
    std::vector<Matricula> load() const {
        std::vector<Matricula> result;
        for (int pid = 0; pid < numPages(); ++pid) {
            SlottedPage pg = readPage(pid);
            for (int sid = 0; sid < pg.getNumSlots(); ++sid)
                if (pg.isAlive(sid))
                    result.push_back(pg.readRecord(sid));
        }
        return result;
    }

    void printPageInfo() const {
        std::cout << "\n=== Páginas en disco ===\n";
        for (int pid = 0; pid < numPages(); ++pid) {
            SlottedPage pg = readPage(pid);
            int alive = 0;
            for (int s = 0; s < pg.getNumSlots(); ++s)
                if (pg.isAlive(s)) alive++;
            std::cout << "  Página " << pid
                      << " | slots=" << pg.getNumSlots()
                      << " | activos=" << alive
                      << " | libre=" << pg.freeSpace() << " bytes\n";
        }
    }
};

std::vector<Matricula> leerCSV(const std::string& archivo) {
    std::vector<Matricula> resultado;
    std::ifstream f(archivo);
    if (!f) { std::cerr << "No se pudo abrir: " << archivo << "\n"; return resultado; }

    std::string linea;
    std::getline(f, linea); // saltar cabecera

    while (std::getline(f, linea)) {
        if (linea.empty()) continue;
        // parseo manual que respeta comas dentro de comillas
        std::vector<std::string> campos;
        std::string campo;
        bool en_comillas = false;
        for (char c : linea) {
            if (c == '"') { en_comillas = !en_comillas; }
            else if (c == ',' && !en_comillas) { campos.push_back(campo); campo.clear(); }
            else if (c != '\r') campo += c;
        }
        campos.push_back(campo);

        Matricula m;
        m.codigo        = campos[0];
        m.ciclo         = std::stoi(campos[1]);
        m.mensualidad   = std::stod(campos[2]);
        m.observaciones = campos[3];
        resultado.push_back(m);
    }
    return resultado;
}

void imprimirMatricula(const Matricula& m) {
    std::cout << "  codigo=" << std::left << std::setw(18) << m.codigo
              << " ciclo=" << std::setw(3) << m.ciclo
              << " mensualidad=" << std::fixed << std::setprecision(2) << std::setw(8) << m.mensualidad
              << " obs=[" << m.observaciones.substr(0, 35)
              << (m.observaciones.size() > 35 ? "..." : "") << "]\n";
}

int main() {
    const std::string archivo_bin = "matriculas.bin";
    const std::string archivo_csv = "datos_p2.csv";
    std::remove(archivo_bin.c_str());

    std::cout << "=== P2: Heap File con SlottedPage (Longitud Variable) ===\n\n";

    // cargar datos desde CSV
    auto datos = leerCSV(archivo_csv);
    std::cout << datos.size() << " registros cargados desde '" << archivo_csv << "'\n";
    if (datos.empty()) {
        std::cerr << "Ejecuta primero: python3 generar_datos.py\n";
        return 1;
    }

    HeapFile hf(archivo_bin);

    // TEST 1: add() ──
    std::cout << "\n--- TEST 1: add() - insertar " << datos.size() << " registros ---\n";
    std::vector<RID> rids;
    for (const auto& m : datos)
        rids.push_back(hf.add(m));
    std::cout << "insertados: " << rids.size() << " registros\n";
    hf.printPageInfo();

    // TEST 2: readRecord() ──
    std::cout << "\n--- TEST 2: readRecord() - leer posiciones 0, 49, 99 ---\n";
    for (int i : {0, 49, 99}) {
        std::cout << "  [page=" << rids[i].pageId << " slot=" << rids[i].slotId << "]\n";
        imprimirMatricula(hf.readRecord(rids[i]));
    }

    // TEST 3: remove() ──
    std::cout << "\n--- TEST 3: remove() - eliminar indices 5, 10, 20, 30, 50 ---\n";
    for (int i : {5, 10, 20, 30, 50}) {
        hf.remove(rids[i]);
        std::cout << "  eliminado: " << datos[i].codigo
                  << " (page=" << rids[i].pageId << " slot=" << rids[i].slotId << ")\n";
    }

    std::cout << "\n  intentando leer registro eliminado (idx 5)...\n";
    try {
        hf.readRecord(rids[5]);
    } catch (const std::exception& e) {
        std::cout << "  OK: " << e.what() << "\n";
    }

    // TEST 4: load() ──
    std::cout << "\n--- TEST 4: load() - cargar todos los válidos ---\n";
    auto activos = hf.load();
    std::cout << "  activos: " << activos.size() << " (esperado: 95)\n";
    std::cout << "  primeros 3:\n";
    for (int i = 0; i < 3; ++i) imprimirMatricula(activos[i]);

    // TEST 5: add() tras eliminaciones ──
    std::cout << "\n--- TEST 5: add() tras eliminaciones ---\n";
    Matricula nuevo = {"TEST-NUEVO", 3, 1800.50, "Registro de prueba post-eliminacion."};
    RID rid_nuevo = hf.add(nuevo);
    std::cout << "  nuevo RID -> page=" << rid_nuevo.pageId << " slot=" << rid_nuevo.slotId << "\n";
    imprimirMatricula(hf.readRecord(rid_nuevo));

    hf.printPageInfo();
    std::cout << "\n=== PRUEBAS COMPLETADAS ===\n";
    return 0;
}