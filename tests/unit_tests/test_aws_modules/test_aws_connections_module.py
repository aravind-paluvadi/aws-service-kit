"""Test file for AWS Connections Module"""
# PIP Imports
import pytest
from botocore.exceptions import NoCredentialsError

# Local Imports
from aws_services.aws_modules.aws_connections_module import get_region, get_client, _CLIENT_CACHE


class TestAWSConnectionsModule:
    """Tests class for AWS Connections Module"""

    def test_get_region(self, mocker):
        """Tests get_region function returns region from session"""
        get_region.cache_clear()
        mock_region = mocker.MagicMock()
        mock_region.region_name = "us-west-2"
        mocker.patch("aws_services.aws_modules.aws_connections_module.Session", return_value=mock_region)

        result = get_region()
        assert result == "us-west-2"
        get_region.cache_clear()

    def test_get_region_no_region(self, mocker):
        """Tests get_region function falls back to default region if no region configured"""
        get_region.cache_clear()
        mock_region = mocker.MagicMock()
        mock_region.region_name = None
        mocker.patch("aws_services.aws_modules.aws_connections_module.Session", return_value=mock_region)

        result = get_region()
        assert result == "us-east-1"
        get_region.cache_clear()

    def test_get_client(self, mocker):
        """Tests get_client function returns a boto3 client"""
        mock_client = mocker.MagicMock()
        mock_session = mocker.MagicMock()
        mock_session.client.return_value = mock_client
        mocker.patch("aws_services.aws_modules.aws_connections_module.Session", return_value=mock_session)
        _CLIENT_CACHE.clear()

        result = get_client("sts", use_cache=False)

        assert result is mock_client
        mock_session.client.assert_called_once()

    def test_get_client_uses_cache(self, mocker):
        """Tests get_client function returns cached client on second call"""
        mock_client = mocker.MagicMock()
        mock_session = mocker.MagicMock()
        mock_session.client.return_value = mock_client
        mocker.patch("aws_services.aws_modules.aws_connections_module.Session", return_value=mock_session)
        _CLIENT_CACHE.clear()

        result_1 = get_client("secretsmanager")
        result_2 = get_client("secretsmanager")

        assert result_1 is result_2
        assert result_1 is mock_client
        mock_session.client.assert_called_once()
        _CLIENT_CACHE.clear()

    def test_get_client_no_cache_with_session_token(self, mocker):
        """Tests get_client function does not cache client when session token is provided"""
        mock_session = mocker.MagicMock()
        mock_session.client.return_value = mocker.MagicMock()
        mocker.patch("aws_services.aws_modules.aws_connections_module.Session", return_value=mock_session)

        get_client("s3", aws_session_token="fake-token")
        get_client("s3", aws_session_token="fake-token")

        assert mock_session.client.call_count == 2

    def test_get_client_raises_no_credentials(self, mocker):
        """Tests get_client function raises NoCredentialsError when credentials are missing"""
        mock_session = mocker.MagicMock()
        mock_session.client.side_effect = NoCredentialsError()
        mocker.patch("aws_services.aws_modules.aws_connections_module.Session", return_value=mock_session)

        with pytest.raises(NoCredentialsError):
            get_client("ec2", use_cache=False)

    def test_get_client_with_custom_region(self, mocker):
        """Tests get_client function creates client with custom region to Session client"""
        mock_client = mocker.MagicMock()
        mock_session = mocker.MagicMock()
        mock_session.client.return_value = mock_client
        mocker.patch("aws_services.aws_modules.aws_connections_module.Session", return_value=mock_session)
        _CLIENT_CACHE.clear()

        get_client("lambda", use_cache=False, region_name="eu-west-1")

        mock_session.client.assert_called_once_with(
            "lambda",
            region_name="eu-west-1",
            endpoint_url="",
            config=mocker.ANY,
            aws_access_key_id=None,
            aws_secret_access_key=None,
            aws_session_token=None
        )
