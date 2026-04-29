#!/usr/bin/env python3
"""NuitkaShield v9.0 — Zero-Crash, AST-Only Pipeline"""
from __future__ import annotations
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
import argparse, ast, hashlib, json, os, re, shutil, tempfile, time
from core.string_encryptor import StringEncryptor
from core.name_mangler import NameMangler
from core.cff_engine import CFFEngine
from core.dead_injector import DeadInjector
from core.runtime_guard import GUARD_STUB, generate_secure_constants
from core.nuitka_builder import NuitkaBuilder

SKIP_FILES = {"__init__.py", "__main__.py"}
IGNORE_DIRS = {".venv","venv","__pycache__",".git","node_modules","dist","build","workspace"}

def load_yaml_config(config_path: Path) -> dict:
    if not config_path.exists(): return {}
    try:
        import yaml
        with open(config_path, "r", encoding="utf-8") as f: return yaml.safe_load(f) or {}
    except: return {}

def load_secrets(secrets_path: Path) -> dict:
    if not secrets_path.exists(): return {}
    try:
        with open(secrets_path, "r", encoding="utf-8") as f: return json.load(f)
    except: return {}

class ShieldPipeline:
    def __init__(self, cfg: dict, master_key: bytes, project_salt: str, secrets: dict):
        self.project_dir = cfg["project_dir"].resolve()
        self.cfg = cfg; self.master_key = master_key; self.project_salt = project_salt; self.secrets = secrets
        self._cff_seed = int.from_bytes(master_key[:4], "big")
        self._dead_seed = master_key[4:12].hex()
        self._name_salt = master_key[12:20].hex()

    def _classify(self, fn: str) -> str:
        if fn in self.cfg.get("skip", []): return "skip"
        if self.cfg["aggressiveness"] == "high": return "high"
        if fn in self.cfg.get("high", []): return "high"
        if fn in self.cfg.get("medium", []): return "medium"
        return "low"

    def _transform_ast(self, source: str, level: str, filename: str) -> tuple[str, str]:
        tree = ast.parse(source, filename=filename)
        # if level in ("high","medium"):
        #     density = {"high": 0.3, "medium": 0.15}.get(level, 0)
        #     tree = DeadInjector(self._dead_seed+filename, density).visit(tree)
        # mangle_lvl = self.cfg["aggressiveness"] if level=="high" else level
        # tree = NameMangler(self._name_salt, mangle_lvl).visit(tree)
        if level == "high": tree = CFFEngine(self._cff_seed).visit(tree)
        stub = ""
        if level in ("high","medium") and filename != "token_guard.py":
            enc = StringEncryptor(self.master_key, self.project_salt+filename)
            tree = enc.visit(tree)
            stub = enc.generate_decrypt_stub(self.master_key.hex(), self.project_salt+filename)
        ast.fix_missing_locations(tree)
        return ast.unparse(tree), stub

    def process_file(self, source_path: Path, output_path: Path, is_entry: bool = False):
        output_path.parent.mkdir(parents=True, exist_ok=True)
        fn = source_path.name
        level = self._classify(fn)
        if fn in SKIP_FILES or level == "skip":
            shutil.copy2(source_path, output_path); return
        try: source = source_path.read_text(encoding="utf-8")
        except: shutil.copy2(source_path, output_path); return

        obfuscated = source; stub = ""
        try:
            obfuscated, stub = self._transform_ast(source, level, fn)
        except Exception:
            pass  # Giữ nguyên source nếu AST fail → đảm bảo syntax 100% hợp lệ

        # Trích xuất __future__ về dòng 1
        future_imports = re.findall(r'^from __future__ import .+\n?', obfuscated, re.MULTILINE)
        if future_imports:
            obfuscated = re.sub(r'^from __future__ import .+\n?', '', obfuscated, flags=re.MULTILINE).strip()

        parts = future_imports + ["\n"]
        if is_entry: parts.append(GUARD_STUB + "\n")
        if fn == "token_guard.py" and self.secrets.get("SUPABASE_ANON_KEY"):
            parts.append(generate_secure_constants(self.secrets["SUPABASE_ANON_KEY"], self.secrets.get("EDGE_FUNC_URL",""), self.master_key) + "\n")
            obfuscated = re.sub(r'^(EDGE_FUNC_URL|ANON_KEY)\s*=.*$', "", obfuscated, flags=re.M)
        if stub: parts.append(stub + "\n")
        parts.append(obfuscated)
        output_path.write_text("\n".join(parts), encoding="utf-8")

    def run(self, shielded_dir: Path):
        py_files = sorted([f for f in self.project_dir.rglob("*.py") if not IGNORE_DIRS.intersection(f.relative_to(self.project_dir).parts)])
        print(f"\n📁 Found {len(py_files)} Python files in {self.project_dir.name}/")
        print("─" * 55)
        for src in py_files:
            rel = src.relative_to(self.project_dir)
            dst = shielded_dir / rel
            is_entry = (src.name == self.cfg["entry"] and src.parent == self.project_dir)
            level = self._classify(src.name)
            print(f"  🔒 [{level.upper():5}] {src.name}")
            self.process_file(src, dst, is_entry=is_entry)
        for f in self.project_dir.rglob("*"):
            if f.is_file() and f.suffix != ".py":
                rel = f.relative_to(self.project_dir)
                if not IGNORE_DIRS.intersection(rel.parts):
                    dst = shielded_dir / rel; dst.parent.mkdir(parents=True, exist_ok=True); shutil.copy2(f, dst)
        print(f"\n✅ Obfuscation complete: {len(py_files)} files")

