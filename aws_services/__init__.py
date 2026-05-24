# aws_services/__init__.py
"""AWS Services Package"""
import logging

# Standard library author pattern - Silence "no handler found" warnings for users who import
# this package but don't configure logging.
logging.getLogger(__name__).addHandler(logging.NullHandler())
