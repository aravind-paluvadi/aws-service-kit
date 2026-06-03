"""File to handle the AWS S3 module"""
from __future__ import annotations

# Standard Library Imports
import logging, io
from threading import Lock
from typing import IO, Iterator, Any

# Local Imports
from .aws_connections_module import get_client
from aws_services.helper_utils.variables import DEFAULT_REGION
from aws_services.helper_utils.utils import aws_retryable, StorageClass, RetryMode


logger = logging.getLogger(__name__)

__all__ = ["AwsS3Module", "S3OperationError"]
type BYTES_DATA = bytes | bytearray | memoryview | IO[bytes]


class S3OperationError(Exception):
    """Exception raised when an S3 operation fails"""


class AwsS3Module:
    """
    Class to handle AWS S3 operations with retry logic and lazy client initialization. Provides methods to
    read, write, list, and delete objects in S3.

    Retries are handled at two levels:
        - botocore adaptive retry (built into the client config)
        - @aws_retryable decorator for transient AWS errors
    """

    def __init__(
            self,
            region_name: str = DEFAULT_REGION,
            aws_access_key_id: str | None = None,
            aws_secret_access_key: str | None = None,
            aws_session_token: str | None = None,
            max_attempts: int = 10
    ):
        """
        Parameters:
        ----------
            region_name:
                AWS region name (e.g. 'us-east-1'). If not provided, will use default from session or fallback.
            aws_access_key_id:
                AWS access key ID for authentication. If not provided, will use default credential resolution.
            aws_secret_access_key:
                AWS secret access key for authentication. If not provided, will use default credential resolution.
            aws_session_token:
                AWS session token for temporary credentials. If not provided, will use default credential resolution.
            max_attempts:
                Maximum retry attempts for AWS operations. This is passed to the botocore client config for
                adaptive retries. (default: 10)
        """
        self._region_name = region_name
        self._aws_access_key_id = aws_access_key_id
        self._aws_secret_access_key = aws_secret_access_key
        self._aws_session_token = aws_session_token
        self._max_attempts = max_attempts
        self._client = None # Lazy init
        self._client_lock = Lock()

    @property
    def client(self):
        """Lazy-load the AWS S3 client on first use"""
        if self._client is None:
            with self._client_lock:
                if self._client is None:
                    self._client = get_client(
                        "s3",
                        region_name=self._region_name,
                        retry_mode=RetryMode.ADAPTIVE.value,
                        max_attempts=self._max_attempts,
                        aws_access_key_id=self._aws_access_key_id,
                        aws_secret_access_key=self._aws_secret_access_key,
                        aws_session_token=self._aws_session_token
                    )
        return self._client

    # ------------------------ Read ---------------------------------------------
    @aws_retryable(logger)
    def get_s3_file(self, bucket_name: str, s3_file_path: str, max_bytes: int | None = None) -> tuple[int, bytes]:
        """
        Function to read file from s3 bucket.
        Parameters:
        ----------
            bucket_name:
                Name of the S3 bucket
            s3_file_path:
                Path to the file in the S3 bucket (key)
            max_bytes:
                Optional maximum number of bytes to read from the file. If not provided,
                the entire file will be read. Useful for large files or when only a preview is needed.

        Return:
        ------
            tuple: (status_code, file_content_bytes)

        Raises:
        ------
            ClientError: On s3 API error (e.g. NoSuchKey).
        """
        logger.info("Reading s3://%s/%s", bucket_name, s3_file_path)
        obj = self.client.get_object(Bucket=bucket_name, Key=s3_file_path)
        if max_bytes is not None:
            size = int(obj.get("ContentLength", 0))
            if size > max_bytes:
                raise S3OperationError(f"Object s3://{bucket_name}/{s3_file_path} is {size} bytes, exceeds max_bytes={max_bytes}")

        status_code = obj.get("ResponseMetadata", {}).get("HTTPStatusCode")
        logger.info("Status code of the read s3://%s/%s call is %s", bucket_name, s3_file_path, status_code)
        return status_code, obj["Body"].read()


    # ------------------------ Write ---------------------------------------------
    @aws_retryable(logger)
    def put_s3_file(
            self,
            bucket_name: str,
            s3_file_path: str,
            data: BYTES_DATA,
            content_type: str = "application/octet-stream",
            storage_class: str = StorageClass.STANDARD,
            s3_kms_key_id: str | None = None,
            server_side_encryption: str = "aws:kms"
    ) -> None:
        """
        Function to write file in s3 bucket with optional KMS encryption.
        Parameters:
        ----------
            bucket_name:
                Name of the S3 bucket
            s3_file_path:
                Path to the file in the S3 bucket (key)
            data:
                File content as bytes or a file-like object. If a file-like object is provided,
                it will be read from the current position. Data must be bytes or seekable stream.
            content_type:
                MIME type of the file (default: application/octet-stream)
            storage_class:
                S3 storage class (default: STANDARD)
            s3_kms_key_id:
                Optional KMS key ID for server-side encryption. If provided, server_side_encryption must be set to 'aws:kms'.
            server_side_encryption:
                Server-side encryption method (default: 'aws:kms'). Ignored if s3_kms_key_id is not provided.
        Return:
        ------
            None, if the upload is successful.

        Raises:
        ------
            S3OperationError: If the upload fails (non-200 status code) or if KMS encryption parameters are invalid.
        """
        # To reset the data stream
        if isinstance(data, io.IOBase):
            if data.seekable():
                data.seek(0)
            else:
                raise ValueError("Requires a seekable stream for safe retries")

        put_kwargs = {
            "Bucket": bucket_name,
            "Key": s3_file_path,
            "Body": data,
            "ContentType": content_type,
            "StorageClass": storage_class
        }
        if s3_kms_key_id:
            put_kwargs["ServerSideEncryption"] = server_side_encryption
            put_kwargs["SSEKMSKeyId"] = s3_kms_key_id


        logger.info("Writing s3://%s/%s", bucket_name, s3_file_path)
        response = self.client.put_object(**put_kwargs)

        status_code = response["ResponseMetadata"]["HTTPStatusCode"]
        if status_code >= 300:
            raise S3OperationError(f"put_object to s3://{bucket_name}{s3_file_path} is {status_code}")
        logger.info("Status of the files written to s3://%s/%s is %s", bucket_name, s3_file_path, status_code)


    # ----------------------------- List / Query ----------------------------------------------------------

    @aws_retryable(logger)
    def list_objects(
            self,
            bucket_name: str,
            prefix: str,
            suffix: str | None = None
    ) -> list[str]:
        """
        Function to list objects in s3://%s/%s suffix with aws retryable
        Parameters:
        ----------
            bucket_name:
                Name of the S3 bucket
            prefix:
                Prefix to filter objects in the S3 bucket (e.g. folder path)
            suffix:
                Optional suffix to further filter objects (e.g. file extension)

        Return:
        ------
            List of object keys that match the prefix and optional suffix.
        """
        logger.info("Listing objects in s3://%s/%s suffix=%s", bucket_name, prefix, suffix)
        paginator = self.client.get_paginator("list_objects_v2")
        results: list[str] = []

        for page in paginator.paginate(Bucket=bucket_name, Prefix=prefix):
            for obj in page.get("Contents", []):
                if (key := obj["Key"]) and (suffix is None or key.endswith(suffix)):
                    results.append(key)

        return results

    # ------------------------------- Delete -------------------------------------------------

    def _delete_batch(self, bucket_name: str, batch: list[dict]) -> int:
        """
        Delete a single batch of up to 1000 s3 objects
        Parameters:
        ----------
            bucket_name:
                Name of the S3 bucket
            batch:
                List of ``{"Key": "<key>"}`` dicts. Must be 1..1000 items.

        Return:
        ------
            The number of objects deleted in this batch.

        Raises:
        -------
            S3OperationError: If the S3 reports per-object errors in the response.
        """
        if not batch:
            return 0

        if len(batch) > 1000:
            raise ValueError(f"S3 delete_objects accepts at most 1000 keys, got {len(batch)}")

        response = self.client.delete_objects(
            Bucket=bucket_name,
            Delete={"Objects": batch, "Quiet": True},
        )
        if errors := response.get("Errors"):
            logger.error("Error while deleting objects in s3://%s: %s", bucket_name, errors)
            raise S3OperationError(f"Failed to delete {len(errors)} objects in s3://{bucket_name}")

        return len(batch)

    @aws_retryable(logger)
    def delete_objects(
            self,
            bucket_name: str,
            prefix: str,
            max_delete: int | None = None
    ) -> int:
        """
        Function to delete objects in s3://%s/%s with aws retryable, can optionally limit
        the number of deletions with max_delete.

        Parameters:
        ----------
            bucket_name:
                Name of the S3 bucket
            prefix:
                Prefix to filter objects in the S3 bucket (e.g. folder path)
            max_delete:
                Optional maximum number of objects to delete. If not provided, all matching objects will be deleted.

        Return:
        ------
            The number of objects deleted.
        """
        if max_delete is not None and max_delete <= 0:
            return 0

        logger.info("Deleting objects in s3://%s/%s", bucket_name, prefix)

        batch: list[dict] = []
        deleted_count = 0

        d_paginator = self.client.get_paginator("list_objects_v2")
        for page in d_paginator.paginate(Bucket=bucket_name, Prefix=prefix):
            for obj in page.get("Contents", []):
                batch.append({"Key": obj["Key"]})

                # Trim batch if we'd exceed max_delete, then flush and return.
                if max_delete is not None and deleted_count + len(batch) >= max_delete:
                    batch = batch[: max_delete - deleted_count]
                    deleted_count = self._delete_batch(bucket_name, batch)
                    logger.info("Deleted %d objects under s3://%s/%s (capped)", deleted_count, bucket_name, prefix)
                    return deleted_count

                # Flush a full S3-sized batch.
                if len(batch) == 1000:
                    deleted_count += self._delete_batch(bucket_name, batch)
                    batch = []

        # Flush any remainder.
        if batch:
            deleted_count += self._delete_batch(bucket_name, batch)

        logger.info("Deleted %d objects under s3://%s/%s", deleted_count, bucket_name, prefix)
        return deleted_count

    # --------------------------------------- Utility ----------------------------------------
    @aws_retryable(logger)
    def prefix_exists(self, bucket_name: str, prefix: str) -> bool:
        """
        Check if any object exists with the given prefix
        Parameters:
        ----------
            bucket_name:
                Name of the S3 bucket
            prefix:
                Prefix to filter objects in the S3 bucket (e.g. folder path)

        Return:
        ------
            True if at least one object exists with the given prefix, False otherwise.
        """
        logger.info("Checking existence of prefix s3://%s/%s", bucket_name, prefix)
        response = self.client.list_objects_v2(Bucket=bucket_name, Prefix=prefix, MaxKeys=1)
        return response.get("KeyCount", 0) > 0

    def iter_objects(self, bucket_name: str, prefix: str, suffix: str | None = None) -> Iterator[str]:
        """
        Yield S3 Keys one at a time without buffering the full list.

        NOTE: Not retryable. Transient errors during pagination will propagate. Use list_objects()
        if you need automatic retries (at the cost of memory).
        Parameters:
        ----------
            bucket_name:
                Name of the S3 bucket
            prefix:
                Prefix to filter objects in the S3 bucket (e.g. folder path)
            suffix:
                Optional suffix to further filter objects (e.g. file extension)
        Return:
        ------
            S3 Key
        """
        i_paginator = self.client.get_paginator("list_objects_v2")
        i_page_iter = i_paginator.paginate(Bucket=bucket_name, Prefix=prefix)

        @aws_retryable(logger)
        def _next_page(it):
            return next(it, None)

        while (page := _next_page(i_page_iter)) is not None:
            for obj in page.get("Contents", []):
                if (key := obj["Key"]) and (suffix is None or key.endswith(suffix)):
                    yield key
