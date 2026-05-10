"""Shared constants for utilities and other task modules"""

DEFAULT_REGION = 'us-east-1'
DEFAULT_DURATION_SECONDS = 3600
MAX_RETRY_ATTEMPTS = 3
MIN_WAIT_SECONDS = 1
MAX_WAIT_SECONDS = 10
MAX_CACHE_SIZE = 1024
MAX_REGION_CACHES = 16
MAX_SECRETS_PER_REGION = 1024
EARLY_REFRESH_SEC = 300
ACCOUNT_ID_REFRESH_SECS = 3600 # Refresh account ID 1 hour before expiry
ACCOUNT_ID_EXPIRY_SECS = 86400 # Account ID is valid for 24 hours; adjust as needed
DEFAULT_SESSION_NAME = "AssumeRoleSession"
AWS_RETRYABLE_ERROR_CODES = frozenset({
    "ThrottlingException", "Throttling", "RequestLimitExceeded", "TooManyRequestsException",
    "InternalServerError", "InternalFailure", "ServiceUnavailableException",
    "ProvisionedThroughputExceededException", "TimeoutError",
    "RequestExpired", "ServiceUnavailable"
})
