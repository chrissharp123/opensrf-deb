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

import osrf.json, osrf.conf, osrf.log, osrf.net, osrf.net_obj, osrf.const
from osrf.const import OSRF_APP_SESSION_CONNECTED, \
    OSRF_APP_SESSION_CONNECTING, OSRF_APP_SESSION_DISCONNECTED, \
    OSRF_MESSAGE_TYPE_CONNECT, OSRF_MESSAGE_TYPE_DISCONNECT, \
    OSRF_MESSAGE_TYPE_REQUEST, OSRF_MESSAGE_TYPE_RESULT, OSRF_MESSAGE_TYPE_STATUS
import osrf.ex
import random, os, time, threading


# -----------------------------------------------------------------------
# Go ahead and register the common network objects
# -----------------------------------------------------------------------
osrf.net_obj.register_hint('osrfMessage', ['threadTrace', 'locale', 'type', 'payload', 'ingress'], 'hash')
osrf.net_obj.register_hint('osrfMethod', ['method', 'params'], 'hash')
osrf.net_obj.register_hint('osrfResult', ['status', 'statusCode', 'content'], 'hash')
osrf.net_obj.register_hint('osrfConnectStatus', ['status', 'statusCode'], 'hash')
osrf.net_obj.register_hint('osrfMethodException', ['status', 'statusCode'], 'hash')


class Session(object):
    """Abstract session superclass."""

    ''' Global cache of in-service sessions '''
    session_cache = {}
    current_ingress = 'opensrf';

    def __init__(self):
        # by default, we're connected to no one
        self.state = OSRF_APP_SESSION_DISCONNECTED
        self.remote_id = None
        self.locale = None
        self.thread = None
        self.service = None

    @staticmethod
    def find_or_create(thread):
        if thread in Session.session_cache:
            return Session.session_cache[thread]
        return ServerSession(thread)

    @staticmethod
    def ingress(ingress):
        if ingress:
            Session.current_ingress = ingress
        return Session.current_ingress

    def set_remote_id(self, remoteid):
        self.remote_id = remoteid
        osrf.log.log_internal("Setting request remote ID to %s" % self.remote_id)

    def wait(self, timeout=120):
        """Wait up to <timeout> seconds for data to arrive on the network"""
        osrf.log.log_internal("Session.wait(%d)" % timeout)
        handle = osrf.net.get_network_handle()
        return handle.recv(timeout)

    def send(self, omessages):
        """Sends an OpenSRF message"""
        if not isinstance(omessages, list):
            omessages = [omessages]

        for msg in omessages:
            msg.ingress(Session.current_ingress);
            
        net_msg = osrf.net.NetworkMessage(
            recipient      = self.remote_id,
            body    = osrf.json.to_json(omessages),
            thread = self.thread,
            locale = self.locale,
        )

        handle = osrf.net.get_network_handle()
        handle.send(net_msg)

    def cleanup(self):
        """Removes the session from the global session cache."""
        del Session.session_cache[self.thread]

