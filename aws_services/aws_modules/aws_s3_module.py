"""File to handle the AWS S3 module"""
from __future__ import annotations

# Standard Library Imports
import logging, io, os
from threading import Lock
from datetime import datetime, timezone
from typing import IO, Iterator, BinaryIO, Any

# PIP Imports
from boto3.s3.transfer import TransferConfig
from botocore.exceptions import ClientError, NoCredentialsError

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
            size = int(obj["ContentLength"]) if "ContentLength" in obj else 0
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

    # ------------------------ Write ---------------------------------------------

    @aws_retryable(logger)
    def upload_file_to_s3(
            self,
            file_obj: BinaryIO,
            bucket_name: str,
            s3_file_path: str,
            config: bool = False,
            kms_key_id: str | None = None,
            multipart_threshold: int = 100 * 1024 * 1024, # 100 MB
            multipart_chunksize: int = 20 * 1024 * 1024, # 100 MB chunks
            max_concurrency: int = 10, # parallel threads
            use_threads: bool = True
    ) -> None:
        """
        Function to upload a file-like object to S3 with optional KMS encryption and multipart upload support.
        Notes:
            - Requires a seekable stream so retries can restart from byte 0.
            - Uses multipart config only when `config=True`.

        Parameters:
        ----------
            file_obj:
                A file-like object (e.g. io.BytesIO, open file handle) containing the data to upload.
            bucket_name:
                The name of the S3 bucket.
            s3_file_path:
                The path to the file in the S3 bucket (e.g. "folder/subfolder/file.csv").
            config:
                Whether to use transfer configuration for multipart upload. Default is False.
            kms_key_id:
                The KMS key ID for server-side encryption.
            multipart_threshold:
                Threshold for multipart upload in bytes. Files larger than this will be uploaded in parts. Default
                is 100 MB.
            multipart_chunksize:
                Size of each part in bytes when performing multipart upload. Default is 100 MB.
            max_concurrency:
                The maximum number of concurrent multipart uploads. Default is 10.
            use_threads:
                Whether to use threads for multipart uploads. Default is True.
        """
        if not hasattr(file_obj, "seek") or not hasattr(file_obj, "read"):
            raise TypeError("file_obj must be a file-like object with read() and seek() methods")

        # Safe retries require rewinding to start
        try:
            file_obj.seek(0)
        except Exception as err_msg:
            raise ValueError("upload_object requires a seekable stream for safe retries") from err_msg

        logger.info("Uploading file to s3://%s/%s", bucket_name, s3_file_path)
        upload_kwargs = AwsS3Module._build_transfer_kwargs(
            config,
            multipart_threshold,
            multipart_chunksize,
            max_concurrency,
            use_threads,
            kms_key_id,
            allow_extra_args=True
        )

        self.client.upload_file_obj(
            file_obj,
            bucket_name,
            s3_file_path,
            **upload_kwargs
        )
        logger.info("Successfully uploaded file to s3://%s/%s", bucket_name, s3_file_path)

    @staticmethod
    def _estimated_parts(file_size_bytes: int, part_size_bytes: int) -> int:
        """
        Parameters:
        ----------
            file_size_bytes:
                Size of the file in bytes.
            part_size_bytes:
                Size of each part in bytes.
        Returns:
        --------
            Estimated number of parts for multipart upload.
        """
        if file_size_bytes < 0:
            raise ValueError(f"file_size_bytes must be >= 0, got {file_size_bytes}")
        if part_size_bytes <= 0:
            raise ValueError(f"part_size_bytes must be > 0, got {part_size_bytes}")

        return -(-file_size_bytes // part_size_bytes) # ceiling division

    def abort_incomplete_multipart_uploads(
            self,
            bucket_name: str,
            key: str,
            min_age_seconds: int = 900, # 15-min safety window
            exact_key: bool = True
    ) -> int:
        """
        Aborts all incomplete multipart uploads matching the given key prefix in the S3 bucket.
        This is useful for cleaning up resources and avoiding unnecessary storage costs.
        Parameters:
        ----------
            bucket_name:
                The name of the S3 bucket.
            key:
                The key to match incomplete multipart uploads.
            min_age_seconds:
                The minimum age of incomplete multipart uploads to abort (defaults to 900 seconds).
            exact_key:
                If True, only abort uploads that exactly match the key. If False,
                abort any uploads that start with the key.
        Returns:
        -------
            The number of aborted multipart uploads.
        """
        if min_age_seconds < 0:
            raise ValueError(f"min_age_seconds must be >= 0, got {min_age_seconds}")

        paginator = self.client.get_paginator("list_multipart_uploads")
        aborted_count = 0
        now = datetime.now(timezone.utc)

        try:
            for page in paginator.paginate(Bucket=bucket_name, Prefix=key):
                for upload in page.get("Uploads", []):
                    upload_key = upload.get("Key", "")
                    initiated = upload.get("Initiated")

                    if exact_key and upload_key != key:
                        continue

                    # Only abort old uploads to avoid killing active writers
                    if initiated is not None:
                        age_seconds = (now - initiated).total_seconds()
                        if age_seconds < min_age_seconds:
                            continue

                    try:
                        self.client.abort_multipart_upload(
                            Bucket=bucket_name,
                            Key=upload_key,
                            UploadId=upload.get('UploadId')
                        )
                        logger.warning(
                            f"Aborted orphaned multipart upload for key: {upload_key} uploaded Id = {upload.get('UploadId')}"
                        )
                        aborted_count += 1
                    except ClientError as error_msg:
                        logger.error(
                            f"Failed to abort upload Key = {upload_key} uploaded Id = {upload.get('UploadId')}: {error_msg}"
                        )
                        continue

        except ClientError as error_msg:
            logger.error(f"Failed to clean multipart uploads for bucket {bucket_name} with prefix {key}: {error_msg}")

        if aborted_count:
            logger.info("Cleaned up %d incomplete multipart uploads.", aborted_count)
        return aborted_count

    @aws_retryable(logger)
    def upload_file(
            self,
            file_path: str,
            bucket_name: str,
            s3_file_path: str | None = None,
            config: bool = False,
            kms_key_id: str | None = None,
            multipart_threshold: int = 100 * 1024 * 1024,
            multipart_chunksize: int = 100 * 1024 * 1024,
            max_concurrency: int = 10,
            cleanup_orphans: bool = True,
            cleanup_on_failure: bool = False,
            use_threads: bool = True
    ) -> bool:
        """
        Upload a local file to S3 with optional multipart upload and cleanup of orphaned uploads.
        Parameters:
        ----------
            file_path:
                Absolute path to the local file to upload.
            bucket_name:
                The name of the target S3 bucket.
            s3_file_path:
                Destination path in the S3 bucket. If None, the file name from file_path will be used.
            config:
                Whether to use TransferConfig for multipart upload configuration. Default is False.
            kms_key_id:
                Optional KMS key ID or ARN for the server side encryption.
            multipart_threshold:
                Threshold for multipart upload in bytes. Files larger than this will be uploaded in parts.
                Default is 100 MB.
            multipart_chunksize:
                Chunk size (in bytes) for each part in a multipart upload. Default is 100 MB.
            max_concurrency:
                Max number of threads to use for multipart uploads. Default is 10.
            cleanup_orphans:
                Abort any pre-existing incomplete uploads for this key. Default is True.
            cleanup_on_failure:
                If True, attempts stale multipart cleanup after a failed upload.
                Note: This may abort other uploads on the same key that are older than min_age_seconds.
                Default is False for safety.
            use_threads:
                Whether to use threads for uploading. Default is True.

        Returns:
        -------
            True if the upload was successful, False otherwise.
        """
        if s3_file_path is None:
            s3_file_path = os.path.basename(file_path)

        if not os.path.isfile(file_path):
            logger.error(f"File {file_path} does not exist.")
            return False

        file_size = os.path.getsize(file_path)
        estimated_parts = None

        if config:
            if multipart_chunksize < 5 * 1024 * 1024:
                logger.error("multipart_chunksize must be >= 5 MiB when")
                return False

            try:
                estimated_parts = AwsS3Module._estimated_parts(file_size, multipart_threshold)
            except ValueError as exc:
                logger.error("Invalid multipart chunk configuration: %s", exc)
                return False

            # Guard: S3 hard limit is 10,000 parts
            if estimated_parts > 10_000:
                logger.error(
                    "File too large for chunk size: %d parts estimated, S3 limit is 10,000."
                    " Increase multipart_chunksize.", estimated_parts
                )
                return False

        logger.info(f"File: {file_path} ({file_size / (1024 ** 3 ):.2f} GB)")
        logger.info(f"Upload file under target s3://{bucket_name}/{s3_file_path}")
        chunk_mb = multipart_chunksize / (1024 * 1024)
        logger.info("Config: chunk=%d bytes (%.2f MiB), concurrency=%d, parts~%s",
                    multipart_chunksize, chunk_mb, max_concurrency, estimated_parts
        )

        upload_kwargs = AwsS3Module._build_transfer_kwargs(
            config,
            multipart_threshold,
            multipart_chunksize,
            max_concurrency,
            use_threads,
            kms_key_id,
            allow_extra_args=True
        )

        # Clean up any orphaned incomplete uploads for this key before starting
        if cleanup_orphans:
            self.abort_incomplete_multipart_uploads(bucket_name, s3_file_path, min_age_seconds=900, exact_key=True)

        try:
            self.client.upload_file(file_path, bucket_name, s3_file_path, **upload_kwargs)
        except NoCredentialsError as error_msg:
            logger.error(
                "AWS credentials not found. Configure via environment variables, "
                "AWS CLI, or IAM role. Error: %s", error_msg
            )
            if cleanup_on_failure:
                logger.info("Attempting to clean up incomplete uploads due to failure...")
                self.abort_incomplete_multipart_uploads(bucket_name, s3_file_path, min_age_seconds=900, exact_key=True)
            return False
        except ClientError as error_msg:
            code = error_msg.response["Error"]["Code"]
            msg = error_msg.response["Error"]["Message"]
            logger.error(f"S3 ClientError [{code}]: {msg}")
            if cleanup_on_failure:
                logger.info("Attempting to clean up incomplete uploads due to failure...")
                self.abort_incomplete_multipart_uploads(bucket_name, s3_file_path, min_age_seconds=900,
                                                            exact_key=True)
            return False
        except Exception as error_msg:
            logger.error(f"Unexpected error occurred: {error_msg}")
            return False

        logger.info("S3 Upload Complete s3://%s/%s", bucket_name, s3_file_path)
        return True


    # ----------------------------- Copy File ----------------------------------------------------------
    @aws_retryable(logger)
    def copy_file_to_s3(
            self,
            source_bucket: str,
            source_key: str,
            source_client: AwsS3Module,
            destination_bucket: str,
            destination_key: str,
            config: bool = False,
            kms_key_id: str | None = None,
            multipart_threshold: int = 100 * 1024 * 1024,  # 100 MB
            multipart_chunksize: int = 20 * 1024 * 1024,  # 100 MB chunks
            max_concurrency: int = 10,  # parallel threads
            use_threads: bool = True
    ) -> bool:
        """
        Copy an s3 object into another s3 bucket and location.

        Parameters:
        ----------
            source_bucket:
                The name of the Source S3 bucket.
            source_key:
                The Source bucket key of the object to copy.
            source_client:
                The S3 client for the source bucket.
            destination_bucket:
                The name of the destination S3 bucket.
            destination_key:
                The key of the object in the destination bucket.
            config:
                Whether to use transfer config.
            kms_key_id:
                The KMS key ID for server-side encryption.
            multipart_threshold:
                Size threshold for multipart uploads.
            multipart_chunksize:
                Size of each part in bytes when performing multipart upload.
            max_concurrency:
                The maximum number of concurrent multipart uploads.
            use_threads:
                Whether to use threads for multipart uploads.

        Returns:
        -------
            A boolean true if the copy is successful, raises error otherwise.
        """
        logger.info(
            "Starting copy file: s3://%s/%s -> s3://%s/%s",
            source_bucket, source_key, destination_bucket, destination_key
        )
        copy_kwargs = AwsS3Module._build_transfer_kwargs(
            config,
            multipart_threshold,
            multipart_chunksize,
            max_concurrency,
            use_threads,
            kms_key_id,
            allow_extra_args=True
        )

        copy_source = {"Bucket": source_bucket, "Key": source_key}
        self.client.copy(
            CopySource=copy_source,
            Bucket=destination_bucket,
            Key=destination_key,
            **copy_kwargs,
            SourceClient=source_client
        )
        logger.info("Successfully copied file to s3://%s/%s", destination_bucket, destination_key)
        return True

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

    @aws_retryable(logger)
    def delete_object(self, bucket_name: str, key: str) -> bool:
        """
        Delete a single S3 Object by exact key from the S3 bucket.

        Parameters:
        ----------
            bucket_name:
                Name of the S3 bucket
            key:
                Key of the object to delete

        Returns:
        -------
            True if the deletion is successful (or object not found), False on error.
        """
        logger.info("Deleting object from s3://%s/%s", bucket_name, key)
        try:
            self.client.delete_object(Bucket=bucket_name, Key=key)
        except ClientError as error_msg:
            logger.error("Failed to delete s3://%s/%s: %s",bucket_name, key, error_msg)
            return False
        return True

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

    # ------------------------------- Download -------------------------------------------------
    @aws_retryable(logger)
    def download_object_from_s3(
            self,
            bucket_name: str,
            s3_file_path: str,
            file_obj: BinaryIO | None = None,
            config: bool = False,
            multipart_threshold: int = 100 * 1024 * 1024,  # 100 MB
            multipart_chunksize: int = 20 * 1024 * 1024,  # 100 MB chunks
            max_concurrency: int = 10,  # parallel threads
            use_threads: bool = True,
            max_bytes: int | None = None,
    ) -> io.BytesIO | None:
        """
        Download an S3 object to a file-like object with optional multipart download support and memory guard.

        Parameters:
        -----------
        bucket_name:
            Name of the S3 bucket
        s3_file_path:
            Path to the file in the S3 bucket (key)
        file_obj:
            A file-like object (e.g. io.BytesIO, open file handle) to write
            the downloaded data to. If not provided, a new io.BytesIO() will be used and returned.
        config:
            Whether to use transfer configuration for multipart download. Default is False.
        multipart_threshold:
            Threshold for multipart download in bytes. Files larger than this will be downloaded in parts. Default
            is 100 MB.
        multipart_chunksize:
            Size of each part in bytes when performing multipart download. Default is 100 MB.
        max_concurrency:
            The maximum number of concurrent multipart downloads. Default is 10.
        use_threads:
            Whether to use threads for multipart downloads. Default is True.
        max_bytes:
            Optional maximum number of bytes to read from the object.
            If provided, a head_object call will be made to check the content length before downloading,
            and an error will be raised if the object size exceeds max_bytes.
            This is useful as a memory guard to avoid downloading large objects when only a preview is needed.
        """
        logger.info("Downloading object from s3://%s/%s", bucket_name, s3_file_path)

        # Optional memory guard before allocating/streaming full content.
        if max_bytes is not None:
            head  = self.client.head_object(Bucket=bucket_name, Key=s3_file_path)
            content_length = int(head.get("ContentLength", 0))
            if content_length > max_bytes:
                raise S3OperationError(
                    f"Object size {content_length} exceeds {max_bytes} bytes, aborting"
                )

        download_kwargs = AwsS3Module._build_transfer_kwargs(
            config,
            multipart_threshold,
            multipart_chunksize,
            max_concurrency,
            use_threads,
            kms_key_id=None,
            allow_extra_args=False
        )

        buffer = file_obj if file_obj is not None else io.BytesIO()
        if hasattr(buffer, "seek"):
            buffer.seek(0)
        if hasattr(buffer, "truncate"):
            buffer.truncate(0)
        self.client.download_fileobj(
            bucket_name, s3_file_path, buffer, **download_kwargs
        )

        if file_obj is not None:
            buffer.seek(0)
            return buffer

        logger.info("Downloaded object from s3://%s/%s", bucket_name, s3_file_path)
        return None
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

    @staticmethod
    def _build_transfer_kwargs(
            use_config: bool,
            multipart_threshold: int,
            multipart_chunksize: int,
            max_concurrency: int,
            use_threads: bool,
            kms_key_id: str | None = None,
            allow_extra_args: bool = True
    ) -> dict[str, Any]:
        """
        Transfer kwargs specific to AWS S3
        Parameters:
        ----------
            use_config:
                Whether to include the TransferConfig in the kwargs.
            multipart_threshold:
                 The size threshold for multipart uploads.
            multipart_chunksize:
                The chunk size for multipart uploads.
            max_concurrency:
                The maximum number of threads for multipart uploads.
            use_threads:
                Whether to use threads for multipart uploads.
            kms_key_id:
                Optional KMS key ID for server-side encryption. If provided, ExtraArgs will include the KMS settings.
            allow_extra_args:
                Whether to include ExtraArgs in the kwargs if kms_key_id is provided.
        Return:
        -------
            dict[str, Any]: Dictionary of transfer kwargs for S3 operations.
        """
        kwargs: dict[str, Any] = {}
        if use_config:
            kwargs["Config"] = TransferConfig(
                multipart_threshold=multipart_threshold,
                multipart_chunksize=multipart_chunksize,
                max_concurrency=max_concurrency,
                use_threads=use_threads
            )

        if allow_extra_args and kms_key_id:
            kwargs["ExtraArgs"] = {
                "ServerSideEncryption": "aws:kms",
                "SSEKMSKeyId": kms_key_id
            }
        return kwargs
