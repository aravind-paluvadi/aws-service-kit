# AWS Service Kit

## Overview
Utility modules to use for the AWS Service calls


## Language
- Python


## Project Structure
```
aws-service-kit/
      ├── aws_services/   # Main package for AWS services
      │     ├── aws_modules          # Subpackage for aws modules
      │     │     ├── __init__.py   # Initialize the aws_modules subpackage
      │     │     ├── aws_connections_module.py   # Module for AWS service connections and interactions
      │     │     ├── aws_s3_module.py     # Module for AWS S3 interactions
      │     │     ├── aws_sm_module.py    # Module for AWS Secrets Manager interactions
      │     │     └── aws_sts_module.py    # Module for AWS Security Token Service (STS) interactions
      │     │
      │     ├── cache_manager          # Subpackage for aws modules
      │     │     ├── __init__.py   # Initialize the cache_manager subpackage
      │     │     ├── base_cache_manager.py   # Base class for cache management
      │     │     ├── thread_cache_manager.py   # Module for thread-specific cache management
      │     │     └── ttl_thread_cache_manager.py    # Module for thread-specific cache management with time-to-live (TTL) functionality
      │     │
      │     ├── helper_utils   # Subpackage for helper utilities
      │     │     ├── __init__.py   # Initialize the helper_utils subpackage
      │     │     ├── utils.py      # General utility functions for AWS services
      │     │     └── variables.py  # Module for defining constants and variables used across AWS services
      │     │
      │     └── __init__.py    # Initialize the aws_services package
      │
      ├── tests/           # Directory for unit tests
      │     ├── unit_tests/   # Subdirectory for unit tests 
      │     │     ├── test_aws_modules/   # Subdirectory for testing aws modules
      │     │     │         ├── __init__.py     # Initialize the test_aws_modules subpackage
      │     │     │         ├── test_aws_connections_module.py     # Unit tests for AWS service connections and interactions
      │     │     │         ├── test_aws_s3_module.py     # Unit tests for AWS S3 interactions
      │     │     │         ├── test_aws_sm_module.py     # Unit tests for AWS Secrets Manager interactions
      │     │     │         └── test_aws_sts_module.py   # Unit tests for AWS Security Token Service (STS) interactions
      │     │     │
      │     │     └── __init__.py  # Initialize the unit_tests subpackage
      │     │
      │     └── __init__.py   # Initialize the tests package
      │   
      ├── .gitignore    # Git ignore file to exclude unnecessary files from version control
      ├── README.md     # README file for project documentation
      └── requirements.txt  # File to list project dependencies
```

## Usage:
```python
from aws_services.aws_modules.aws_connections_module import get_client
s3_client = get_client('s3')
```

## Benefits:
- **Standardized & Extensible Architecture:** 
    Provides a unified interface for *S3, STS, and Secrets Manager*, using a modular structure that ensures code 
    reusability and easy integration of additional AWS services.
- **Performance & Resilience:**
    Built-in *thread-safe caching* to reduce redundant API calls and latency, paired with robust *retry logic* to handle 
    transient network errors gracefully.
- **Production-Ready Utilities:**
    Integrated *standardized logging* and centralized *exception handling*, allowing for seamless debugging, monitoring, 
    and professional-grade error management.
- **Best Practices by Default:** 
    Simplifies complex AWS interactions—including secure credential management and rate-limit adherence—backed by a 
    comprehensive *unit-testing suite* for guaranteed reliability.

## Core Features: 
**Caching | Thread-Safety | Retry Logic | Structured Logging | Unit Tested**

## Conclusion:
The AWS Service Kit abstracts the complexity of AWS integrations, allowing you to focus on core business logic. 
By combining standardized service wrappers with built-in resilience and performance optimizations, it provides a 
production-ready foundation for building scalable, maintainable, and robust cloud applications.
