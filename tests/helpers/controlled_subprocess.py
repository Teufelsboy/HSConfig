from __future__ import annotations

import os
from pathlib import Path


def controlled_python_environment(root: Path) -> dict[str, str]:
    environment = os.environ.copy()
    for key in tuple(environment):
        upper = key.upper()
        if upper.startswith(
            (
                "HSCONFIG_COVERAGE_",
                "COVERAGE_",
                "PYTEST_",
                "HYPOTHESIS_",
                "PYTHON",
            )
        ):
            environment.pop(key, None)
    environment.update(
        {
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTHONIOENCODING": "utf-8",
            "PYTHONNOUSERSITE": "1",
            "PYTHONSAFEPATH": "1",
            "PYTHONUTF8": "1",
            "PYTHONPATH": os.pathsep.join((str(root / "src"), str(root))),
        }
    )
    return environment
