"""
Initialization file to make the functions and classed in aws modules import able from the package level.
- This allows users to import functions and classes directly from aws_modules instead of having to specify the
individual module they are located in.

EXAMPLE:
    Instead of importing get_secret from aws_sm_module, users can import it directly from aws_modules.
This promotes cleaner and more convenient imports for users of the package.

"""
# aws_modules/__init__.py
from .aws_sm_module import get_secret
from .aws_s3_module import AwsS3Module, S3OperationError
from .aws_connections_module import get_client, get_region, validate_region, _CLIENT_CACHE as _CLIENT_CACHE
from .aws_sts_module import (
    assume_role, get_account_details, get_endpoint_url, _STS_CACHE as _STS_CACHE, _ACCOUNT_ID_CACHE as _ACCOUNT_ID_CACHE
)


"""
Client caching:
    Clients are cached at process scope keyed by service, region, endpoint, credentials, and config. 
    Call `clear_caches()` (or `_CLIENT_CACHE.clear()`) in tests or after credential rotation
    
Thread safety:
    Caches are thread-safe and will refresh values in the background before they expire.
"""
def clear_caches() -> None:
    """Clear all internal cached values. Useful for testing or credentials rotation"""
    _STS_CACHE.clear()
    _ACCOUNT_ID_CACHE.clear()
    _CLIENT_CACHE.clear()
    get_region.cache_clear()


__all__ = [
    "get_secret",
    "AwsS3Module",
    "S3OperationError",
    "get_client",
    "get_region",
    "validate_region",
    "assume_role",
    "get_account_details",
    "get_endpoint_url",
    "clear_caches",
]
