"""Test settings: no database, no model, no network.

`SECRET_KEY` has no default by design (a shipped default is a shipped private key), so it
is supplied here rather than every test importing settings having to know that. The LLM
cache is disabled so a scripted reply is never served from a previous run's answer.
"""

import os
import sys
from pathlib import Path

os.environ.setdefault("SECRET_KEY", "test-secret-not-used-for-signing")
os.environ.setdefault("PROCESSING_LLM_PROVIDER", "fake")
os.environ.setdefault("PROCESSING_LLM_CACHE_ENABLED", "0")
os.environ.setdefault("PROCESSING_USDA_API_KEY", "")

# The service image installs `shared` and runs from `/app`; a local pytest run has neither.
_ROOT = Path(__file__).resolve().parents[1]
for path in (_ROOT, _ROOT.parent / "shared"):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))
