from pathlib import Path

from hsconfig.io import write_json
from hsconfig.runtime_surface_ledger import (
    rederive_runtime_surface_ledger_from_package,
)


RUNTIME_SURFACE_LEDGER_PATH = "reports/runtime_surface_ledger.json"


def write_current_runtime_surface_ledger(package: Path) -> dict:
    ledger = rederive_runtime_surface_ledger_from_package(package)
    write_json(package / RUNTIME_SURFACE_LEDGER_PATH, ledger)
    return ledger
