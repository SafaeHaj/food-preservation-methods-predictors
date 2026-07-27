"""Pluggable survival engines behind one abstract interface.

Relocated as-is from the survival pipeline. The engines still consume the old modelling
table (``t_failure``/``event``) and are not yet wired to the measurements schema, so nothing
is imported eagerly here -- import the individual engine modules directly once they are ported.
"""
