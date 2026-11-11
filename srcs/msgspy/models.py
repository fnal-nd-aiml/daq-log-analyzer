"""
File: models.py
Purpose: Pydantic model for parsed MessageFacility UDP messages.
Category: Utility
Author: artdaq team
Depends: pydantic
Exports: MFMessage
Complexity: Low | Lines: 14
"""

from pydantic import BaseModel, Field

class MFMessage(BaseModel):
    raw: bytes = Field(description='Original raw datagram bytes')
    severity: str = Field(default='', description='Message severity level')
    category: str = Field(default='', description='Message category')
    hostname: str = Field(default='', description='Originating hostname')
    application: str = Field(default='', description='Application name')
    pid: int = Field(default=0, description='Process ID')
    timestamp: str = Field(default='', description='Timestamp string')
    module: str = Field(default='', description='Source module name')
    filename: str = Field(default='', description='Source filename')
    line_number: int = Field(default=0, description='Source line number')
    message: str = Field(default='', description='Message body')