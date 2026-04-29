"""
NuitkaShield v7.0 — Pre-AST Hardening Layer
Strip comments, inject opaque predicates, obfuscate imports — BEFORE AST transform.
"""
from __future__ import annotations
import ast
import tokenize
import io
import re
from typing import List, Tuple

def strip_comments_and_docstrings(source: str) -> str:
    """
    Strip ALL comments and docstrings at token level.
    This runs BEFORE ast.parse() — ensures zero plaintext leakage.
    """
    tokens = tokenize.generate_tokens(io.StringIO(source).readline)
    result = []
    prev_toktype = tokenize.INDENT
    last_lineno = -1

    for tok in tokens:
        toktype, tstring, start, end, line = tok
        # Skip comments
        if toktype == tokenize.COMMENT:
            continue
        # Skip docstrings (STRING tokens that are standalone expressions)
        if toktype == tokenize.STRING and prev_toktype == tokenize.INDENT:
            # Check if it's a docstring (first statement in module/class/func)
            if start[0] == last_lineno + 1 or (prev_toktype in (tokenize.COLON, tokenize.NEWLINE)):
                continue
        # Keep everything else
        if start[0] > last_lineno:
            result.append("\n" * (start[0] - last_lineno))
        elif start[1] > last_lineno:
            result.append(" " * (start[1] - last_lineno))
        result.append(tstring)
        last_lineno = end[0]
        prev_toktype = toktype

    return "".join(result)

def inject_opaque_predicates(source: str, sensitivity: str) -> str:
    """
    Wrap sensitive code blocks in opaque predicates.
    Example: `if True: real_code` → `while _𝔬𝔭(seed, line): break; real_code`
    """
    if sensitivity != "high":
        return source

    # Pattern: match standalone statements (not inside f-strings/comments)
    # We inject after each logical block
    lines = source.split("\n")
    result = []
    seed = hash(source) & 0xFFFF

    for i, line in enumerate(lines):
        stripped = line.strip()
        # Skip empty lines, imports, decorators
        if not stripped or stripped.startswith(("import ", "from ", "@")):
            result.append(line)
            continue

        # Inject opaque predicate before "sensitive-looking" lines
        if any(kw in stripped.lower() for kw in ["def ", "class ", "if ", "for ", "while ", "try:", "with "]):
            # Generate unique opaque condition
            cond_var = f"_𝔬𝔭_{seed}_{i}"
            result.append(f"while {cond_var}({seed}, {i}): break  # opaque")

        result.append(line)

    # Add opaque predicate helper at top
    helper = f'''
def _𝔬𝔭_{seed}(s: int, l: int) -> bool:
    """Opaque predicate: always False but looks runtime-dependent."""
    import time, os, hashlib
    _t = time.perf_counter_ns()
    _h = hashlib.sha256(f"{{s}}:{{l}}:{{os.getpid()}}".encode()).digest()
    return (_t + int.from_bytes(_h[:4], "big")) & 1 == 2  # Always False
'''
    return helper + "\n" + "\n".join(result)

def obfuscate_imports(source: str, sensitivity: str) -> str:
    """
    Convert static imports to dynamic __import__() calls for high-sensitivity files.
    Example: `from src.module import X` → `X = __import__("src.module", fromlist=["X"]).X`
    """
    if sensitivity != "high":
        return source

    # Simple regex-based transform (safe for most cases)
    # Match: from X import Y, Z
    pattern = r'^from\s+([\w.]+)\s+import\s+(.+)$'

    def repl(m):
        module = m.group(1)
        imports = [i.strip() for i in m.group(2).split(",")]
        results = []
        for imp in imports:
            alias = ""
            if " as " in imp:
                name, alias = imp.split(" as ")
                name, alias = name.strip(), alias.strip()
            else:
                name = alias = imp.strip()
            # Dynamic import
            results.append(f"{alias} = __import__({repr(module)}, fromlist=[{repr(name)}]).{name}")
        return "\n".join(results)

    return re.sub(pattern, repl, source, flags=re.MULTILINE)

def preprocess(source: str, sensitivity: str) -> str:
    """
    Full pre-AST preprocessing pipeline.
    Order matters: strip → obfuscate imports → inject opaque predicates.
    """
    source = strip_comments_and_docstrings(source)
    source = obfuscate_imports(source, sensitivity)
    source = inject_opaque_predicates(source, sensitivity)
    return source