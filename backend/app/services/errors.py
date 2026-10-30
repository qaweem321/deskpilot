class NotFound(Exception):
    """The record does not exist (or the user may not see it)."""


class InvalidAction(Exception):
    """The request breaks a business rule, e.g. refunding more than was paid."""
