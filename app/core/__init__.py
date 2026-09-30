"""Application core module.

This module provides core functionality for the application including
configuration management and logging setup.
"""

import logging

from app.core.config import Config
from app.core.logger import setup_logger


def get_config() -> Config:
  """Get application configuration instance.

  Returns:
      Config: Application configuration instance.
  """
  return Config()


def get_logger() -> logging.Logger:
  """Get application logger instance.

  Returns:
      logging.Logger: Configured logger for the application.
  """
  return setup_logger()


# Global instances
config = get_config()
default_logger = get_logger()
