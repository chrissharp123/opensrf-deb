# -----------------------------------------------------------------------
# Copyright (C) 2007  Georgia Public Library Service
# Bill Erickson <billserickson@gmail.com>
# 
# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2
# of the License, or (at your option) any later version.
# 
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
# 
#
# This modules define the exception classes.  In general, an 
# exception is little more than a name.
# -----------------------------------------------------------------------

class OSRFException(Exception):
    """Root class for exceptions."""
    def __init__(self, info=''):
        self.msg = '%s: %s' % (self.__class__.__name__, info)
    def __str__(self):
        return self.msg


class NetworkException(OSRFException):
    def __init__(self):
        OSRFException.__init__('Error communicating with the OpenSRF network')

class OSRFProtocolException(OSRFException):
    """Raised when something happens during opensrf network stack processing."""
    pass

class OSRFServiceException(OSRFException):
    """Raised when there was an error communicating with a remote service."""
    pass

class OSRFConfigException(OSRFException):
    """Invalid config option requested."""
    pass

class OSRFNetworkObjectException(OSRFException):
    pass
    
class OSRFJSONParseException(OSRFException):
    """Raised when a JSON parsing error occurs."""
    pass

