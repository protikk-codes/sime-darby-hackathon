"""Exceptions raised by the service layer. The UI shows their messages to the user."""


class TownshipError(Exception):
    """Base class for all expected application errors."""


class ValidationError(TownshipError):
    """User input failed validation."""


class NotFoundError(TownshipError):
    """A requested record does not exist."""


class DatabaseFailure(TownshipError):
    """A database operation failed unexpectedly."""
