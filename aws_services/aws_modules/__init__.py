"""
Initialization file to make the functions and classed in aws modules import able from the package level.
- This allows users to import functions and classes directly from aws_modules instead of having to specify the
individual module they are located in.

EXAMPLE:
    Instead of importing get_secret from aws_sm_module, users can import it directly from aws_modules.
This promotes cleaner and more convenient imports for users of the package.

"""
# aws_modules/__init__.py
from .aws_sm_module import get_secret
from .aws_s3_module import AwsS3Module, S3OperationError
from .aws_connections_module import get_client, get_region
from .aws_sts_module import assume_role, get_account_details, get_endpoint_url


__all__ = [
    "get_secret",
    "AwsS3Module",
    "S3OperationError",
    "get_client",
    "get_region",
    "assume_role",
    "get_account_details",
    "get_endpoint_url"
]
