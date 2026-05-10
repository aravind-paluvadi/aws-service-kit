"""Test file for AWS Secrets Manager Module"""
# PIP Imports
from pytest import mark, raises
from botocore.exceptions import ClientError


# Local Imports
from aws_services.aws_modules.aws_sm_module import get_secret, _get_cache
from aws_services.helper_utils.variables import DEFAULT_DURATION_SECONDS, MAX_SECRETS_PER_REGION, DEFAULT_REGION


class TestAWSSMModule:
    """Tests class for AWS Secrets Manager Module"""

    @mark.parametrize("inputs", [
        {"secret_name": ""},
        {"secret_name": "test_secret", "region_name": ""}
    ], ids=["empty_secret_name", "empty_region_name"])
    def test_get_secret_raises_on_empty_name(self, inputs):
        """Tests get_secret raises on empty secret name"""
        with raises(ValueError):
            get_secret(**inputs)

    def test_get_secret(self, mocker):
        """Tests get_secret returns secret value from AWS Secrets Manager"""
        mock_cache = mocker.MagicMock()
        mock_cache.get_secret_string.return_value = {"secret_string": "secret_value"}
        mock_get_cache = mocker.patch("aws_services.aws_modules.aws_sm_module._get_cache", return_value=mock_cache)

        result = get_secret("test_secret")

        assert result == {"secret_string": "secret_value"}
        mock_cache.get_secret_string.assert_called_once_with("test_secret")
        mock_get_cache.assert_called_once_with(DEFAULT_REGION, DEFAULT_DURATION_SECONDS)

    def test_get_secret_returns_raw_string_passes_region_and_ttl(self, mocker):
        """Tests get_secret returns raw string and passes region and ttl to cache"""
        mock_cache = mocker.MagicMock()
        mock_cache.get_secret_string.return_value = "plain_string_secret"
        mock_get_cache = mocker.patch("aws_services.aws_modules.aws_sm_module._get_cache", return_value=mock_cache)

        result = get_secret("test_secret", region_name="us-west-2", ttl=1800)

        assert result == "plain_string_secret"
        mock_cache.get_secret_string.assert_called_once_with("test_secret")
        mock_get_cache.assert_called_once_with("us-west-2", 1800)

    def test_get_cache(self, mocker):
        """Tests get_cache returns cache success scenario"""
        mocker.patch(
            "aws_services.aws_modules.aws_sm_module._CACHE_BY_REGION.get_or_create",
            side_effect=lambda key, factory: factory()
        )
        mock_get_client = mocker.patch("aws_services.aws_modules.aws_sm_module.get_client", return_value=mocker.MagicMock())
        mock_config = mocker.patch("aws_services.aws_modules.aws_sm_module.SecretCacheConfig", return_value=mocker.MagicMock())
        mocker.patch("aws_services.aws_modules.aws_sm_module.SecretCache", return_value="Mock Object")

        secret = _get_cache("us-west-2")
        assert secret == "Mock Object"
        mock_get_client.assert_called_once_with("secretsmanager", region="us-west-2")
        mock_config.assert_called_once_with(
            secret_refresh_interval=DEFAULT_DURATION_SECONDS,
            max_cache_size=MAX_SECRETS_PER_REGION
        )

    def test_get_secret_raises_client_error(self, mocker):
        """Test get_secret re-raises client error from secrets manager"""
        mock_cache = mocker.MagicMock()
        mock_cache.get_secret_string.side_effect = ClientError(
            {"Error": {"Code": "ResourceNotFoundException", "Message": "Secret not found"}},
            "GetSecretValue"
        )
        mocker.patch("aws_services.aws_modules.aws_sm_module._get_cache", return_value=mock_cache)

        with raises(ClientError):
            get_secret("non_existent_secret")
