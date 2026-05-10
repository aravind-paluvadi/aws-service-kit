"""Test file for AWS STS Module"""
# Standard Imports
from datetime import datetime, timezone

# PIP Imports
from pytest import mark, raises
from botocore.exceptions import ClientError


# Local Imports
from aws_services.aws_modules.aws_sts_module import assume_role, get_endpoint_url, get_account_details
from aws_services.helper_utils.variables import DEFAULT_REGION


_VALID_ROLE_ARN = "arn:aws:iam::123456789012:role/role_name"
_MOCK_CREDENTIALS = {
    "AccessKeyId": "AKIAIOSFODNN7EXAMPLE",
    "SecretAccessKey": "secret",
    "SessionToken": "token",
    "Expiration": datetime(2099, 1, 1, tzinfo=timezone.utc)
}


class TestAWSSTS:
    """Tests class for AWS STS Module"""

    # ---------------------- get_endpoint_url -------------------------------------

    def test_get_endpoint_url_with_region(self):
        """Tests get_endpoint_url returns correct URL for a given region"""
        assert get_endpoint_url(aws_region="us-west-2") == "https://sts.us-west-2.amazonaws.com"

    def test_get_endpoint_url_default_region(self):
        """Tests get_endpoint_url falls back to detected region"""
        endpoint_url = get_endpoint_url()
        assert endpoint_url.startswith("https://sts.")
        assert endpoint_url.endswith(".amazonaws.com")

    def test_get_ednpoint_url_raises_on_invalid_region(self):
        """Tests get_ednpoint_url raises ValueError on invalid region"""
        with raises(ValueError):
            get_endpoint_url(aws_region="INVALID_REGION")

    # ---------------------- assume_role -------------------------------------

    def test_assume_role(self, mocker):
        """Tests assume role function"""
        # Test with valid role arn
        mock_sts = mocker.MagicMock()
        mock_sts.assume_role.return_value = {"Credentials": _MOCK_CREDENTIALS}
        mock_get_client = mocker.patch("aws_services.aws_modules.aws_sts_module.get_client", return_value=mock_sts)
        mocker.patch(
            "aws_services.aws_modules.aws_sts_module._STS_CACHE.get_or_create_expiry",
            side_effect=lambda key, factory: factory()[0]
        )

        credentials = assume_role(role_arn=_VALID_ROLE_ARN)
        assert credentials["AccessKeyId"] == "AKIAIOSFODNN7EXAMPLE"
        mock_get_client.assert_called_once_with("sts", endpoint_url=mocker.ANY ,region=DEFAULT_REGION)

    @mark.parametrize(
        "region", ["us-EAST-1", "us_east_1", "invalid"],
        ids=["uppercase", "underscores", "no_digits"]
    )
    def test_assume_role_raises_on_invalid_region(self, region):
        """Tests assume_role raises ValueError on invalid region"""
        with raises(ValueError):
            assume_role(_VALID_ROLE_ARN, region_name=region)

    def test_assume_role_raises_on_invalid_arn(self):
        """Tests assume_role raises ValueError on invalid arn"""
        with raises(ValueError):
            assume_role(role_arn="invalid_role_arn")

    def test_assume_role_error_scenario(self, mocker):
        """Tests assume_role error scenario"""
        # Test with valid role arn but client error
        mock_sts = mocker.MagicMock()
        mock_sts.assume_role.side_effect = ClientError(
            {"Error": {"Code": "AccessDenied", "Message": "Access Denied"}},
            "AssumeRole"
        )
        mocker.patch("aws_services.aws_modules.aws_sts_module.get_client", return_value=mock_sts)
        mocker.patch(
            "aws_services.aws_modules.aws_sts_module._STS_CACHE.get_or_create_expiry",
            side_effect=lambda key, factory: factory()[0]
        )

        with raises(ClientError):
            assume_role(role_arn=_VALID_ROLE_ARN)

    # ---------------------- get_account_details -------------------------------------

    @mark.parametrize("region", [
        "us-EAST-1", "not-a-region"
    ], ids=["uppercase", "invalid_format"])
    def test_get_account_details_raises_on_invalid_region(self, region):
        """Tests get_account_details raises ValueError on invalid region"""
        with raises(ValueError):
            get_account_details(region_name=region)

    def test_get_account_details(self, mocker):
        """Tests get_account_details returns correct account details"""
        mock_sts = mocker.MagicMock()
        mock_sts.get_caller_identity.return_value = {"Account": "123456789012"}
        mock_get_client = mocker.patch("aws_services.aws_modules.aws_sts_module.get_client", return_value=mock_sts)
        mocker.patch(
            "aws_services.aws_modules.aws_sts_module._ACCOUNT_ID_CACHE.get_or_create_expiry",
            side_effect=lambda key, factory: factory()[0]
        )

        account_id = get_account_details()
        assert account_id == "123456789012"
        mock_get_client.assert_called_once_with("sts", endpoint_url=mocker.ANY ,region=DEFAULT_REGION)
