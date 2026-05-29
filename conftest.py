"""Conftest a livello root: aggiunge la root al sys.path per `import src.*`."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))


def pytest_configure(config):
    config.addinivalue_line(
        "markers", "integration: test che richiede rete o servizi esterni"
    )
