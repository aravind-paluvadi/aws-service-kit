"""Shared constants for utilities and other task modules"""
# Standard Imports
from typing import Final
from types import MappingProxyType


CLIENT_OPTIONS_DEFAULT: Final[MappingProxyType[str, object]] = MappingProxyType({
    "max_attempts": 10,
    "retry_mode": "standard",
    "connect_timeout": 10,
    "read_timeout": 120,
    "max_pool_connections": 50
})
DEFAULT_REGION: Final[str] = 'us-east-1'
DEFAULT_DURATION_SECONDS: Final[int] = 3600
MAX_RETRY_ATTEMPTS: Final[int] = 3
MIN_WAIT_SECONDS: Final[int] = 1
MAX_WAIT_SECONDS: Final[int] = 10
MAX_CACHE_SIZE: Final[int] = 1024
MAX_REGION_CACHES: Final[int] = 16
MAX_SECRETS_PER_REGION: Final[int] = 1024
EARLY_REFRESH_SEC: Final[int] = 300
ACCOUNT_ID_REFRESH_SECS: Final[int] = 3600 # Refresh account ID 1 hour before expiry
ACCOUNT_ID_EXPIRY_SECS: Final[int] = 86400 # Account ID is valid for 24 hours; adjust as needed
DEFAULT_SESSION_NAME: Final[str] = "AssumeRoleSession"
AWS_RETRYABLE_ERROR_CODES: Final[frozenset[str]] = frozenset({
    "ThrottlingException", "Throttling", "RequestLimitExceeded", "TooManyRequestsException",
    "InternalServerError", "InternalFailure", "ServiceUnavailableException",
    "ProvisionedThroughputExceededException", "TimeoutError",
    "RequestExpired", "ServiceUnavailable"
})
