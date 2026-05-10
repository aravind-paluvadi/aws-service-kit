"""File to handle the AWS Session calls"""
# Standard Library Imports
import logging
from functools import lru_cache
from typing import Optional, Callable, Any


# Pip Imports
from boto3 import Session
from botocore.config import Config
from botocore.exceptions import (
    NoCredentialsError, BotoCoreError,
    EndpointConnectionError, ConnectionClosedError
)


# Local Imports
from aws_services.cache_manager.thread_cache_manager import ThreadCacheManager
from aws_services.helper_utils.variables import DEFAULT_REGION, MAX_CACHE_SIZE
from aws_services.helper_utils.utils import update_dict_keys, aws_retryable


__all__ = ["get_client", "get_region"]

logger = logging.getLogger(__name__)

_CLIENT_CACHE: ThreadCacheManager = ThreadCacheManager(max_size=MAX_CACHE_SIZE)

_OPTIONS_DEFAULT = {
    "region": DEFAULT_REGION,
    "endpoint_url": None,
    "max_attempts": 10,
    "config_mode": "standard",
    "connect_timeout": 10,
    "read_timeout": 120,
    "max_pool_connections": 50
}


@lru_cache(maxsize=1)
def get_region() -> str:
    """
    Detects and caches the AWS region from the current session.
    If no region is configured, it falls back to a default region.

    Note: Rest is cached for the lifetime of the process. Call
    get_region.cache_clear() in tests if overriding the region via env vars.

    Return:
    ------
        str: AWS region name
    """
    region = Session().region_name
    if not region:
        logger.warning("AWS region not configured, falling back to '%s'", DEFAULT_REGION)
        return DEFAULT_REGION
    return region


def get_client(
        service_name: str,
        config: Optional[Config] = None,
        aws_access_key_id: Optional[str] = None,
        aws_secret_access_key: Optional[str] = None,
        aws_session_token: Optional[str] = None,
        use_cache: bool = True,
        **kwargs: Any
) -> Any:
    """
    Return a stable AWS client with retries and standardized config.
    Pass use_cache=False when using assume-role credentials (tokens expire).

    Parameters:
    ----------
        service_name:
            AWS service name (e.g. 'sts', 'secretsmanager')
        region:
            AWS region name (e.g. 'us-east-1'). If not provided, will use default from session or fallback.
        endpoint_url:
            Custom endpoint URL for the service (useful for testing or non-AWS environments)
        config:
            Optional botocore Config object for advanced configuration. If not provided,
            a default config with retries will be used.
        max_attempts:
            Maximum Botocore retry attempts for AWS API calls (default: 10)
        config_mode:
            Botocore retry mode (e.g. 'standard' or 'adaptive' for client-side rate limiting)
        connect_timeout:
            Connection timeout in seconds for AWS API calls (default: 10)
        read_timeout:
            Read timeout in seconds for AWS API calls (default: 120)
        max_pool_connections:
            Maximum number of connections in the pool (default: 50, increase for concurrency)
        aws_access_key_id:
            Optional explicit AWS Access key
        aws_secret_access_key:
            Optional explicit AWS Secret key
        aws_session_token:
            Optional explicit AWS Session token (required if using temporary credentials from assume-role)
        use_cache:
            Whether to cache the client instance for future calls. Set False for assume-role credentials, Should be
            False if using temporary credentials that expire. (default: True).

    Return:
    -------
        boto3 client for the specified service
    """
    options = _OPTIONS_DEFAULT.copy()
    args = update_dict_keys(options, kwargs)

    # Never cache client with explicit session credentials (tokens expire)
    should_cache = use_cache and not aws_session_token
    cache_key = (
        service_name,
        args.get("region"),
        args.get("endpoint_url"),
        args.get("max_attempts"),
        args.get("config_mode"),
        args.get("connect_timeout"),
        args.get("read_timeout"),
        args.get("max_pool_connections"),
        aws_access_key_id
    ) if should_cache else None

    cfg = config or _build_config(
        max_attempts=args.get("max_attempts"),
        retry_mode=args.get("config_mode"),
        connect_timeout=args.get("connect_timeout"),
        read_timeout=args.get("read_timeout"),
        max_pool_connections=args.get("max_pool_connections")
    )

    def _create() -> Any:
        return Session().client(
            service_name,
            region_name=args.get("region"),
            endpoint_url=args.get("endpoint_url"),
            config=cfg,
            aws_access_key_id=aws_access_key_id,
            aws_secret_access_key=aws_secret_access_key,
            aws_session_token=aws_session_token
        )

    if cache_key:
        return _CLIENT_CACHE.get_or_create(
            cache_key,
            lambda: _create_client_with_retry(_create, service_name)
        )

    return _create_client_with_retry(_create, service_name)


def _build_config(
        max_attempts: int = 10,
        retry_mode: str = "standard",   # or 'adaptive' for client-side rate limiting
        connect_timeout: int = 10,
        read_timeout: int = 120,
        max_pool_connections: int = 50    # increase for concurrency
) -> Config:
    """
    Function to build the config.

    Parameters:
    ----------
        max_attempts:
            Maximum Botocore retry attempts for AWS API calls (default: 10)
        retry_mode:
            Botocore retry mode (e.g. 'standard' or 'adaptive' for client-side rate limiting)
        connect_timeout:
            Connection timeout in seconds for AWS API calls (default: 10)
        read_timeout:
            Read timeout in seconds for AWS API calls (default: 120)
        max_pool_connections:
            Maximum number of connections in the pool (default: 50, increase for concurrency)

    Return:
    -------
        Config object with specified retry and timeout settings
    """
    return Config(
        retries={"max_attempts": max_attempts, "mode": retry_mode},
        connect_timeout=connect_timeout,
        read_timeout=read_timeout,
        max_pool_connections=max_pool_connections
    )


@aws_retryable(logger)
def _create_client_with_retry(create_fn: Callable, service_name: str) -> Any:
    """
    Parameters:
    ----------
        create_fn:
                Function that creates and returns the AWS client instance when called. This is wrapped in a
                retry decorator to handle transient errors during client creation.
        service_name:
                Name of the AWS service for logging purposes (e.g. 'sts', 'secretsmanager')

    Return:
    ------
        boto3 client for the specified service

    Raises:
    ------
        NoCredentialsError: If AWS credentials are not found in the environment or configuration.
        EndpointConnectionError: If there is a connection issue reaching the AWS service endpoint.
        ConnectionClosedError: If the connection to the AWS service is unexpectedly closed during client creation.
        BotoCoreError: For any other non-retryable errors that occur during client creation, the error message is logged and re-raised.
    """
    try:
        return create_fn()
    except NoCredentialsError:
        logger.warning("No AWS credentials found for creating %s client. Ensure credentials are configured.", service_name)
        raise
    except (EndpointConnectionError, ConnectionClosedError):
        raise
    except BotoCoreError as error_msg:
        logger.error("Non-retryable BotoCoreError for service %s: %s", service_name, str(error_msg))
        raise
