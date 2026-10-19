"""Exceptions métier du domaine applicatif, découplées du transport HTTP."""


class DomainError(Exception):
    """Exception de base du domaine métier."""

    status_code: int = 400

    def __init__(self, detail: str, status_code: int | None = None):
        super().__init__(detail)
        self.detail = detail
        if status_code is not None:
            self.status_code = status_code


class ResourceNotFoundError(DomainError):
    status_code = 404


class ForbiddenActionError(DomainError):
    status_code = 403


class ConflictError(DomainError):
    status_code = 409


class InsufficientBalanceError(DomainError):
    status_code = 400


class RateLimitExceededError(DomainError):
    status_code = 429
