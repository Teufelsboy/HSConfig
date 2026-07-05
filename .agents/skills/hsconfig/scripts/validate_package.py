#!/usr/bin/env python
from __future__ import annotations

import sys

from hsconfig.cli import main


raise SystemExit(main(["validate", *sys.argv[1:]]))
