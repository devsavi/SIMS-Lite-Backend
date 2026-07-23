"""
Repository layer.

Repositories abstract all database access behind a clean interface.
Service classes consume repositories and never write SQLAlchemy queries
directly, making the data layer swappable and fully unit-testable.
"""
