"""
File: errors.py
Purpose: Custom exception hierarchy for MessageFacility UDP message spy.
Category: Utility
Author: artdaq team
Depends: None
Exports: MsgSpyError, SocketError, ParseError
Complexity: Low | Lines: 8
"""

class MsgSpyError(Exception):
    pass

class SocketError(MsgSpyError):
    pass

class ParseError(MsgSpyError):
    pass