class ClientSession(Session):
    """Client session object.  Use this to make server requests."""

    def __init__(self, service, locale='en-US'):
        
        # call superclass constructor
        Session.__init__(self)

        # the service we are sending requests to
        self.service = service

        # the locale we want requests to be returned in
        self.locale = locale

        # find the remote service handle <router>@<domain>/<service>
        domain = osrf.conf.get('domain', 0)
        router = osrf.conf.get('router_name')
        self.remote_id = "%s@%s/%s" % (router, domain, service)
        self.orig_remote_id = self.remote_id

        # generate a random message thread
        self.thread = "%s%s%s%s" % (os.getpid(), 
            str(random.randint(100,100000)), str(time.time()),threading.currentThread().getName().lower())

        # how many requests this session has taken part in
        self.next_id = 0 

        # cache of request objects 
        self.requests = {}

        # cache this session in the global session cache
        Session.session_cache[self.thread] = self

    def reset_request_timeout(self, rid):
        req = self.find_request(rid)
        if req:
            req.reset_timeout = True
            

    def request2(self, method, arr):
        """Creates a new request and sends the request to the server using a python array as the params."""
        return self.__request(method, arr)

    def request(self, method, *args):
        """Creates a new request and sends the request to the server using a variable argument list as params"""
        arr = list(args)
        return self.__request(method, arr)

    def __request(self, method, arr):
        """Builds the request object and sends it."""
        if self.state != OSRF_APP_SESSION_CONNECTED:
            self.reset_remote_id()

        osrf.log.make_xid()

        osrf.log.log_debug("Sending request %s -> %s " % (self.service, method))
        req = ClientRequest(self, self.next_id, method, arr, self.locale)
        self.requests[str(self.next_id)] = req
        self.next_id += 1
        req.send()
        return req


    def connect(self, timeout=10):
        """Connects to a remote service"""

        if self.state == OSRF_APP_SESSION_CONNECTED:
            return True
        self.state = OSRF_APP_SESSION_CONNECTING

        # construct and send a CONNECT message
        self.send(
            osrf.net_obj.NetworkObject.osrfMessage( 
                {   'threadTrace' : 0,
                    'type' : OSRF_MESSAGE_TYPE_CONNECT
                } 
            )
        )

        while timeout >= 0 and not self.state == OSRF_APP_SESSION_CONNECTED:
            start = time.time()
            self.wait(timeout)
            timeout -= time.time() - start
        
        if self.state != OSRF_APP_SESSION_CONNECTED:
            raise osrf.ex.OSRFServiceException("Unable to connect to " + self.service)
        
        return True

    def disconnect(self):
        """Disconnects from a remote service"""

        if self.state == OSRF_APP_SESSION_DISCONNECTED:
            return True

        self.send(
            osrf.net_obj.NetworkObject.osrfMessage( 
                {   'threadTrace' : 0,
                    'type' : OSRF_MESSAGE_TYPE_DISCONNECT
                } 
            )
        )

        self.state = OSRF_APP_SESSION_DISCONNECTED

    

    def reset_remote_id(self):
        """Recovers the original remote id"""
        self.remote_id = self.orig_remote_id
        osrf.log.log_internal("Resetting remote ID to %s" % self.remote_id)

    def push_response_queue(self, message):
        """Pushes the message payload onto the response queue 
            for the request associated with the message's ID."""
        osrf.log.log_debug("pushing %s" % message.payload())
        try:
            self.find_request(message.threadTrace()).push_response(message.payload())
        except Exception, e: 
            osrf.log.log_warn("pushing respond to non-existent request %s : %s" % (message.threadTrace(), e))

    def find_request(self, rid):
        """Returns the original request matching this message's threadTrace."""
        try:
            return self.requests[str(rid)]
        except KeyError:
            osrf.log.log_debug('find_request(): non-existent request %s' % str(rid))
            return None

    @staticmethod
    def atomic_request(service, method, *args):
        ses = ClientSession(service)
        req = ses.request2(method, list(args))
        resp = req.recv()
        data = None
        if resp:
            data = resp.content()
        req.cleanup()
        ses.cleanup()
        return data




class Request(object):
    def __init__(self, session, rid, method=None, params=[], locale='en-US'):
        self.session = session # my session handle
        self.rid     = rid # my unique request ID
        self.method = method # method name
        self.params = params # my method params
        self.locale = locale
        self.complete = False # is this request done?
        self.complete_time =  0 # time at which the request was completed


class ClientRequest(Request):
    """Represents a single OpenSRF request.
        A request is made and any resulting respones are 
        collected for the client."""

    def __init__(self, session, rid, method=None, params=[], locale='en-US'):
        Request.__init__(self, session, rid, method, params, locale)
        self.queue  = [] # response queue
        self.reset_timeout = False # resets the recv timeout?
        self.send_time = 0 # local time the request was put on the wire
        self.first_response_time = 0 # time it took for our first reponse to be received

    def send(self):
        """Sends a request message"""

        # construct the method object message with params and method name
        method = osrf.net_obj.NetworkObject.osrfMethod( {
            'method' : self.method,
            'params' : self.params
        } )

        # construct the osrf message with our method message embedded
        message = osrf.net_obj.NetworkObject.osrfMessage( {
            'threadTrace' : self.rid,
            'type' : OSRF_MESSAGE_TYPE_REQUEST,
            'payload' : method,
            'locale' : self.locale
        } )

        self.send_time = time.time()
        self.session.send(message)

    def recv(self, timeout=120):
        """ Waits up to <timeout> seconds for a response to this request.
        
            If a message is received in time, the response message is returned.
            Returns None otherwise."""

        self.session.wait(0)

        orig_timeout = timeout
        while not self.complete and (timeout >= 0 or orig_timeout < 0) and len(self.queue) == 0:

            s = time.time()
            self.session.wait(timeout)

            if self.reset_timeout:
                self.reset_timeout = False
                timeout = orig_timeout

            elif orig_timeout >= 0:
                timeout -= time.time() - s

        now = time.time()

        # -----------------------------------------------------------------
        # log some statistics 
        if len(self.queue) > 0:
            if not self.first_response_time:
                self.first_response_time = now
                osrf.log.log_debug("time elapsed before first response: %f" \
                    % (self.first_response_time - self.send_time))

        if self.complete:
            if not self.complete_time:
                self.complete_time = now
                osrf.log.log_debug("time elapsed before complete: %f" \
                    % (self.complete_time - self.send_time))
        # -----------------------------------------------------------------


        if len(self.queue) > 0:
            # we have a reponse, return it
            return self.queue.pop(0)

        return None

    def push_response(self, content):
        """Pushes a method response onto this requests response queue."""
        self.queue.append(content)

    def cleanup(self):
        """Cleans up request data from the cache. 

            Do this when you are done with a request to prevent "leaked" cache memory."""
        del self.session.requests[str(self.rid)]

    def set_complete(self):
        """Sets me as complete.  This means the server has sent a 'request complete' message"""
        self.complete = True


