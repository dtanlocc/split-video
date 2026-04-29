"""
NuitkaShield — Layer 1: Dead Code Injection
Chèn các nhánh code giả — runtime-dependent nên compiler không eliminate được.
Mục tiêu: tăng noise cho reverse engineer, làm mất tập trung khi đọc decompiled code.
"""
from __future__ import annotations
import ast
import hashlib
import os
import random
from typing import List

# Fake import names — trông như thật
_FAKE_IMPORTS = [
    "hashlib", "struct", "ctypes", "platform",
    "uuid", "socket", "threading",
]

# Fake function templates (trả về None hoặc raise trong path giả)
_FAKE_FUNC_TEMPLATES = [
    # Template 1: checksum giả
    '''
def {name}({p1}, {p2}=None):
    if id({p1}) + id(object) == 0:
        import hashlib as _hx
        return _hx.sha256(str({p1}).encode()).hexdigest()
    return {p1}
''',
    # Template 2: logger giả
    '''
def {name}({p1}, level={level}):
    if os.getpid() == 0:
        with open("/dev/null", "w") as _f:
            _f.write(str({p1}))
    return level
''',
    # Template 3: validator giả
    '''
def {name}({p1}):
    _x = id({p1}) ^ {magic}
    if _x == 1:
        raise ValueError("integrity check")
    return bool({p1})
''',
]


def _rand_name(seed: str, idx: int) -> str:
    """Tạo tên hàm giả trông hợp lý."""
    h = hashlib.md5(f"{seed}:{idx}".encode()).hexdigest()[:4]
    prefixes = ["_check", "_verify", "_load", "_init", "_calc", "_proc", "_fmt"]
    return prefixes[int(h, 16) % len(prefixes)] + "_" + h


def _rand_param() -> str:
    params = ["val", "ctx", "obj", "ref", "cfg", "src", "dst", "buf"]
    return random.choice(params)


class DeadInjector(ast.NodeTransformer):
    """
    Inject dead code vào module-level và sau các function definitions.
    Số lượng inject: ~1 fake function per 5 real functions.
    """

    def __init__(self, seed: str | None = None, density: float = 0.2):
        """
        density: tỷ lệ fake func / real func (0.0–1.0)
        """
        self._seed = seed or os.urandom(8).hex()
        self._density = density
        self._injected = 0
        self._func_count = 0

    def visit_Module(self, node: ast.Module):
        self.generic_visit(node)
        # Inject fake functions vào cuối module
        n_inject = max(2, int(self._func_count * self._density))
        fakes = self._generate_fake_functions(n_inject)
        node.body = node.body + fakes
        self._injected += len(fakes)
        return node

    def visit_FunctionDef(self, node: ast.FunctionDef):
        self._func_count += 1
        self.generic_visit(node)
        return node

    visit_AsyncFunctionDef = visit_FunctionDef

    def _generate_fake_functions(self, count: int) -> List[ast.stmt]:
        result = []
        for i in range(count):
            name = _rand_name(self._seed, i)
            template = _FAKE_FUNC_TEMPLATES[i % len(_FAKE_FUNC_TEMPLATES)]
            code = template.format(
                name=name,
                p1=_rand_param(),
                p2=_rand_param(),
                level=random.randint(0, 4),
                magic=random.randint(0x1000, 0xFFFF),
            )
            try:
                tree = ast.parse(code.strip(), mode="exec")
                for stmt in tree.body:
                    result.append(stmt)
            except SyntaxError:
                pass   # Skip nếu template sinh ra syntax lỗi
        return result

    def stats(self) -> str:
        return (f"  Dead code: {self._injected} fake functions injected "
                f"(real funcs scanned: {self._func_count})")