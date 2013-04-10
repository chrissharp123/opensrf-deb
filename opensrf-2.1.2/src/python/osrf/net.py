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
# -----------------------------------------------------------------------


import os, time, threading
from pyxmpp.jabber.client import JabberClient
from pyxmpp.message import Message
from pyxmpp.jid import JID
from socket import gethostname
import libxml2
import osrf.log, osrf.ex

THREAD_SESSIONS = {}

# - log jabber activity (for future reference)
#import logging
#logger=logging.getLogger()
#logger.addHandler(logging.StreamHandler())
#logger.addHandler(logging.FileHandler('j.log'))
#logger.setLevel(logging.DEBUG)




class XMPPNoRecipient(osrf.ex.OSRFException):
    ''' Raised when a message was sent to a non-existent recipient 
        The recipient is stored in the 'recipient' field on this object
    '''
    def __init__(self, recipient):
        osrf.ex.OSRFException.__init__(self, 'Error communicating with %s' % recipient)
        self.recipient = recipient

class XMPPNoConnection(osrf.ex.OSRFException):
    pass

def set_network_handle(handle):
    """ Sets the thread-specific network handle"""
    THREAD_SESSIONS[threading.currentThread().getName()] = handle

def get_network_handle():
    """ Returns the thread-specific network connection handle."""
    return THREAD_SESSIONS.get(threading.currentThread().getName())

def clear_network_handle():
    ''' Disconnects the thread-specific handle and discards it '''
    handle = THREAD_SESSIONS.get(threading.currentThread().getName())
    if handle:
        osrf.log.log_internal("clearing network handle %s" % handle.jid.as_utf8())
        del THREAD_SESSIONS[threading.currentThread().getName()]
        return handle

class NetworkMessage(object):
    """Network message

    attributes:

    sender - message sender
    recipient - message recipient
    body - the body of the message
    thread - the message thread
    locale - locale of the message
    osrf_xid - The logging transaction ID
    """

    def __init__(self, message=None, **args):
        if message:
            self.body = message.get_body()
            self.thread = message.get_thread()
            self.recipient = message.get_to()
            self.router_command = None
            self.router_class = None
            if message.xmlnode.hasProp('router_from') and \
                message.xmlnode.prop('router_from') != '':
                self.sender = message.xmlnode.prop('router_from')
            else:
                self.sender = message.get_from().as_utf8()
            if message.xmlnode.hasProp('osrf_xid'):
                self.xid = message.xmlnode.prop('osrf_xid')
            else:
                self.xid = ''
        else:
            self.sender = args.get('sender')
            self.recipient = args.get('recipient')
            self.body = args.get('body')
            self.thread = args.get('thread')
            self.router_command = args.get('router_command')
            self.router_class = args.get('router_class')
            self.xid = osrf.log.get_xid()

    @staticmethod
    def from_xml(xml):
        doc = libxml2.parseDoc(xml)
        msg = Message(doc.getRootElement())
        return NetworkMessage(msg)
        

    def make_xmpp_msg(self):
        ''' Creates a pyxmpp.message.Message and adds custom attributes '''

        msg = Message(None, self.sender, self.recipient, None, None, None, \
            self.body, self.thread)
        if self.router_command:
            msg.xmlnode.newProp('router_command', self.router_command)
        if self.router_class:
            msg.xmlnode.newProp('router_class', self.router_class)
        if self.xid:
            msg.xmlnode.newProp('osrf_xid', self.xid)
        return msg

    def to_xml(self):
        ''' Turns this message into XML '''
        return self.make_xmpp_msg().serialize()
        

class Network(JabberClient):
    def __init__(self, **args):
        self.isconnected = False

        # Create a unique jabber resource
        resource = args.get('resource') or 'python_client'
        resource += '_' + gethostname() + ':' + str(os.getpid()) + '_' + \
            threading.currentThread().getName().lower()
        self.jid = JID(args['username'], args['host'], resource)

        osrf.log.log_debug("initializing network with JID %s and host=%s, "
            "port=%s, username=%s" % (self.jid.as_utf8(), args['host'], \
            args['port'], args['username']))

        #initialize the superclass
        JabberClient.__init__(self, self.jid, args['password'], args['host'])
        self.queue = []

        self.receive_callback = None
        self.transport_error_msg = None

    def connect(self):
        JabberClient.connect(self)
        while not self.isconnected:
            stream = self.get_stream()
            act = stream.loop_iter(10)
            if not act:
                self.idle()

    def set_receive_callback(self, func):
        """The callback provided is called when a message is received.
        
            The only argument to the function is the received message. """
        self.receive_callback = func

    def session_started(self):
        osrf.log.log_info("Successfully connected to the opensrf network")
        self.authenticated()
        self.stream.set_message_handler("normal", self.message_received)
        self.stream.set_message_handler("error", self.error_received)
        self.isconnected = True

    def send(self, message):
        """Sends the provided network message."""
        osrf.log.log_internal("jabber sending to %s: %s" % (message.recipient, message.body))
        message.sender = self.jid.as_utf8()
        msg = message.make_xmpp_msg()
        self.stream.send(msg)

    def error_received(self, stanza):
        self.transport_error_msg = NetworkMessage(stanza)
        osrf.log.log_error("XMPP error message received from %s" % self.transport_error_msg.sender)
    
    def message_received(self, stanza):
        """Handler for received messages."""
        if stanza.get_type()=="headline":
            return True
        # check for errors
        osrf.log.log_internal("jabber received message from %s : %s" 
            % (stanza.get_from().as_utf8(), stanza.get_body()))
        self.queue.append(NetworkMessage(stanza))
        return True

    def stream_closed(self, stream):
        osrf.log.log_debug("XMPP Stream closing...")

    def stream_error(self, err):
        osrf.log.log_error("XMPP Stream error: condition: %s %r"
            % (err.get_condition().name,err.serialize()))

    def disconnected(self):
        osrf.log.log_internal('XMPP Disconnected')

    def recv(self, timeout=120):
        """Attempts to receive a message from the network.

        timeout - max number of seconds to wait for a message.  
        If a message is received in 'timeout' seconds, the message is passed to 
        the receive_callback is called and True is returned.  Otherwise, false is
        returned.
        """

        forever = False
        if timeout < 0:
            forever = True
            timeout = None

        if len(self.queue) == 0:
            while (forever or timeout >= 0) and len(self.queue) == 0:
                starttime = time.time()

                stream = self.get_stream()
                if not stream:
                   raise XMPPNoConnection('We lost our server connection...') 

                act = stream.loop_iter(timeout)
                endtime = time.time() - starttime

                if not forever:
                    timeout -= endtime

                osrf.log.log_internal("exiting stream loop after %s seconds. "
                    "act=%s, queue size=%d" % (str(endtime), act, len(self.queue)))

                if self.transport_error_msg:
                    msg = self.transport_error_msg
                    self.transport_error_msg = None
                    raise XMPPNoRecipient(msg.sender)

                if not act:
                    self.idle()

        # if we've acquired a message, handle it
        msg = None
        if len(self.queue) > 0:
            msg = self.queue.pop(0)
            if self.receive_callback:
                self.receive_callback(msg)

        return msg


    def flush_inbound_data(self):
        ''' Read all pending inbound messages from the socket and discard them '''
        cb = self.receive_callback
        self.receive_callback = None
        while self.recv(0): pass 
        self.receive_callback = cb




