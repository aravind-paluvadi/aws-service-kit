"""File with AWS Secrets Manager module"""
# Standard Library Imports
import logging
from json import loads, JSONDecodeError
from typing import Dict, Any, Union


# PIP Imports
from botocore.exceptions import ClientError
from aws_secretsmanager_caching import SecretCache, SecretCacheConfig


# Local Imports
from .aws_connections_module import get_client
from aws_services.cache_manager.thread_cache_manager import ThreadCacheManager
from aws_services.helper_utils.utils import aws_retryable, require_non_empty
from aws_services.helper_utils.variables import (
    DEFAULT_REGION, DEFAULT_DURATION_SECONDS, MAX_REGION_CACHES,
    MAX_SECRETS_PER_REGION, AWS_RETRYABLE_ERROR_CODES
)


__all__ = ["get_secret"]


logger = logging.getLogger(__name__)


# Create one cache per process; underlying client is created via our safe factory. Default refresh is 1 hour; adjust as needed.
_CACHE_BY_REGION: ThreadCacheManager = ThreadCacheManager(max_size=MAX_REGION_CACHES)


def _get_cache(region_name: str, ttl: int = DEFAULT_DURATION_SECONDS) -> SecretCache:
    """
    Get or create a SecretCache for the specified region.
    Parameter:
    ---------
        region_name:
            AWS region for which to get the cache.
        ttl:
            Time to live for the secrets in seconds. Default is 3600 (1 hour).
    Return:
    -------
        SecretCache instance for the specified region.
    """
    cache_key = (region_name, ttl)
    def sm_call() -> SecretCache:
        sm_client = get_client("secretsmanager", region=region_name)
        config = SecretCacheConfig(
            secret_refresh_interval=ttl,
            max_cache_size=MAX_SECRETS_PER_REGION
        )
        return SecretCache(config=config, client=sm_client)

    return _CACHE_BY_REGION.get_or_create(cache_key, sm_call)


@aws_retryable(logger)
def get_secret(
        secret_name: str,
        region_name: str = DEFAULT_REGION,
        ttl: int = DEFAULT_DURATION_SECONDS
) -> Union[Dict[str, Any], str]:
    """
    Function to get secrets with specified secret name
    Parameter:
    -----------
        secret_name:
            Name of the secret that needs to get secrets from.
        region_name:
            AWS Region service is present in. Default is 'us-east-1'
        ttl:
            Time to live for the secrets in seconds. Default is 3600 seconds (1 hour).

    Return:
    -------
        Dictionary of secrets from the specified secret name.

    Raises:
    ------
        ValueError: If there is an error fetching the secret from AWS Secrets Manager.
        ClientError: If there is an error fetching the secret from AWS Secrets Manager.
                    The error is retried if it is in the list of retryable error codes;
                    otherwise, it is raised immediately.
    """
    # Check if the required fields are missing
    require_non_empty(secret_name=secret_name, region_name=region_name)

    logger.info(
        "Fetching secret",
        extra={"secret_name": secret_name, "region": region_name}
    )
    try:
        secret_str = _get_cache(region_name, ttl).get_secret_string(secret_name)
    except ClientError as error_msg:
        code = error_msg.response['Error']['Code']
        if code not in AWS_RETRYABLE_ERROR_CODES:
            logger.error(
                "Non-retryable Secrets Manager error",
                extra={"secret_name": secret_name, "error_code": code}
            )
        raise

    try:
        return loads(secret_str)
    except (JSONDecodeError, TypeError):
        logger.debug(
            "Secret is not JSON, returning raw string",
            extra={"secret_name": secret_name}
        )
        return secret_str
