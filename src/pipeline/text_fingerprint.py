import hashlib
import re
import unicodedata
from typing import Any, Dict, Optional
from pathlib import Path

import yaml


PROJECT_ROOT = Path(__file__).resolve().parents[2]  
DEFAULT_CONFIG_PATH = PROJECT_ROOT / "configs" / "text_fingerprint.yaml"

_U00_PAT = re.compile(r"(\\u00[0-9a-fA-F]{2}|u00[0-9a-fA-F]{2})")


def load_fingerprint_config(path: str | None = None) -> Dict[str, Any]:
    cfg_path = Path(path) if path else DEFAULT_CONFIG_PATH
    data = yaml.safe_load(cfg_path.read_text(encoding="utf-8"))
    return data.get("text_fingerprint", {}) if isinstance(data, dict) else {}

def _replace_u00(m: re.Match) -> str:
    hex2 = m.group(0)[-2:]
    return chr(int(hex2, 16))


def normalize_text(s: Optional[str], cfg: Dict[str, Any]) -> Optional[str]:
    if s is None:
        return None

    s2 = s

    # Fix \u00xx or u00xx sequences if enabled
    if cfg.get("fix_u00_sequences", True) and _U00_PAT.search(s2):
        # If string contains real \u escapes, decode those safely
        if "\\u" in s2:
            try:
                s2 = s2.encode("utf-8").decode("unicode_escape")
            except Exception:
                pass
        # Handle u00xx without backslash
        s2 = _U00_PAT.sub(_replace_u00, s2)

    # Unicode normalization
    form = cfg.get("unicode_form", "NFKC")
    try:
        s2 = unicodedata.normalize(form, s2)
    except Exception:
        # If form is invalid, fall back
        s2 = unicodedata.normalize("NFKC", s2)

    if cfg.get("lowercase", True):
        s2 = s2.lower()

    if cfg.get("collapse_whitespace", True):
        s2 = re.sub(r"\s+", " ", s2).strip()

    if cfg.get("strip_trailing_ellipsis", True):
        s2 = re.sub(r"(\.{3}|…)\s*$", "", s2).strip()

    return s2


def signature_text(s: Optional[str], cfg: Dict[str, Any]) -> Optional[str]:
    s2 = normalize_text(s, cfg)
    if s2 is None:
        return None
    prefix_len = int(cfg.get("prefix_len", 300))
    return s2[:prefix_len]


def fingerprint_md5(s: Optional[str], cfg: Dict[str, Any]) -> Optional[str]:
    sig = signature_text(s, cfg)
    if sig is None:
        return None
    return hashlib.md5(sig.encode("utf-8")).hexdigest()
