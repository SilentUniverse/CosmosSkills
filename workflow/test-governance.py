#!/usr/bin/env python3
"""Inspect declared test scope and retained costs; never execute a test or install a tool."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_governance import main

if __name__ == '__main__':
    raise SystemExit(main())
