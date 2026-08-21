from __future__ import annotations
import fnmatch, urllib.parse
from ..database import db

LEVELS = {"LOW": 1, "MEDIUM": 2, "HIGH": 3, "CRITICAL": 4}
DEFAULT_APPROVAL_LEVELS = {"read": "LOW", "analyze": "LOW", "tests": "MEDIUM", "patch": "MEDIUM",
                           "code_edit": "HIGH", "dependency": "HIGH", "training": "HIGH",
                           "internet": "CRITICAL", "security_policy": "CRITICAL", "model_promote": "CRITICAL",
                           "owner_permissions": "CRITICAL"}
IMMUTABLE_GENERIC_CONTROLS = {"kill_switch", "last_emergency_stop_at", "last_emergency_stop_reason", "last_emergency_bundle_id"}
HIGH_RISK_ENABLE_WHILE_STOPPED = {"internet_enabled", "terminal_enabled", "install_deps_enabled", "server_enabled", "external_models_enabled", "training_enabled", "autonomous_cycles"}
NUMERIC_LIMITS = {
    "cpu_limit_percent": (1, 100),
    "ram_limit_mb": (128, 262144),
    "storage_limit_mb": (512, 1048576),
    "budget_credits": (0, 1_000_000_000),
    "session_ttl_s": (60, 2_592_000),
    "session_idle_timeout_s": (60, 2_592_000),
    "max_sessions_per_device": (1, 100),
}

def kill_switch_active() -> bool: return bool(db.get_controls().get("kill_switch", False))
def allowed(capability: str) -> bool:
    c = db.get_controls()
    if kill_switch_active(): return False
    aliases = {"python":"python_enabled", "terminal":"terminal_enabled", "web":"web_enabled",
               "code_edit":"code_editing_enabled", "tools":"tools_enabled", "training":"training_enabled",
               "network":"internet_enabled", "external_models":"external_models_enabled", "files":"tools_enabled"}
    return bool(c.get(aliases.get(capability, capability), False))

def approval_level(action: str) -> str: return db.get_controls().get("approval_" + action, DEFAULT_APPROVAL_LEVELS.get(action, "HIGH"))

def validate_control_changes(values: dict) -> dict:
    controls = db.get_controls()
    sanitized = {}
    for key, value in values.items():
        if key in IMMUTABLE_GENERIC_CONTROLS:
            raise ValueError(f"control '{key}' must be changed through its dedicated emergency endpoint")
        if key in NUMERIC_LIMITS:
            if not isinstance(value, (int, float)):
                raise ValueError(f"control '{key}' must be numeric")
            lo, hi = NUMERIC_LIMITS[key]
            if not (lo <= float(value) <= hi):
                raise ValueError(f"control '{key}' out of allowed range {lo}..{hi}")
        if key.startswith("approval_"):
            if value not in LEVELS:
                raise ValueError(f"approval level for '{key}' must be one of {sorted(LEVELS)}")
        if key in ("domain_allowlist", "domain_blocklist"):
            if not isinstance(value, list) or not all(isinstance(x, str) and x.strip() for x in value):
                raise ValueError(f"control '{key}' must be a non-empty-string list")
        if controls.get("kill_switch", False) and key in HIGH_RISK_ENABLE_WHILE_STOPPED and bool(value):
            raise ValueError(f"cannot enable '{key}' while kill switch is active")
        sanitized[key] = value
    return sanitized

def domain_allowed(url: str) -> bool:
    p = urllib.parse.urlparse(url)
    host = (p.hostname or "").lower()
    c = db.get_controls()
    if not c.get("internet_enabled", False) or not c.get("web_enabled", False): return False
    deny = c.get("domain_blocklist", []) or []
    allow = c.get("domain_allowlist", []) or []
    if any(fnmatch.fnmatch(host, x.lower()) for x in deny): return False
    return not allow or any(fnmatch.fnmatch(host, x.lower()) for x in allow)
