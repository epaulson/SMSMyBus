import os
import wsgiref.handlers
import logging
import time
import re

from google.appengine.api import users
from google.appengine.api import memcache
from google.appengine.api.urlfetch import DownloadError
from google.appengine.api.labs import taskqueue
from google.appengine.api.labs.taskqueue import Task
from google.appengine.ext import webapp
from google.appengine.ext import db

from google.appengine.runtime import apiproxy_errors
import bus

FEED_VERSION = "1.0"

class StopRequestHandler(webapp.RequestHandler):
    
    def get(self, stopID=""):
	  
      # validate the request parameters
      if len(stopID) == 0:
        logging.info("Illegal web service call with stop %s" % stopID)
        xml = '<SMSMyBusResponse><status>-1</status></SMSMyBusResponse>'
        self.response.headers['Content-Type'] = 'text/xml'
        self.response.out.write(xml)
        return

      logging.info("looking for stop %s data" % stopID)
      xml = memcache.get(stopID)
      if xml is None:
        logging.info("cache MISS for stop %s data" % stopID)
        xml = '<SMSMyBusResponse><status>-1</status></SMSMyBusResponse>'
          
      self.response.headers['Content-Type'] = 'text/xml'
      self.response.out.write(xml)
        
## end StopRequestHandler
        
class GetAllStopLocationsHandler(webapp.RequestHandler):
    def get(self):
        logging.info("fetching the all-stop feed")
        
        xml = '<feed v="'+FEED_VERSION+'">'
        q = db.GqlQuery("SELECT * FROM StopLocation")
        stops = q.fetch(1000)
        curs = q.cursor()
        while stops is not None:
            for sl in stops:
                entry = "<stop><id>"+sl.stopID+"</id><intersection>"+sl.intersection+"</intersection><location>"+str(sl.location)+"</location></stop>"
                logging.info("stop... %s" % entry) 
                xml += entry
            stops = q.with_cursor(curs)
            curs = q.cursor()
        xml += "</feed>"
        self.response.headers['Content-Type'] = 'text/xml'
        self.response.out.write(xml)
        
## end GetAllStopLocationsHandler

class GetStopLocationHandler(webapp.RequestHandler):
    def get(self,stopID=""):
        logging.info("fetching the stop location feed for STOP %s" % stopID)
        
        xml = '<feed version="'+FEED_VERSION+'">'
        q = db.GqlQuery("SELECT * FROM StopLocation WHERE stopID = :1", stopID)
        stops = q.fetch(100)
        if stops is None:
            xml += "<status>Invalid stop ID specified</status>"
        else:
            for sl in stops:
                entry = "<stop><id>"+sl.stopID+"</id><intersection>"+sl.intersection.replace('&','/')+"</intersection><location>"+str(sl.location)+"</location></stop>"
                logging.info("stop... %s" % entry) 
                xml += entry
        
        xml += "</feed>"
        self.response.headers['Content-Type'] = 'text/xml'
        self.response.out.write(xml)
        
## end GetStopLocationHandler

class GetRouteStopsHandler(webapp.RequestHandler):
    def get(self,routeID=""):
        logging.info("fetching the stop location feed for ROUTE %s" % routeID)
        
        xml = '<feed version="'+FEED_VERSION+'"><route><id>'+routeID+'</id></route>'
        q = db.GqlQuery("SELECT * FROM RouteListing WHERE route = :1", routeID)
        stops = q.fetch(200)
        if stops is None:
            xml += "<status>Invalid route ID specified</status>"
        else:
            for s in stops:
                sl = s.stopLocation
                stopID = s.stopID
                direction = bus.getDirectionLabel(s.direction)
                
                if sl is None:
                    intersection = "unknown"
                    location = "unknown"
                else:
                    intersection = sl.intersection.replace('&','/')
                    location = str(sl.location)
                
                entry = "<stop><id>"+stopID+"</id><intersection>"+intersection+"</intersection><location>"+location+"</location><direction>"+direction+"</direction></stop>"
                logging.info("stop... %s" % entry) 
                xml += entry
        
        xml += "</feed>"
        self.response.headers['Content-Type'] = 'text/xml'
        self.response.out.write(xml)

## end GetRouteStopsHandler

        
class RouteRequestHandler(webapp.RequestHandler):
    
    def get(self, routeID="", stopID=""):
      
      # validate the request parameters
      if len(routeID) == 0 or len(stopID) == 0:
        logging.info("Illegal web service call with route (%s) and stop (%s)", (routeID, stopID))
        xml = '<SMSMyBusResponse><status>-1</status><reason>Illegal request parameters</reason></SMSMyBusResponse>'
        self.response.headers['Content-Type'] = 'text/xml'
        self.response.out.write(xml)
        return
    
      if len(routeID) == 1:
        routeID = "0" + routeID
      if len(stopID) == 3:
        stopID = "0" + stopID
    
      textBody = bus.findBusAtStop(routeID,stopID)

      if textBody.find('route') > -1:
          logging.error("bailing because we don't like the results... %s" % textBody)
          xml = '<SMSMyBusResponse><status>-1</status><reason>unable to locate this route</reason></SMSMyBusResponse>'
          self.response.headers['Content-Type'] = 'text/xml'
          self.response.out.write(xml)
          return

      xml = buildXMLResponse(textBody,routeID,stopID)                            
      
      self.response.headers['Content-Type'] = 'text/xml'
      self.response.out.write(xml)

