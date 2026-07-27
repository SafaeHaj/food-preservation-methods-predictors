"""Persistence layer for the processing domain.

Repositories hold queries only: no HTTP concepts, no business rules, no transaction
control. Services compose them and own the transaction via `shared.uow.unit_of_work`.
"""
