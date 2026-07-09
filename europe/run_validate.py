"""Run the edge-validation (PASS/WARN/FAIL) on EU data.

    python run_validate.py      (after run_analyze.py)
"""
import sys
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
sys.path.insert(1, str(HERE.parent))

import validate_edge  # noqa: E402

if __name__ == "__main__":
    validate_edge.main()
