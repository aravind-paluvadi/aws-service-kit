"""Helper module for project, contains utility functions"""
# Standard Library Imports
import logging


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


def update_dict_keys(fields, mapping):
    """
    Update the keys of the fields dictionary based on the provided mapping. This allows for flexible renaming
    of fields while ensuring that only expected keys are updated.
    Parameters:
    ----------
        fields:
            The original dictionary containing the fields to be updated.
        mapping:
            A dictionary containing the fields are the original field name and values are the new fields names.

    Returns:
    -------
        A new dictionary with the updated fields based on the provided mapping.
    """
    if mapping:
        for key, value in mapping.items():
            if key in fields:
                fields[key] = value
            # The key must exist in the available fields
            else:
                raise TypeError(f"Unexpected key {key} in mapping")

    return fields

def require_non_empty(**fields):
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
    if isinstance(exception, (EndpointConnectionError, ConnectionClosedError)):
        return True
    if isinstance(exception, ClientError):
        code = exception.response.get("Error", {}).get("Code", "")
        return code in AWS_RETRYABLE_ERROR_CODES
    return False
