"""Test settings: no database, no model, no network.

`SECRET_KEY` has no default by design (a shipped default is a shipped private key), so it
is supplied here rather than every test importing settings having to know that. The LLM
cache is disabled so a scripted reply is never served from a previous run's answer.
"""

import os

os.environ.setdefault("SECRET_KEY", "test-secret-not-used-for-signing")
os.environ.setdefault("EXTRACTION_LLM_PROVIDER", "fake")
os.environ.setdefault("EXTRACTION_LLM_CACHE_ENABLED", "0")