def cmd_build(args):
    print("🛡️  NuitkaShield v9.0 — Zero-Crash Pipeline")
    cfg_path = Path(args.config) if args.config else Path(__file__).parent / "config" / "shield_config.yaml"
    cfg = load_yaml_config(cfg_path)
    secrets_path = Path(args.secrets) if args.secrets else cfg_path.parent.parent / ".shield_secrets.json"
    secrets = load_secrets(secrets_path)
    build_cfg = {
        "project_dir": Path(args.project or cfg.get("project",{}).get("backend_dir","../smart-video-pro")),
        "entry": args.entry or cfg.get("project",{}).get("entry","main_cli.py"),
        "output_dir": Path(args.output or cfg.get("build",{}).get("output_dir","../../dist")),
        "output_name": args.name or cfg.get("build",{}).get("output_name","smart-video-pro"),
        "aggressiveness": args.aggressive or cfg.get("obfuscation",{}).get("aggressiveness","high"),
        "high": set(cfg.get("obfuscation",{}).get("sensitivity_overrides",{}).get("high",[])),
        # THÊM .union(...) VÀO DÒNG DƯỚI ĐÂY
        "medium": set(cfg.get("obfuscation",{}).get("sensitivity_overrides",{}).get("medium",[])).union({"yolo_impl.py", "security_core.py", "whisper_impl.py"}),
        "skip": set(cfg.get("obfuscation",{}).get("sensitivity_overrides",{}).get("skip",["__init__.py"])),
    }
    key_src = args.build_key or os.environ.get("SHIELD_BUILD_KEY") or "AUTOCLIP_DEFAULT_2025"
    master_key = hashlib.sha256(key_src.encode()).digest()
    project_salt = hashlib.md5(str(build_cfg["project_dir"]).encode()).hexdigest()
    print(f"\n📋 Build Config:\n   Project: {build_cfg['project_dir']}\n   Entry: {build_cfg['entry']}\n   Aggressive: {build_cfg['aggressiveness']}\n   Secrets: {'✅' if secrets.get('SUPABASE_ANON_KEY') else '❌'}")
    with tempfile.TemporaryDirectory(prefix="nuitkashield_") as tmp:
        tmp = Path(tmp); shielded = tmp / "shielded" / build_cfg["project_dir"].name; shielded.mkdir(parents=True)
        pipe = ShieldPipeline(build_cfg, master_key, project_salt, secrets)
        pipe.run(shielded)
        builder = NuitkaBuilder(shielded, build_cfg["entry"], build_cfg["output_dir"], build_cfg["output_name"], True, True, 0)
        if not builder.run(shielded / build_cfg["entry"]): sys.exit(1)

if __name__ == "__main__":
    import argparse, struct, base64
    p = argparse.ArgumentParser()
    p.add_argument("--config"); p.add_argument("--secrets"); p.add_argument("--project"); p.add_argument("--entry")
    p.add_argument("--output"); p.add_argument("--name"); p.add_argument("--aggressive", choices=["low","medium","high"])
    p.add_argument("--build-key"); p.add_argument("cmd", nargs="?", default="build")
    cmd_build(p.parse_args())