"""Centralized logger. Usa `logging` padrão; em produção (Streamlit Cloud)
os logs vão para stderr e aparecem no painel "Manage app → Logs".

Opcional: se SENTRY_DSN estiver nas secrets, envia também para Sentry.
"""
import logging
import os
import sys

try:
    import streamlit as st
except Exception:  # pragma: no cover
    st = None

_INITIALIZED = False


def _init():
    global _INITIALIZED
    if _INITIALIZED:
        return
    root = logging.getLogger("quad")
    if not root.handlers:
        h = logging.StreamHandler(sys.stderr)
        h.setFormatter(logging.Formatter(
            "[%(levelname)s] %(asctime)s %(name)s — %(message)s",
            datefmt="%H:%M:%S",
        ))
        root.addHandler(h)
        root.setLevel(logging.INFO)

    # Sentry opcional (só se dsn + pacote instalados)
    dsn = None
    try:
        if st is not None:
            dsn = st.secrets.get("SENTRY_DSN")
    except Exception:
        pass
    dsn = dsn or os.environ.get("SENTRY_DSN")
    if dsn:
        try:
            import sentry_sdk
            sentry_sdk.init(dsn=dsn, traces_sample_rate=0.0,
                            send_default_pii=False)
            root.info("Sentry habilitado")
        except Exception as e:
            root.warning("Sentry DSN configurado mas pacote indisponivel: %s", e)

    _INITIALIZED = True


def get_logger(name: str) -> logging.Logger:
    _init()
    # sub-logger sob 'quad'
    short = name.replace("app.", "").replace("__main__", "main")
    return logging.getLogger(f"quad.{short}")
