#!/usr/bin/env python3
"""Copy the authored UI catalog into the standalone backend/worker build context."""
from pathlib import Path
root = Path(__file__).resolve().parent.parent
(root / 'backend/apps/core/locales/messages.json').write_bytes((root / 'frontend/src/messages.json').read_bytes())
