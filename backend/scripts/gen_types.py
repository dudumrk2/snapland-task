#!/usr/bin/env python3
"""
gen_types.py

Delegates to root scripts/gen_types.py.
"""
import sys
from pathlib import Path

root_script_dir = Path(__file__).resolve().parent.parent.parent / "scripts"
sys.path.insert(0, str(root_script_dir))

if __name__ == "__main__":
    import gen_types
    gen_types.main()
