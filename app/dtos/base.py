"""Base DTO models module.

This module provides base classes for data transfer objects (DTOs)
used throughout the application for API request and response serialization.
"""

from pydantic import BaseModel, ConfigDict


class BaseSerializerModel(BaseModel):
  """Base serializer model with common configuration.

  Provides common configuration for all DTO models including
  automatic attribute mapping from ORM models.
  """

  model_config = ConfigDict(from_attributes=True)
