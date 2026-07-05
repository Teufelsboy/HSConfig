#!/usr/bin/env python
from __future__ import annotations

import sys

from hsconfig.cli import main


raise SystemExit(main(["build", *sys.argv[1:]]))
