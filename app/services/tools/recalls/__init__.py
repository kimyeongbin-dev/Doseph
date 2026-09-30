"""Recall checker tool package (Phase 7).

Exposes the two LLM-callable functions used by the Router LLM to
answer user recall questions:

- ``check_user_medications_recall``: Q1 — does the user's medication
  list overlap with any recall.
- ``check_manufacturer_recalls``: Q2 — recall history for a given
  manufacturer (or, by default, every manufacturer represented in the
  user's medication list).
"""

from app.services.tools.recalls.checker import (
  check_manufacturer_recalls,
  check_user_medications_recall,
)

__all__ = [
  "check_manufacturer_recalls",
  "check_user_medications_recall",
]