class ServerSession(Session):
    """Implements a server-side session"""

    def __init__(self, thread):
        Session.__init__(self)
        self.thread = thread
        self.callbacks = {}
        self.session_data = {}
        Session.session_cache[self.thread] = self

    def send_status(self, thread_trace, payload):
        self.send(
            osrf.net_obj.NetworkObject.osrfMessage( 
                {   'threadTrace' : thread_trace,
                    'type' : osrf.const.OSRF_MESSAGE_TYPE_STATUS,
                    'payload' : payload,
                    'locale' : self.locale
                } 
            )
        )

    def send_connect_ok(self, thread_trace):
        status_msg = osrf.net_obj.NetworkObject.osrfConnectStatus({   
            'status' : 'Connection Successful',
            'statusCode': osrf.const.OSRF_STATUS_OK
        })
        self.send_status(thread_trace, status_msg)

    def send_method_not_found(self, thread_trace, method_name):
        status_msg = osrf.net_obj.NetworkObject.osrfConnectStatus({   
            'status' : 'Method [%s] not found for %s' % (method_name, self.service),
            'statusCode': osrf.const.OSRF_STATUS_NOTFOUND
        })
        self.send_status(thread_trace, status_msg)


    def run_callback(self, type):
        if type in self.callbacks:
            self.callbacks[type](self)

    def register_callback(self, type, func):
        self.callbacks[type] = func

    def cleanup(self):
        Session.cleanup(self)
        self.run_callback('death')


class ServerRequest(Request):

    def __init__(self, session, rid, method, params=[]):
        Request.__init__(self, session, rid, method, params, session.locale)
        self.response_list = []

    def _build_response_msg(self, data):
        result = osrf.net_obj.NetworkObject.osrfResult({
            'content' :  data,
            'statusCode' : osrf.const.OSRF_STATUS_OK,
            'status' : 'OK'
        })

        return osrf.net_obj.NetworkObject.osrfMessage({
            'threadTrace' : self.rid,
            'type' : OSRF_MESSAGE_TYPE_RESULT,
            'payload' : result,
            'locale' : self.locale
        })

    def _build_complete_msg(self):

        status = osrf.net_obj.NetworkObject.osrfConnectStatus({   
            'threadTrace' : self.rid,
            'status' : 'Request Complete',
            'statusCode': osrf.const.OSRF_STATUS_COMPLETE
        })

        return osrf.net_obj.NetworkObject.osrfMessage({
            'threadTrace' : self.rid,
            'type' : OSRF_MESSAGE_TYPE_STATUS,
            'payload' : status,
            'locale' : self.locale
        })

    def respond(self, data):
        ''' For non-atomic calls, this sends a response directly back
            to the client.  For atomic calls, this pushes the response
            onto the response list '''
        osrf.log.log_internal("responding with %s" % str(data))
        if self.method.atomic:
            self.response_list.append(data)
        else:
            self.session.send(self._build_response_msg(data))

    def respond_complete(self, data):
        ''' Sends a complete message accompanied by the final result if applicable '''

        if self.complete: 
            return
        self.complete = True
        self.complete_time = time.time()

        if self.method.atomic:
            if data is not None:
                self.response_list.append(data) 
            self.session.send([
                self._build_response_msg(self.response_list),
                self._build_complete_msg(),
            ])

        elif data is not None:
            self.session.send([
                self._build_response_msg(data),
                self._build_complete_msg(),
            ])

        else:
            self.session.send(self._build_complete_msg())
            

class MultiSession(object):
    ''' Manages multiple requests.  With the current implementation, a 1 second 
        lag time before the first response is practically guaranteed.  Use 
        only for long running requests.

        Another approach would be a threaded version, but that would require
        build-up and breakdown of thread-specific xmpp connections somewhere.
        conection pooling? 
    '''
    class Container(object):
        def __init__(self, req):
            self.req = req
            self.id = None

    def __init__(self):
        self.complete = False
        self.reqs = []

    def request(self, service, method, *args):
        ses = ClientSession(service)
        cont = MultiSession.Container(ses.request(method, *args))
        cont.id = len(self.reqs)
        self.reqs.append(cont)

    def recv(self, timeout=120):
        ''' Returns a tuple of req_id, response '''
        duration = 0
        block_time = 1
        while True:
            for i in range(0, len(self.reqs)):
                cont = self.reqs[i]
                req = cont.req

                res = req.recv(0)
                if i == 0 and not res:
                    res = req.recv(block_time)

                if res: break

            if res: break

            duration += block_time
            if duration >= timeout:
                return None

        if req.complete:
            self.reqs.pop(self.reqs.index(cont))

        if len(self.reqs) == 0:
            self.complete = True

        return cont.id, res.content()

