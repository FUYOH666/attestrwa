"""Errors the attester maps to HTTP statuses."""


class AttesterError(Exception):
    """Base class; ``status`` is the HTTP status the API answers with."""

    status = 500


class ConfigError(AttesterError):
    """The service is not configured well enough to act."""

    status = 503


class DealNotFound(AttesterError):
    status = 404


class DealNotActionable(AttesterError):
    """The deal exists but no decision can be made about it (settled, past deadline)."""

    status = 409


class InputError(AttesterError):
    """The caller supplied context the policy does not accept from a caller."""

    status = 422


class UpstreamError(AttesterError):
    """The chain or a data provider failed. No decision is made: fail closed."""

    status = 502
