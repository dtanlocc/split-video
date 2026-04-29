"""NuitkaShield v2.0 — Config & Secrets Loader"""
from __future__ import annotations
import yaml
import json
from pathlib import Path
from typing import Dict, Any

def load_config(config_path: Path) -> Dict[str, Any]:
    if not config_path.exists():
        raise FileNotFoundError(f"Config not found: {config_path}")
    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)

def load_secrets(secrets_path: Path) -> Dict[str, str]:
    if not secrets_path.exists():
        return {}
    try:
        with open(secrets_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        raise RuntimeError(f"Invalid secrets JSON: {e}")

def resolve_build_config(cli_args: Any, cfg: Dict[str, Any]) -> Dict[str, Any]:
    """Merge CLI args with YAML config. CLI overrides YAML."""
    project = cfg.get("project", {})
    build = cfg.get("build", {})
    obf = cfg.get("obfuscation", {})

    return {
        "project_dir": Path(cli_args.project or project.get("backend_dir", "../smart-video-pro")),
        "entry": cli_args.entry or project.get("entry", "main_cli.py"),
        "output_dir": Path(cli_args.output or build.get("output_dir", "../../dist")),
        "output_name": cli_args.name or build.get("output_name", "smart-video-pro"),
        "console": cli_args.console if cli_args.console is not None else build.get("console", True),
        "lto": not cli_args.no_lto if cli_args.no_lto is not None else build.get("lto", True),
        "jobs": cli_args.jobs or build.get("jobs", 0),
        "aggressiveness": cli_args.aggressive or obf.get("aggressiveness", "medium"),
        "high": set(obf.get("sensitivity_overrides", {}).get("high", [])),
        "medium": set(obf.get("sensitivity_overrides", {}).get("medium", [])),
        "skip": set(obf.get("sensitivity_overrides", {}).get("skip", ["__init__.py"])),
    }