"""Conftest a livello root: aggiunge la root al sys.path per `import src.*`."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))


import os
import pytest


def pytest_configure(config):
    config.addinivalue_line(
        "markers", "integration: test che richiede rete o servizi esterni"
    )
    config.addinivalue_line(
        "markers",
        "destructive: test che cancella/modifica DATI REALI in DB. "
        "Skip by default. Run con: RUN_DESTRUCTIVE_TESTS=1 pytest -m destructive",
    )


def pytest_collection_modifyitems(config, items):
    """Skip dei test destructive a meno che RUN_DESTRUCTIVE_TESTS=1.

    Evita catastrofi tipo `pytest tests/` che trunca il DB di produzione.
    """
    if os.environ.get("RUN_DESTRUCTIVE_TESTS") == "1":
        return
    skip_marker = pytest.mark.skip(
        reason="Test destructive: cancella/modifica dati reali. "
        "Per eseguirlo: RUN_DESTRUCTIVE_TESTS=1 pytest -m destructive"
    )
    for item in items:
        if "destructive" in item.keywords:
            item.add_marker(skip_marker)
