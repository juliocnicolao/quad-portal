"""Pytest config — adiciona app/ ao sys.path e mocka st.cache_data."""
import sys, os, types

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
APP  = os.path.join(ROOT, "app")
if APP not in sys.path:
    sys.path.insert(0, APP)

# Streamlit pode não estar disponível em CI; faz shim mínimo para imports.
try:
    import streamlit  # noqa: F401
except ImportError:  # pragma: no cover
    stub = types.ModuleType("streamlit")
    def _cache_passthrough(*a, **kw):
        def _wrap(fn): return fn
        return _wrap if not a else (a[0] if callable(a[0]) else _wrap)
    stub.cache_data = _cache_passthrough
    stub.secrets    = {}
    sys.modules["streamlit"] = stub
