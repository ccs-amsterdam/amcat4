"""Exceptions raised by the storage layer, independent of the database used"""


class NotFoundError(Exception):
    """The requested object (project, document, role, ...) does not exist"""


class ConflictError(Exception):
    """The object to be created already exists"""
