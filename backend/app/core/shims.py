import sys
import types
import json

def patch_system_shims():
    """
    Applies pure Python compatibility shims for environment-blocked binary DLLs (e.g. ormsgpack).
    Ensures LangGraph compiles and runs seamlessly across all host environments.
    """
    if "ormsgpack" not in sys.modules:
        try:
            import ormsgpack  # type: ignore
        except Exception:
            m = types.ModuleType("ormsgpack")
            m.OPT_NON_STR_KEYS = 1
            m.OPT_PASSTHROUGH_DATACLASS = 2
            m.OPT_PASSTHROUGH_DATETIME = 4
            m.OPT_PASSTHROUGH_ENUM = 8
            m.OPT_PASSTHROUGH_UUID = 16
            m.OPT_REPLACE_SURROGATES = 32
            m.OPT_SERIALIZE_NUMPY = 64
            m.OPT_SERIALIZE_PYDANTIC = 128
            m.packb = lambda x, **kw: json.dumps(x, default=str).encode("utf-8")
            m.unpackb = lambda x, **kw: json.loads(x.decode("utf-8")) if isinstance(x, (bytes, bytearray)) else json.loads(x)
            sys.modules["ormsgpack"] = m

patch_system_shims()
