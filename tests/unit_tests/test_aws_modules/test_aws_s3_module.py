"""Test file for AWS S3 module"""
# PIP Imports
import pytest

# Local Imports
from aws_services.aws_modules.aws_s3_module import AwsS3Module, S3OperationError


class TestAwsS3Module:
    """Tests class for AWS S3 module"""

    def test_get_s3_file(self, mocker):
        """Test get s3 file function"""
        mock_get_s3 = mocker.MagicMock()
        mock_get_s3.get_object.return_value = {"ResponseMetadata": {"HTTPStatusCode": 200}, "Body": mocker.MagicMock()}
        mocker.patch("aws_services.aws_modules.aws_s3_module.get_client", return_value=mock_get_s3)

        status, body = AwsS3Module().get_s3_file("bucket_name", "path/to/file")
        assert status == 200
        assert body is not None
        mock_get_s3.get_object.assert_called_once_with(Bucket="bucket_name", Key="path/to/file")

    def test_put_file_in_s3(self, mocker):
        """Test put s3 file function"""
        mock_s3_client = mocker.MagicMock()
        mock_s3_client.put_object.return_value = {"ResponseMetadata": {"HTTPStatusCode": 200}}
        mocker.patch("aws_services.aws_modules.aws_s3_module.get_client", return_value=mock_s3_client)

        AwsS3Module().put_s3_file("bucket_name", "path/to/file", b"data")

        mock_s3_client.put_object.assert_called_once_with(
            Bucket="bucket_name",
            Key="path/to/file",
            Body=b"data",
            ContentType="application/octet-stream",
            StorageClass="STANDARD"
        )

    def test_put_file_in_s3_raises_on_non_200(self, mocker):
        """Test put s3 file function raises S3OperationError when response status code is not 200"""
        mock_put_s3 = mocker.MagicMock()
        mock_put_s3.put_object.return_value = {"ResponseMetadata": {"HTTPStatusCode": 500}}
        mocker.patch("aws_services.aws_modules.aws_s3_module.get_client", return_value=mock_put_s3)

        with pytest.raises(S3OperationError):
            AwsS3Module().put_s3_file("bucket_name", "path/to/file", b"data")

    def test_put_file_in_s3_with_kms(self, mocker):
        """Test put s3 file function includes KMS kwargs when kms key provided"""
        mock_s3_client = mocker.MagicMock()
        mock_s3_client.put_object.return_value = {"ResponseMetadata": {"HTTPStatusCode": 200}}
        mocker.patch("aws_services.aws_modules.aws_s3_module.get_client", return_value=mock_s3_client)

        AwsS3Module().put_s3_file(
            "bucket_name",
            "path/to/file",
            b"data",
            s3_kms_key_id="arn:aws:kms:us-west-2:123456789012:key/abc"
        )

        call_kwargs = mock_s3_client.put_object.call_args[1]
        assert call_kwargs["ServerSideEncryption"] == "aws:kms"
        assert call_kwargs["SSEKMSKeyId"] == "arn:aws:kms:us-west-2:123456789012:key/abc"

    def test_list_objects(self, mocker):
        """Test function to list objects in the s3 path"""
        mock_paginate = mocker.MagicMock()
        mock_paginate.paginate.return_value = [
            {
                "Contents": [
                    {"Key": "path/to/file1.csv"}, {"Key": "path/to/file2.parquet"}, {"Key": "path/to/file3.csv"}
                ]
            }
        ]
        mock_s3_client = mocker.MagicMock()
        mock_s3_client.get_paginator.return_value = mock_paginate
        mocker.patch("aws_services.aws_modules.aws_s3_module.get_client", return_value=mock_s3_client)

        result = AwsS3Module().list_objects("bucket_name", "s3_prefix", suffix=".csv")
        assert result == ["path/to/file1.csv", "path/to/file3.csv"]

    def test_list_objects_no_suffix(self, mocker):
        """Test function to list objects in the s3 path returns all objects when no suffix is provided"""
        mock_paginate = mocker.MagicMock()
        mock_paginate.paginate.return_value = [{
            "Contents": [{"Key": "path/to/file1.csv"}, {"Key": "path/to/file2.parquet"}],
        }]
        mock_s3_client = mocker.MagicMock()
        mock_s3_client.get_paginator.return_value = mock_paginate
        mocker.patch("aws_services.aws_modules.aws_s3_module.get_client", return_value=mock_s3_client)

        result = AwsS3Module().list_objects("bucket_name", "s3_prefix")
        assert result == ["path/to/file1.csv", "path/to/file2.parquet"]

    def test_delete_prefix(self, mocker):
        """Test function to delete a prefix in the s3 path"""
        mock_paginate = mocker.MagicMock()
        mock_paginate.paginate.return_value = [{"Contents": [{"Key": "path/to/file1"}, {"Key": "path/to/file2"}]}]

        mock_delete_s3 = mocker.MagicMock()
        mock_delete_s3.get_paginator.return_value = mock_paginate
        mock_delete_s3.delete_objects.return_value = {"Error": []}
        mocker.patch("aws_services.aws_modules.aws_s3_module.get_client", return_value=mock_delete_s3)

        s3_delete_files = AwsS3Module().delete_objects("bucket_name", "s3_prefix")
        assert s3_delete_files == 2
        mock_delete_s3.delete_objects.assert_called_with(
            Bucket="bucket_name",
            Delete={"Objects": [{"Key": "path/to/file1"}, {"Key": "path/to/file2"}], "Quiet": True}
        )

    def test_delete_prefix_empty(self, mocker):
        """Test function to delete a prefix in the s3 path, returns 0 when no objects found"""
        mock_paginate = mocker.MagicMock()
        mock_paginate.paginate.return_value = [{"Contents": []}]
        mock_s3_client = mocker.MagicMock()
        mock_s3_client.get_paginator.return_value = mock_paginate
        mocker.patch("aws_services.aws_modules.aws_s3_module.get_client", return_value=mock_s3_client)

        result = AwsS3Module().delete_objects("bucket_name", "s3_prefix", max_delete=2)
        assert result == 0

    def test_delete_prefix_with_max_delete(self, mocker):
        """Test function to delete a prefix in the s3 path, returns number of deleted objects up to max_delete limit"""
        mock_paginate = mocker.MagicMock()
        mock_paginate.paginate.return_value = [
            {"Contents": [{"Key": "path/to/file1"}, {"Key": "path/to/file2"}, {"Key": "path/to/file3"}]}
        ]
        mock_s3_client = mocker.MagicMock()
        mock_s3_client.get_paginator.return_value = mock_paginate
        mock_s3_client.delete_objects.return_value = {"Error": []}
        mocker.patch("aws_services.aws_modules.aws_s3_module.get_client", return_value=mock_s3_client)

        result = AwsS3Module().delete_objects("bucket_name", "s3_prefix", max_delete=2)
        assert result == 2
        mock_s3_client.delete_objects.assert_called_with(
            Bucket="bucket_name",
            Delete={"Objects": [{"Key": "path/to/file1"}, {"Key": "path/to/file2"}], "Quiet": True}
        )

    def test_delete_prefix_raises_on_errors(self, mocker):
        """Test function to delete a prefix raises S3OperationError when delete returns errors"""
        mock_paginate = mocker.MagicMock()
        mock_paginate.paginate.return_value = [{"Contents": [{"Key": "path/to/file1"}]}]
        mock_s3_client = mocker.MagicMock()
        mock_s3_client.get_paginator.return_value = mock_paginate
        mock_s3_client.delete_objects.return_value = {
            "Errors": [{"Key": "path/to/file1", "Code": "AccessDenied", "Message": "Access Denied"}]
        }
        mocker.patch("aws_services.aws_modules.aws_s3_module.get_client", return_value=mock_s3_client)

        with pytest.raises(S3OperationError):
            AwsS3Module().delete_objects("bucket_name", "s3_prefix")

    def test_prefix_exists(self, mocker):
        """Test function to check if prefix exists in the s3 path"""
        mock_put_s3 = mocker.MagicMock()
        mock_put_s3.list_objects_v2.return_value = {"KeyCount": 1}
        mocker.patch("aws_services.aws_modules.aws_s3_module.get_client", return_value=mock_put_s3)

        assert AwsS3Module().prefix_exists("bucket_name", "s3_prefix")

    def test_prefix_not_exists(self, mocker):
        """Test function to check if prefix does not exist in the s3 path, returns 0 when no objects found"""
        mock_put_s3 = mocker.MagicMock()
        mock_put_s3.list_objects_v2.return_value = {"KeyCount": 0}
        mocker.patch("aws_services.aws_modules.aws_s3_module.get_client", return_value=mock_put_s3)

        assert AwsS3Module().prefix_exists("bucket_name", "s3_prefix") == False
