"""NuitkaShield v9.0 — String Encryption (Dict & F-String Safe)"""
from __future__ import annotations
import ast, os, base64, hashlib, struct
from typing import Dict

_SKIP_PREFIXES = ("__", "src.", "utf-8", "utf8", "win32", "linux", "darwin")
_SKIP_EXACT = {" ", "\n", "\t", "r", "w", "rb", "wb", "utf-8", "utf8", "json", "str", "int", "float", "bool", "None", "True", "False", "POST", "GET", "HEAD", "Content-Type", "application/json"}

def _xor_cipher(data: bytes, key: bytes) -> bytes:
    return bytes(b ^ key[i % len(key)] for i, b in enumerate(data))

class StringEncryptor(ast.NodeTransformer):
    def __init__(self, master_key: bytes, project_salt: str):
        self._key = hashlib.pbkdf2_hmac("sha256", master_key + project_salt.encode(), b"nuitkashield_v9", 100_000)
        self._counter = 0
        self._catalog: Dict[int, str] = {}
        self._fs_depth = 0
        self._in_dict_key = False

    def _should_skip(self, s: str) -> bool:
        if len(s) < 4 or s in _SKIP_EXACT: return True
        if any(s.startswith(p) for p in _SKIP_PREFIXES): return True
        return False

    def _encrypt_one(self, text: str) -> int:
        raw = text.encode("utf-8")
        payload = struct.pack("!I", len(raw)) + _xor_cipher(raw, self._key[:16])
        idx = self._counter
        self._catalog[idx] = base64.b85encode(payload).decode("ascii")
        self._counter += 1
        return idx

    def visit_JoinedStr(self, node):
        self._fs_depth += 1
        self.generic_visit(node)
        self._fs_depth -= 1
        return node

    def visit_Dict(self, node):
        self._in_dict_key = True
        for k in node.keys:
            if isinstance(k, ast.Constant): self.visit(k)
        self._in_dict_key = False
        for v in node.values:
            if v: self.visit(v)
        return node

    def visit_Constant(self, node):
        if self._fs_depth > 0 or self._in_dict_key:
            return node
        if not isinstance(node.value, str) or self._should_skip(node.value):
            return node
        idx = self._encrypt_one(node.value)
        return ast.Call(func=ast.Name(id="_ŝ", ctx=ast.Load()), args=[ast.Constant(value=idx)], keywords=[])

    def generate_decrypt_stub(self, key_hex: str, salt: str) -> str:
        return f'''
import struct as _Ś, base64 as _Ŝ, hashlib as _Š
def _ŝ(_i: int) -> str:
 _K=_Š.pbkdf2_hmac("sha256",bytes.fromhex("{key_hex}")+{repr(salt)}.encode(),b"nuitkashield_v9",100_000)
 _C={repr(self._catalog)}
 _p=_Ŝ.b85decode(_C[_i].encode("ascii"))
 _l=_Ś.unpack("!I",_p[:4])[0];_ct=_p[4:]
 return bytes(_b^_K[_j%16] for _j,_b in enumerate(_ct))[:_l].decode("utf-8")
'''