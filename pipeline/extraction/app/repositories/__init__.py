"""Persistence layer for the extraction domain.

Repositories hold queries and nothing else: no HTTP concepts, no business rules, no
transaction control. Services compose them and own the transaction via
`shared.uow.unit_of_work`.
"""
