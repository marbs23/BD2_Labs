from dataclasses import dataclass
from typing import Optional, List, Tuple
import struct
import os


@dataclass
class Node:
    # campos de datos
    id: int
    name: str
    age: int
    country: str
    department: str
    pos: str
    salary: float
    joining_date: str
    # campos de control del árbol
    left: int = -1
    right: int = -1
    height: int = 1


class BSTFile:
    # formato: i (id), 30s (name), i (age), 20s (country), 20s (dept),
    # 20s (pos), f (salary), 10s (date) + iii (left, right, height)
    # total bytes: 4+30+4+20+20+20+4+10 + 4+4+4 = 120 bytes por nodo
    HEADER_FORMAT = 'ii' # size, root_ptr
    NODE_FORMAT = 'i30si20s20s20sf10siii'

    HEADER_SIZE = struct.calcsize(HEADER_FORMAT)
    NODE_SIZE = struct.calcsize(NODE_FORMAT)

    def __init__(self, filename: str):
        self.filename = filename
        file_exists = os.path.exists(filename)
        new_file = not file_exists or os.path.getsize(filename) == 0
        self.file = open(filename, 'r+b' if file_exists else 'w+b')
        if new_file:
            self._write_header(0, -1)

    def _read_header(self) -> Tuple[int, int]:
        self.file.seek(0)
        data = self.file.read(self.HEADER_SIZE)
        if len(data) != self.HEADER_SIZE:
            return 0, -1
        return struct.unpack(self.HEADER_FORMAT, data)

    def _write_header(self, size: int, root_ptr: int) -> None:
        self.file.seek(0)
        self.file.write(struct.pack(self.HEADER_FORMAT, size, root_ptr))
        self.file.flush()

    def _node_offset(self, index: int) -> int:
        return self.HEADER_SIZE + index * self.NODE_SIZE

    def _pack_node(self, node: Node) -> bytes:
        return struct.pack(
            self.NODE_FORMAT,
            node.id,
            node.name.encode("utf-8")[:30].ljust(30, b"\x00"),
            node.age,
            node.country.encode("utf-8")[:20].ljust(20, b"\x00"),
            node.department.encode("utf-8")[:20].ljust(20, b"\x00"),
            node.pos.encode("utf-8")[:20].ljust(20, b"\x00"),
            node.salary,
            node.joining_date.encode("utf-8")[:10].ljust(10, b"\x00"),
            node.left,
            node.right,
            node.height)

    def _unpack_node(self, data: bytes) -> Node:
        parts = struct.unpack(self.NODE_FORMAT, data)
        return Node(
            id=parts[0],
            name=parts[1].decode("utf-8").rstrip('\x00').strip(),
            age=parts[2],
            country=parts[3].decode("utf-8").rstrip('\x00').strip(),
            department=parts[4].decode("utf-8").rstrip('\x00').strip(),
            pos=parts[5].decode("utf-8").rstrip('\x00').strip(),
            salary=round(parts[6], 3),
            joining_date=parts[7].decode("utf-8").rstrip('\x00').strip(),
            left=parts[8],
            right=parts[9],
            height=parts[10])

    def _read_node(self, index: int) -> Node:
        self.file.seek(self._node_offset(index))
        data = self.file.read(self.NODE_SIZE)
        if len(data) != self.NODE_SIZE:
            raise IndexError(f"Nodo inválido en índice {index}")
        return self._unpack_node(data)

    def _write_node(self, index: int, node: Node) -> None:
        self.file.seek(self._node_offset(index))
        self.file.write(self._pack_node(node))
        self.file.flush()

    # utilidades avl

    def _get_height(self, index: int) -> int:
        if index == -1:
            return 0
        return self._read_node(index).height

    def _get_balance(self, index: int) -> int:
        if index == -1:
            return 0
        node = self._read_node(index)
        return self._get_height(node.left) - self._get_height(node.right)

    def _update_height(self, index: int) -> None:
        node = self._read_node(index)
        node.height = 1 + max(self._get_height(node.left),
                              self._get_height(node.right))
        self._write_node(index, node)

    # rotaciones

    def _right_rotate(self, y_index: int) -> int:
        y = self._read_node(y_index)
        x_index = y.left
        x = self._read_node(x_index)

        y.left = x.right
        x.right = y_index

        self._write_node(y_index, y)
        self._update_height(y_index)

        self._write_node(x_index, x)
        self._update_height(x_index)
        return x_index

    def _left_rotate(self, x_index: int) -> int:
        x = self._read_node(x_index)
        y_index = x.right
        y = self._read_node(y_index)

        x.right = y.left
        y.left = x_index

        self._write_node(x_index, x)
        self._update_height(x_index)

        self._write_node(y_index, y)
        self._update_height(y_index)
        return y_index

    def _rebalance(self, index: int, key: int) -> int:
        balance = self._get_balance(index)
        node = self._read_node(index)

        if balance > 1:
            left_child = self._read_node(node.left)
            if key < left_child.id:
                return self._right_rotate(index)
            else:
                node.left = self._left_rotate(node.left)
                self._write_node(index, node)
                return self._right_rotate(index)

        if balance < -1:
            right_child = self._read_node(node.right)
            if key > right_child.id:
                return self._left_rotate(index)
            else:
                node.right = self._right_rotate(node.right)
                self._write_node(index, node)
                return self._left_rotate(index)

        return index

    # operaciones

    def _insert_rec(self, index: int, new_node: Node) -> int:
        if index == -1:
            size, _ = self._read_header()
            self._write_node(size, new_node)
            return size

        current = self._read_node(index)
        if new_node.id < current.id:
            current.left = self._insert_rec(current.left, new_node)
        elif new_node.id > current.id:
            current.right = self._insert_rec(current.right, new_node)
        else:
            return index

        self._write_node(index, current)
        self._update_height(index)
        return self._rebalance(index, new_node.id)

    def insert(self, node: Node) -> None:
        size, root = self._read_header()
        new_root = self._insert_rec(root, node)
        self._write_header(size + 1, new_root)

    def search(self, id_key: int) -> Optional[Node]:
        _, root_ptr = self._read_header()
        curr = root_ptr
        while curr != -1:
            node = self._read_node(curr)
            if id_key == node.id: return node
            curr = node.left if id_key < node.id else node.right
        return None

    def _find_min(self, index: int) -> int:
        curr = index
        while True:
            node = self._read_node(curr)
            if node.left == -1: return curr
            curr = node.left

    def _delete_rec(self, index: int, key: int) -> Tuple[int, bool]:
        if index == -1: return -1, False

        node = self._read_node(index)
        deleted = False

        if key < node.id:
            node.left, deleted = self._delete_rec(node.left, key)
        elif key > node.id:
            node.right, deleted = self._delete_rec(node.right, key)
        else:
            deleted = True
            if node.left == -1: return node.right, True
            if node.right == -1: return node.left, True

            successor_idx = self._find_min(node.right)
            successor = self._read_node(successor_idx)
            node.id = successor.id
            node.name = successor.name
            node.age = successor.age
            node.country = successor.country
            node.department = successor.department
            node.pos = successor.pos
            node.salary = successor.salary
            node.joining_date = successor.joining_date

            node.right, _ = self._delete_rec(node.right, successor.id)

        self._write_node(index, node)
        self._update_height(index)

        balance = self._get_balance(index)
        if balance > 1:
            if self._get_balance(node.left) >= 0:
                return self._right_rotate(index), True
            node.left = self._left_rotate(node.left)
            self._write_node(index, node)
            return self._right_rotate(index), True
        if balance < -1:
            if self._get_balance(node.right) <= 0:
                return self._left_rotate(index), True
            node.right = self._right_rotate(node.right)
            self._write_node(index, node)
            return self._left_rotate(index), True

        return index, deleted

    def delete(self, id_key: int) -> bool:
        size, root = self._read_header()
        new_root, deleted = self._delete_rec(root, id_key)
        if deleted:
            self._write_header(size - 1, new_root)
        return deleted

    def range_search(self, low: int, high: int) -> List[Node]:
        result = []
        _, root = self._read_header()

        def _inorder(idx):
            if idx == -1: return
            node = self._read_node(idx)
            if node.id > low: _inorder(node.left)
            if low <= node.id <= high: result.append(node)
            if node.id < high: _inorder(node.right)

        _inorder(root)
        return result

    @classmethod
    def from_csv(cls, filename: str, csv_path: str) -> 'BSTFile':
        import csv
        if os.path.exists(filename): os.remove(filename)
        bst = cls(filename)
        with open(csv_path, newline='', encoding='utf-8') as f:
            reader = csv.reader(f, delimiter=';')
            next(reader)
            for row in reader:
                bst.insert(Node(
                    id=int(row[0]), name=row[1], age=int(row[2]),
                    country=row[3], department=row[4], pos=row[5],
                    salary=float(row[6]), joining_date=row[7]
                ))
        return bst

    def close(self) -> None:
        self.file.close()