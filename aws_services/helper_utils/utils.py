"""Helper module for project, contains utility functions"""
from __future__ import annotations

# Standard Library Imports
import logging
import hashlib
from typing import Any
from enum import StrEnum


# PIP Imports
from botocore.exceptions import ClientError, EndpointConnectionError, ConnectionClosedError
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential_jitter,
    retry_if_exception,
    before_sleep_log
)

# Local Imports
from .variables import (
    MAX_RETRY_ATTEMPTS,
    MIN_WAIT_SECONDS,
    MAX_WAIT_SECONDS,
    AWS_RETRYABLE_ERROR_CODES
)


logger = logging.getLogger(__name__)


def merge_known_kwargs(fields, overrides):
    """
    Update the keys of the fields dictionary based on the provided mapping. This allows for flexible renaming
    of fields while ensuring that only expected keys are updated.
    Parameters:
    ----------
        fields:
            The original dictionary containing the fields to be updated.
        overrides:
            A dictionary containing the fields are the original field name and values are the new fields names.

    Returns:
    -------
        A new dictionary with the updated fields based on the provided mapping.
    """
    # Set the config options based on given values
    if not overrides:
        return dict(fields)
    unknown = set(overrides) - set(fields)
    if unknown:
        raise TypeError(f"Unknown keyword arguments: {sorted(unknown)}")
    return {**fields, **overrides}


def require_non_empty(**fields: Any) -> None:
    """
    Check if the input fields are not empty.
    Parameters:
    ----------
        fields:
            A dictionary containing the fields to be checked for non-emptiness. The keys are the field names
            and the values are the field values.
    Raises:
    -------
        ValueError: If any of the fields are empty, a ValueError is raised with a message indicating
                    which fields are missing.
    """
    missing_fields = [key for key, value in fields.items() if not value]
    if missing_fields:
        raise ValueError(f"Missing fields: {", ".join(missing_fields)}")


def aws_retryable(logger_instance: logging.Logger):
    """
    Standard AWS retryable function that can be used to retry AWS API calls in case of transient errors.
    It uses the tenacity library to implement the retry logic, which includes exponential backoff with jitter and
    logging of retry attempts.
    Parameters:
    ----------
        logger_instance:
                A logging.Logger instance that will be used to log retry attempts. The logger will log a warning message
                each time a retry is attempted due to a transient error.
    Returns:
    -------
        Tenacity retry decorator with exponential jitter backoff and logging of retry attempts.
    """
    return retry(
        stop=stop_after_attempt(MAX_RETRY_ATTEMPTS),
        wait=wait_exponential_jitter(initial=MIN_WAIT_SECONDS, max=MAX_WAIT_SECONDS),
        before_sleep=before_sleep_log(logger_instance, logging.WARNING), # type: ignore[arg-type]
        retry=retry_if_exception(_is_retryable_error),
        reraise=True
    )


def _is_retryable_error(exception: BaseException) -> bool:
    """Return True if exception is transient and should be retried."""
    match exception:
        case EndpointConnectionError() |  ConnectionClosedError():
            return True
        case ClientError():
            code = exception.response.get("Error", {}).get("Code", "")
            return code in None or code in AWS_RETRYABLE_ERROR_CODES
        case _:
            return False


def _fp(*parts: str | None) -> str:
    """
    Function to hash the given parts using SHA-256 and return the hexadecimal digest.
    This can be used to create unique identifiers for caching or other purposes.
    """
    h = hashlib.sha256()

    for p in parts:
        h.update((p or "").encode()); h.update(b"\0")
    return h.hexdigest()


class StorageClass(StrEnum):
    STANDARD = "STANDARD"
    STANDARD_IA = "STANDARD_IA"
    ONEZONE_IA = "ONEZONE_IA"
    GLACIER = "GLACIER"
    GLACIER_IR = "GLACIER_IR"
    DEEP_ARCHIVE = "DEEP_ARCHIVE"
    INTELLIGENT_TIERING = "INTELLIGENT_TIERING"


class RetryMode(StrEnum):
    STANDARD = "standard"
    ADAPTIVE = "adaptive"
    LEGACY = "legacy"
