"""
Initialization file for helper module. This allows to mask the main file structure and allow importing the functions
and variables directly from the package level.

EXAMPLE:
    Instead of importing aws_retryable, require_non_empty, DEFAULT_REGION, DEFAULT_DURATION_SECONDS,
EARLY_REFRESH_SEC, MAX_CACHE_SIZE from helper_utils.utils and helper_utils.variables, users can import them directly
from helper_utils. This promotes cleaner and more convenient imports for users of the package.
"""
# helper_utils/__init__.py
from aws_services.helper_utils.utils import aws_retryable, require_non_empty
from aws_services.helper_utils.variables import (
    DEFAULT_REGION,
    DEFAULT_DURATION_SECONDS,
    MAX_RETRY_ATTEMPTS,
    MIN_WAIT_SECONDS,
    MAX_WAIT_SECONDS,
    MAX_CACHE_SIZE,
    MAX_REGION_CACHES,
    MAX_SECRETS_PER_REGION,
    EARLY_REFRESH_SEC,
    ACCOUNT_ID_REFRESH_SECS,
    ACCOUNT_ID_EXPIRY_SECS,
    DEFAULT_SESSION_NAME,
    AWS_RETRYABLE_ERROR_CODES,
    CLIENT_OPTIONS_DEFAULT
)


__all__ = [
    "aws_retryable",
    "require_non_empty",
    "DEFAULT_REGION",
    "DEFAULT_DURATION_SECONDS",
    "MAX_RETRY_ATTEMPTS",
    "MIN_WAIT_SECONDS",
    "MAX_WAIT_SECONDS",
    "MAX_CACHE_SIZE",
    "MAX_REGION_CACHES",
    "MAX_SECRETS_PER_REGION",
    "EARLY_REFRESH_SEC",
    "ACCOUNT_ID_REFRESH_SECS",
    "ACCOUNT_ID_EXPIRY_SECS",
    "DEFAULT_SESSION_NAME",
    "AWS_RETRYABLE_ERROR_CODES",
    "CLIENT_OPTIONS_DEFAULT"
]