## end RequestHandler




def postResults(sid, caller, textBody):
    
    stopID = caller.split(':')[1]
    if textBody.find('route') > -1 or textBody.find("isn't running") > -1:
        xml = '<SMSMyBusResponse><status>-1</status></SMSMyBusResponse>'
    else:
        xml = buildXMLResponse(textBody,'',stopID)
    
    # stuff the xml into the memcache using the stopID as the key
    worked = memcache.replace(stopID,xml)
    if worked == False:
        memcache.set(stopID,xml)    

    # @todo backup the memcache using the datastore
    
    return

## end postResults()
      
def buildXMLResponse(textBody, routeID, stopID):
    
      xml = ''
      if len(routeID) == 0:
          xml = '<SMSMyBusResponse><status>0</status><stop>' + stopID + '</stop>'
      else:
          xml = '<SMSMyBusResponse><status>0</status><route>' + routeID + '</route><stop>' + stopID + '</stop>'
                
      ltime = time.localtime()
      ltime_hour = ltime.tm_hour - 5
      ltime_hour += 24 if ltime_hour < 0 else 0
      ltime_min = ltime_hour * 60 + ltime.tm_min
      logging.debug("local time... %s (%s:%s) day minutes %s" % (ltime,ltime_hour,ltime.tm_min,ltime_min))
            
      logging.debug("textBody.... %s" % textBody)
      tlist = textBody.split('\n')
      
      tstamp_min = str(ltime.tm_min) if ltime.tm_min >= 10 else ("0"+str(ltime.tm_min))
      tstamp_hour = str(ltime_hour) if ltime_hour <=12 else str(ltime_hour-12)
      tstamp_label = "pm" if ltime_hour > 11 else "am"
      xml += '<timestamp>'+tstamp_hour+':'+tstamp_min+tstamp_label+'</timestamp>'
      
      for t in tlist:
          logging.debug("convert %s" % t)
          
          if t.find(':') > -1:
              # parse aggregated data
              if t.find('Route') > -1:
                  xml += '<route>'
                  m = re.search('Route\s+([0-9]+)\s+([0-9]+):([0-9]+)',t)
                  if m is None:
                      logging.error("no match for the route timing data!?!")
                      xml += '</route></SMSMyBusResponse>'
                      return
                  else:
                      logging.debug("found groupings %s" % m.group(0))
                      logging.debug("found routeID %s" % m.group(1))
                      logging.debug("found hour %s" % m.group(2))
                      logging.debug("found minutes %s" % m.group(3))
              
                  #logging.debug("results of RE... %s" % m.groups())
                  # pull out the routeID
                  routeID = m.group(1).lstrip('0')
                  xml += '<routeID>'+routeID+'</routeID>'
              
                  # pull out the qualifiers                  
                  direction = t.split('toward ')[1]
                  logging.debug("found direction %s" % direction)
                  
                  # pull out the time
                  btime_hour = arrival_hour = int(m.group(2))
                  btime_min = int(m.group(3))
                  
                  # determine whether we're in the morning or afternoon
                  # - adjust hours accordingly
                  # - determine meta data for human readable form
                  if t.find('pm') > -1:
                      btime_hour += 12 if btime_hour < 12 else 0
                      arrival_meta = 'pm'
                  else:
                      arrival_meta = 'am'
 
                  delta_in_min = (btime_hour*60 + btime_min) - ltime_min
                  xml += '<human>Route '+routeID+' toward '+direction+' arrives in '+str(delta_in_min)+' minutes</human>'
                  xml += '<minutes>'+str(delta_in_min)+'</minutes>'
                  xml += '<arrivalTime>'+str(arrival_hour)+':'+m.group(3)+arrival_meta+'</arrivalTime>'
                  xml += '<destination>'+direction+'</destination>'
                  
                  xml += '</route>'
              else:
                  # parse single route data
                  
                  # pull out the time
                  btime_hour = arrival_hour = int(t.split(':')[0])
                  if t.find('pm') > -1:
                      t = t.replace('pm','')
                      btime_hour += 12 if btime_hour < 12 else 0
                      arrival_meta = 'pm'
                  else:
                      t = t.replace('am','')
                      arrival_meta = 'am'
                       
                  btime_min = int(t.split(':')[1])
                  delta_in_min = (btime_hour*60 + btime_min) - ltime_min
                  xml += '<route>'
                  xml += '<routeID>'+routeID.lstrip('0')+'</routeID>'
                  xml += '<minutes>' + str(delta_in_min) + '</minutes>'
                  xml += '<arrivalTime>'+str(arrival_hour)+':'+str(btime_min)+arrival_meta+'</arrivalTime>'
                  xml += '<destination> </destination>'
                  xml += '</route>'
                  

              
      xml += '</SMSMyBusResponse>'
      return xml
  
## end buildXMLResponse()


def main():
  logging.getLogger().setLevel(logging.INFO)
  #
  # feed handles use the following model...
  #
  # http://www.smsmybus.com/feed/<feed-version>/<dev-key>/<routeID>/<stopID>/
  #
  application = webapp.WSGIApplication([('/api/allstops/', GetAllStopLocationsHandler),
                                        ('/api/stops/(.*)/', GetRouteStopsHandler),
                                        ('/api/location/(.*)/', GetStopLocationHandler),
                                        ],
                                       debug=True)
  wsgiref.handlers.CGIHandler().run(application)


if __name__ == '__main__':
  main()
