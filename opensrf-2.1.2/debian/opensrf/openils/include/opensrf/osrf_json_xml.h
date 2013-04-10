#ifndef OSRF_JSON_XML_H
#define OSRF_JSON_XML_H

#ifdef OSRF_JSON_ENABLE_XML_UTILS

#include <stdio.h>
#include <string.h>
#include <libxml/globals.h>
#include <libxml/xmlerror.h>
#include <libxml/parser.h>
#include <libxml/tree.h>
#include <libxml/xmlmemory.h>

#include <opensrf/osrf_json.h>
#include <opensrf/utils.h>
#include <opensrf/osrf_list.h>

#ifdef __cplusplus
extern "C" {
#endif

/**
 *	Generates an XML representation of a JSON object */
char* jsonObjectToXML( const jsonObject*);


/*
 * Builds a JSON object from the provided XML 
 */
jsonObject* jsonXMLToJSONObject(const char* xml);

#ifdef __cplusplus
}
#endif

#endif
#endif
