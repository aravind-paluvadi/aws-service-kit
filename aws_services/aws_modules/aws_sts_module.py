"""File with AWS STS module"""
# Standard Library Imports
import re
import logging
from time import time
from typing import Tuple, Any, Optional


# Local Imports
from .aws_connections_module import get_client, get_region
from aws_services.cache_manager.ttl_thread_cache_mager import TTLThreadCacheManager
from aws_services.helper_utils.utils import aws_retryable
from aws_services.helper_utils.variables import (
    DEFAULT_REGION, DEFAULT_DURATION_SECONDS, EARLY_REFRESH_SEC, ACCOUNT_ID_REFRESH_SECS,
    ACCOUNT_ID_EXPIRY_SECS, DEFAULT_SESSION_NAME
)


__all__ = ["assume_role", "get_account_details", "get_endpoint_url"]

logger = logging.getLogger(__name__)


# Thread-safe cache for account details
_ACCOUNT_ID_CACHE: TTLThreadCacheManager[str] = TTLThreadCacheManager(early_refresh_secs=ACCOUNT_ID_REFRESH_SECS)
_STS_CACHE: TTLThreadCacheManager[dict] = TTLThreadCacheManager(early_refresh_secs=EARLY_REFRESH_SEC)


_ARN_PATTERN = re.compile(r"^arn:aws[-\w]*:iam::\d{12}:role/.+$")
_REGION_PATTERN = re.compile(r"^[a-z]{2,}-[a-z]+-\d+$")


def get_endpoint_url(aws_region: Optional[str] = None) -> str:
    """
    Get the STS endpoint URL for the specified AWS region.
    If no region is provided, it uses the default region.

    Parameter:
    ----------
        aws_region:
            AWS region for which to get the endpoint URL. Optional.

    Return:
    -------
        Endpoint URL for the STS service in the specified region.
    """
    aws_region = aws_region or get_region()
    if not _REGION_PATTERN.match(aws_region):
        raise ValueError(f"Invalid AWS region provided: {aws_region!r}")

    return f"https://sts.{aws_region}.amazonaws.com"


@aws_retryable(logger)
def assume_role(
        role_arn: str,
        region_name: str = DEFAULT_REGION,
        endpoint_url: Optional[str] = None,
        session_name: str = DEFAULT_SESSION_NAME,
        duration_seconds: int = DEFAULT_DURATION_SECONDS
) -> dict:
    """
    Function to get credentials with specified endpoint
    Parameter:
    -----------
        role_arn:
            Role arn to assume the role.
        region_name:
            AWS region service is present in.
        endpoint_url:
            Endpoint url for the assume role.
        session_name:
            Session name url for the assume role
        duration_seconds:
            Duration in seconds for the assumed role session. Default is 3600 seconds (1 hour).

    Return:
    -------
        Dictionary of credentials from the specified endpoint url.
    """
    if not role_arn or not _ARN_PATTERN.match(role_arn):
        raise ValueError(f"Invalid role_arn provided: {role_arn!r}")

    resolved_endpoint = endpoint_url or get_endpoint_url(region_name)
    cache_key = (role_arn, session_name, region_name)

    def aws_assume_role_call() -> Tuple[dict, Any]:
        sts_client = get_client("sts", endpoint_url=resolved_endpoint, region=region_name)

        logger.info(
            "Assuming role",
            extra={"role_arn": role_arn, "session_name": session_name, "region": region_name}
        )
        assume_role_json = sts_client.assume_role(
            RoleArn=role_arn,
            RoleSessionName=session_name,
            DurationSeconds=duration_seconds
        )

        credentials = assume_role_json["Credentials"]
        expiration = credentials["Expiration"]
        expires_at = (
            expiration.timestamp()
            if hasattr(expiration, "timestamp")
            else float(expiration)
        )
        return credentials, expires_at

    return _STS_CACHE.get_or_create_expiry(cache_key, aws_assume_role_call)


@aws_retryable(logger)
def get_account_details(
        region_name: str = DEFAULT_REGION,
        endpoint_url: Optional[str] = None
) -> str:
    """
    Function to get account for the endpoint url
    Parameter:
    -----------
        region_name:
            AWS region service is present in.
        endpoint_url:
            Endpoint url for the assume role.

    Return:
    -------
        Account details of the current aws account.
    """
    resolved_endpoint = endpoint_url or get_endpoint_url(region_name)
    cache_key = f"{region_name}:{endpoint_url}"

    def aws_account_call() -> Tuple[str, float]:
        sts_client = get_client("sts", endpoint_url=resolved_endpoint, region=region_name)
        logger.info("Fetching caller identity", extra={"region": region_name})

        response = sts_client.get_caller_identity()
        account_id = response.get("Account")

        logger.info("Successfully retrieved account details", extra={"account_id": account_id})
        expires_at = time() + ACCOUNT_ID_EXPIRY_SECS
        return account_id, expires_at

    return _ACCOUNT_ID_CACHE.get_or_create_expiry(cache_key, aws_account_call)
