"""
NuitkaShield v9.7 — Layer 2: Unicode Name Mangling (Fix Nonlocal/Global Scope)
✅ Counter-based uniqueness | ✅ Scope-aware arg processing | ✅ F-String safe
✅ Fix: Đảm bảo nonlocal/global trỏ đúng biến đã được mangle
"""
from __future__ import annotations
import ast
import hashlib
from typing import Set, Dict, List

_UNICODE_POOL = list(
    "αβγδεζηθικλμνξοπρστυφχψω"
    "ΑΒΓΔΕΖΗΘΙΚΛΜΝΞΟΠΡΣΤΥΦΧΨΩ"
    "абвгдежзийклмнопрстуфхцчшщ"
    "АБВГДЕЖЗИЙКЛМНОПРСТУФХЦЧШ"
    "𝔞𝔟𝔠𝔡𝔢𝔣𝔤𝔥𝔦𝔧𝔨𝔩𝔪𝔫𝔬𝔭𝔮𝔯𝔰𝔱𝔲𝔳𝔴𝔵𝔶𝔷"
)

_PROTECTED: Set[str] = {
    "self", "cls", "args", "kwargs", "None", "True", "False",
    "__init__", "__new__", "__call__", "__str__", "__repr__",
    "__enter__", "__exit__", "__del__", "__class__", "__name__",
    "__file__", "__doc__", "__all__", "__slots__", "__dict__",
    "__main__", "__module__", "__annotations__",
    "print", "len", "range", "list", "dict", "set", "tuple",
    "str", "int", "float", "bool", "bytes", "type", "super",
    "open", "zip", "map", "filter", "enumerate", "sorted",
    "isinstance", "issubclass", "hasattr", "getattr", "setattr",
    "staticmethod", "classmethod", "property", "abstractmethod",
    "main", "run_pipeline_isolated", "verify_session_token",
    "PipelineManager", "RunPipelineRequest", "ProgressEvent",
    "emit", "start_worker", "add_task",
    "model_validate", "model_dump_json", "model_dump",
    "BaseModel", "Field", "ValidationError",
    "asyncio", "create_task", "gather", "run", "Queue",
    "get_running_loop", "run_in_executor", "CancelledError",
    "detect_hardware", "HardwareProfile",
    "WhisperTranscriber", "WhisperModelCache",
    "GeminiEngine", "YOLOImpl", "VideoRendererImpl",
    "FFmpegHandler", "SRTUtils", "ErrorMessageMapper",
}

class NameMangler(ast.NodeTransformer):
    def __init__(self, salt: str, aggressiveness: str = "high"):
        self._salt = salt
        self._level = {"low": 0, "medium": 1, "high": 2}[aggressiveness]
        self._mapping: Dict[str, str] = {}      # Global mapping: orig -> mangled
        self._used: Set[str] = set()            # Registry toàn file
        self._counter = 0                       # Bộ đếm đơn điệu
        self._fs_depth = 0                      # Theo dõi f-string

        # Stack để quản lý scope biến (dùng cho nonlocal/global)
        self._scope_stack: List[Set[str]] = []
        self._pending_nonlocals: Dict[str, str] = {} # Map tên gốc -> tên mangled chờ áp dụng

    def _should(self, name: str) -> bool:
        if name in _PROTECTED or (name.startswith("__") and name.endswith("__")):
            return False
        return name not in _PROTECTED if self._level == 2 else name.startswith("_")

    def _gen(self, orig: str) -> str:
        """Tạo tên UNIQUE tuyệt đối."""
        if orig in self._mapping:
            return self._mapping[orig]

        self._counter += 1
        h = hashlib.sha3_256(f"{orig}|{self._salt}|{self._counter}".encode()).digest()
        base = "".join(_UNICODE_POOL[b % len(_UNICODE_POOL)] for b in h[:12])
        cand = f"_{base}_{self._counter:04x}"

        attempts = 0
        while cand in self._used:
            self._counter += 1
            cand = f"_{base}_{self._counter:04x}"
            attempts += 1
            if attempts > 100:
                cand = f"_m{self._counter:06x}"

        self._used.add(cand)
        self._mapping[orig] = cand
        return cand

    def _get_current_mangled(self, orig: str) -> str:
        """Lấy tên đã mangle nếu có, hoặc trả về orig."""
        return self._mapping.get(orig, orig)

    def visit_JoinedStr(self, node):
        self._fs_depth += 1
        self.generic_visit(node)
        self._fs_depth -= 1
        return node

    def visit_Nonlocal(self, node):
        """Xử lý đặc biệt: nonlocal phải trỏ đúng biến đã được định nghĩa ở scope ngoài."""
        new_names = []
        for name in node.names:
            if self._should(name):
                mangled = self._mapping.get(name)
                if mangled:
                    new_names.append(mangled)
                else:
                    # 🔥 FIX: Nếu chưa kịp map, BẮT BUỘC phải giữ lại tên gốc để không bị SyntaxError
                    new_names.append(name)
            else:
                new_names.append(name)
        node.names = new_names
        return node

    def visit_Global(self, node):
        """Tương tự nonlocal nhưng cho global."""
        new_names = []
        for name in node.names:
            if self._should(name):
                mangled = self._mapping.get(name)
                if mangled:
                    new_names.append(mangled)
                else:
                    # 🔥 FIX: Bắt buộc giữ tên gốc nếu không map được
                    new_names.append(name)
            else:
                new_names.append(name)
        node.names = new_names
        return node

    def visit_Name(self, node):
        if self._fs_depth == 0 and self._should(node.id):
            mapped = self._mapping.get(node.id)
            if mapped:
                return ast.Name(id=mapped, ctx=node.ctx)
        return node

    def visit_FunctionDef(self, node):
        # 1. Push scope mới
        self._scope_stack.append(set())

        # 2. Xử lý tên hàm
        if self._should(node.name):
            node.name = self._gen(node.name)

        # 3. Thu thập tất cả args an toàn (Hỗ trợ đa phiên bản Python)
        all_args = []
        if hasattr(node.args, 'posonlyargs'):
            all_args.extend(node.args.posonlyargs)
        all_args.extend(node.args.args)
        all_args.extend(node.args.kwonlyargs)
        if node.args.vararg:
            all_args.append(node.args.vararg)
        if node.args.kwarg:
            all_args.append(node.args.kwarg)

        # 🔥 FIX QUAN TRỌNG: Chống lỗi Duplicate Arguments từ DeadInjector
        seen_args = set()
        for arg in all_args:
            if self._should(arg.arg):
                old_name = arg.arg
                
                # Nếu DeadInjector vô tình tạo 2 tham số trùng tên 
                # -> Ép đổi tên gốc (thêm hậu tố) để tạo Unique ID
                if old_name in seen_args:
                    old_name = f"{old_name}_dup_{self._counter}"
                
                seen_args.add(old_name)
                
                new_name = self._gen(old_name)
                arg.arg = new_name
                self._scope_stack[-1].add(new_name)
            else:
                seen_args.add(arg.arg)

        # 4. Xử lý body
        self.generic_visit(node)

        # 5. Pop scope
        self._scope_stack.pop()
        return node

    visit_AsyncFunctionDef = visit_FunctionDef

    def visit_ClassDef(self, node):
        if self._level == 2 and self._should(node.name):
            node.name = self._gen(node.name)
        self.generic_visit(node)
        return node

    def visit_Assign(self, node):
        self.generic_visit(node)
        return node