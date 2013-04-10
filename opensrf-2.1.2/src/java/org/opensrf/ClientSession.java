package org.opensrf;
import java.util.Date;
import java.util.List;
import java.util.Map;
import java.util.HashMap;
import java.util.ArrayList;
import java.util.Random;
import java.util.Arrays;

import org.opensrf.util.*;
import org.opensrf.net.xmpp.*;


/**
 * Models an OpenSRF client session.
 */
public class ClientSession extends Session {

    /** The remote service to communicate with */
    private String service;
    /** OpenSRF domain */
    private String domain;
    /** Router name */
    private String router;

    /** 
     * original remote node.  The current remote node will change based 
     * on server responses.  This is used to reset the remote node to 
     * its original state.
     */
    private String origRemoteNode;
    /** The next request id */
    private int nextId;
    /** The requests this session has sent */
    private Map<Integer, Request> requests;

    /**
     * Creates a new client session.  Initializes the 
     * @param service The remote service.
     */
    public ClientSession(String service) throws ConfigException {
        this(service, null);
    }

    /**
     * Creates a new client session.  Initializes the 
     * @param service The remote service.
     * @param locale The locale for this session.
     */
    public ClientSession(String service, String locale) throws ConfigException {
        this.service = service;
        if(locale != null) 
            setLocale(locale);

        /** generate the remote node string */
        domain = (String) Config.global().getFirst("/domain");
        router = Config.global().getString("/router_name");
        setRemoteNode(router + "@" + domain + "/" + service);
        origRemoteNode = getRemoteNode();


        /** create a random thread */
        long time = new Date().getTime();
        Random rand = new Random(time);
        setThread(rand.nextInt()+""+rand.nextInt()+""+time+Thread.currentThread().getId());

        nextId = 0;
        requests = new HashMap<Integer, Request>();
        cacheSession();
    }

    /**
     * Creates a new request to send to our remote service.
     * @param method The method API name
     * @param params The list of method parameters
     * @return The request object.
     */
    public Request request(String method, List<Object> params) throws SessionException {
        return request(new Request(this, nextId++, method, params));
    }

    /**
     * Creates a new request to send to our remote service.
     * @param method The method API name
     * @param params The list of method parameters
     * @return The request object.
     */
    public Request request(String method, Object[] params) throws SessionException {
        return request(new Request(this, nextId++, method, Arrays.asList(params)));
    }


    /**
     * Creates a new request to send to our remote service.
     * @param method The method API name
     * @return The request object.
     */
    public Request request(String method) throws SessionException {
        return request(new Request(this, nextId++, method));
    }


    private Request request(Request req) throws SessionException {
        if(getConnectState() != ConnectState.CONNECTED)
            resetRemoteId();
        requests.put(new Integer(req.getId()), req);
        req.send();
        return req;
    }


    /**
     * Resets the remoteNode to its original state.
     */
    public void resetRemoteId() {
        setRemoteNode(origRemoteNode);
    }


    /**
     * Pushes a response onto the result queue of the appropriate request.
     * @param msg The received RESULT Message
     */
    public void pushResponse(Message msg) {

        Request req = findRequest(msg.getId());
        if(req == null) {
            /** LOG that we've received a result to a non-existant request */
            System.err.println(msg.getId() +" has no corresponding request");
            return;
        }
        OSRFObject payload = (OSRFObject) msg.get("payload");

        /** build a result and push it onto the request's result queue */
        req.pushResponse(
            new Result( 
                payload.getString("status"), 
                payload.getInt("statusCode"),
                payload.get("content")
            )
        );
    }

    public Request findRequest(int reqId) {
        return requests.get(new Integer(reqId));
    }

    /**
     * Removes a request for this session's request set
     */
    public void cleanupRequest(int reqId) {
        requests.remove(new Integer(reqId));
    }

     public void setRequestComplete(int reqId) {
        Request req = findRequest(reqId);
        if(req == null) return;
        req.setComplete();
    }

    public static Object atomicRequest(String service, String method, Object[] params) throws MethodException {
        try {
            ClientSession session = new ClientSession(service);
            Request osrfRequest = session.request(method, params);
            Result result = osrfRequest.recv(600000);
            if(result.getStatusCode() != 200) 
                throw new MethodException( 
                    "Request "+service+":"+method+":"+" failed with status code " + result.getStatusCode());
            return result.getContent();
        } catch(Exception e) {
            throw new MethodException(e);
        }
    }
}

