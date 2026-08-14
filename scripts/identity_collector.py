#!/usr/bin/env python3
"""P0-R2 forward identity collector CLI entry point (prereg API Contracts).
Thin dispatcher only -- all real logic lives in the sibling `identity_collector/`
package (imported below), never here, so this file can be run directly
(`python scripts/identity_collector.py ...`) without the package/module name
collision that would occur if logic lived in both places under one name.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from identity_collector.cli import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
