"""File to handle the AWS S3 module"""
# Standard Library Imports
import logging
from threading import Lock
from typing import Optional, List


# Local Imports
from .aws_connections_module import get_client
from aws_services.helper_utils.utils import aws_retryable
from aws_services.helper_utils.variables import DEFAULT_REGION


logger = logging.getLogger(__name__)

__all__ = ["AwsS3Module", "S3OperationError"]


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
            aws_region: str = DEFAULT_REGION,
            aws_access_key_id: Optional[str] = None,
            aws_secret_access_key: Optional[str] = None,
            aws_session_token: Optional[str] = None,
            max_attempts: int = 10
    ):
        """
        Parameters:
        ----------
            aws_region:
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
        self._aws_region = aws_region
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
                        region=self._aws_region,
                        config_mode="adaptive",
                        max_attempts=self._max_attempts,
                        aws_access_key_id=self._aws_access_key_id,
                        aws_secret_access_key=self._aws_secret_access_key,
                        aws_session_token=self._aws_session_token
                    )
        return self._client

    # ------------------------ Read ---------------------------------------------
    @aws_retryable(logger)
    def get_s3_file(self, bucket_name: str, s3_file_path: str) -> tuple:
        """
        Function to read file from s3 bucket.
        Parameters:
        ----------
            bucket_name:
                Name of the S3 bucket
            s3_file_path:
                Path to the file in the S3 bucket (key)

        Return:
        ------
            tuple: (status_code, file_content_bytes)

        Raises:
        ------
            ClientError: On s3 API error (e.g. NoSuchKey).
        """
        logger.info("Reading s3://%s/%s", bucket_name, s3_file_path)
        obj = self.client.get_object(Bucket=bucket_name, Key=s3_file_path)
        status_code = obj["ResponseMetadata"]["HTTPStatusCode"]

        logger.info("Status code of the read s3://%s/%s call is %s", bucket_name, s3_file_path, status_code)
        return status_code, obj["Body"].read()


    # ------------------------ Write ---------------------------------------------
    @aws_retryable(logger)
    def put_s3_file(
            self,
            bucket_name: str,
            s3_file_path: str,
            data,
            content_type: str = "application/octet-stream",
            storage_class: str = "STANDARD",
            s3_kms_key_id: Optional[str] = None,
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
                it will be read from the current position.
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
        if hasattr(data, "seek"):
            data.seek(0)

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
        if status_code != 200:
            raise S3OperationError(
                f"put_object to s3://%s%s is %s", bucket_name, s3_file_path, status_code
            )
        logger.info(f"Status of the files written to s3://%s/%s is %s", bucket_name, s3_file_path, status_code)


    # ----------------------------- List / Query ----------------------------------------------------------

    @aws_retryable(logger)
    def list_objects(
            self,
            bucket_name: str,
            prefix: str,
            suffix: Optional[str] = None
    ) -> List[str]:
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
        return self._list_objects_internal(bucket_name, prefix, suffix)

    def _list_objects_internal(
            self,
            bucket_name: str,
            prefix: str,
            suffix: Optional[str] = None
    ) -> List[str]:
        """
        Internal Function to list objects in s3://%s/%s suffix
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
        results: List[str] = []

        for page in paginator.paginate(Bucket=bucket_name, Prefix=prefix):
            for obj in page.get("Contents", []):
                if suffix is None or obj["Key"].endswith(suffix):
                    results.append(obj["Key"])

        return results

    # ------------------------------- Delete -------------------------------------------------

    @aws_retryable(logger)
    def delete_objects(
            self,
            bucket_name: str,
            prefix: str,
            max_delete: Optional[int] = None
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
        logger.info("Deleting objects in s3://%s/%s", bucket_name, prefix)
        objects = self._list_objects_internal(bucket_name, prefix)
        if not objects:
            logger.info("No objects found to delete in s3://%s/%s", bucket_name, prefix)
            return 0

        # Apply optional cap
        if max_delete is not None:
            objects = objects[:max_delete]

        deleted_count = 0
        # delete_objects accepts max 1000 keys per call
        for i in range(0, len(objects), 1000):
            batch = [{"Key": obj} for obj in objects[i:i + 1000]]
            response = self.client.delete_objects(Bucket=bucket_name, Delete={"Objects": batch, "Quiet": True})
            errors = response.get("Errors", [])
            if errors:
                logger.error("Errors occurred while deleting objects in s3://%s/%s: %s", bucket_name, prefix, errors)
                raise S3OperationError(f"Failed to delete some objects in s3://{bucket_name}/{prefix} count: {len(errors)}")
            deleted_count += len(batch)

        logger.info("Deleted %d objects in s3://%s/%s", deleted_count, bucket_name, prefix)
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
