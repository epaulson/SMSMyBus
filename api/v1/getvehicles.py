import os
import wsgiref.handlers
import logging
import re

from django.utils import simplejson

from google.appengine.ext import webapp
from google.appengine.api import urlfetch

from google.appengine.ext.webapp.util import run_wsgi_app

from api.v1 import utils

class MainHandler(webapp.RequestHandler):
    
    def get(self):
      
      # validate the request parameters
      devStoreKey = validateRequest(self.request)
      if devStoreKey is None:
          logging.debug("unable to validate the request parameters")
          self.response.headers['Content-Type'] = 'application/javascript'
          self.response.out.write(simplejson.dumps(utils.buildErrorResponse('-1','Illegal request parameters')))
          return
      
      # snare the inputs
      routeID = self.request.get('routeID')
      logging.debug('getvehicles request parameters...  routeID %s' % routeID)
      
      if utils.afterHours() is True:
          # don't run these jobs during "off" hours
	      json_response = utils.buildErrorResponse('-1','The Metro service is not currently running')
      elif routeID is not '':
          json_response = routeRequest(routeID)
          utils.recordDeveloperRequest(devStoreKey,utils.GETVEHICLES,self.request.query_string,self.request.remote_addr);
      else:
          logging.error("API: invalid request")
          json_response = utils.buildErrorResponse('-1','Invalid Request parameters. Did you forget to include a routeID?')
          utils.recordDeveloperRequest(devStoreKey,utils.GETVEHICLES,self.request.query_string,self.request.remote_addr,'illegal query string combination');

      #logging.debug('API: json response %s' % json_response);    
      # encapsulate response in json
      callback = self.request.get('callback')
      if callback is not '':
          self.response.headers['Content-Type'] = 'application/javascript'
          self.response.headers['Access-Control-Allow-Origin'] = '*'
          self.response.headers['Access-Control-Allow-Methods'] = 'GET'
          response = callback + '(' + simplejson.dumps(json_response) + ');'
      else:
          self.response.headers['Content-Type'] = 'application/json'
          response = simplejson.dumps(json_response)
      
      self.response.out.write(response)

    def post(self):
        self.response.headers['Content-Type'] = 'application/javascript'
        self.response.out.write(simplejson.dumps(utils.buildErrorResponse('-1','The API does not support POST requests')))
        return

## end MainHandler

VEHICLE_URL_BASE = 'http://webwatch.cityofmadison.com/webwatch/UpdateWebMap.aspx?u='
def routeRequest(routeID):
    loop = 0
    done = False
    result = None
    while not done and loop < 3:
        try:
          url = VEHICLE_URL_BASE + routeID
          result = urlfetch.fetch(url)
          done = True;
        except urlfetch.DownloadError:
          logging.error("Error loading page (%s)... sleeping" % loop)
          if result:
            logging.debug("Error status: %s" % result.status_code)
            logging.debug("Error header: %s" % result.headers)
            logging.debug("Error content: %s" % result.content)
          time.sleep(6)
          loop = loop+1
           
    if result is None or result.status_code != 200:
        logging.error("Exiting early: error fetching URL: " + result.status_code)
        return utils.buildErrorResponse('-1','Error reading live Metro feed')
    
    dataArray = result.content.split('*')
    logging.debug('timestamp is %s' % dataArray[0])
    timestamp = dataArray[0]
    
    vehicles = dataArray[2].split(';')
    results = dict({'status' : 0,
                    'routeID' : routeID,
                    'count' : len(vehicles)-1, 
                    'timestamp' : timestamp, 
                    'vehicles' : list()
                    })
    for v in vehicles:
        if v == vehicles[-1]:
            break
        location = v.split('|')
        next = location[3].split('<br>')
        spot = dict({'lat':location[0],
                     'lon':location[1],
                     'direction':re.sub('<[^>]*>', '', next[0]),
                     'vehicleID':next[1].split(':')[1].lstrip(),
                     'nextStop':next[2].split(':')[1].lstrip()
                   })
        results['vehicles'].append(spot)
    
    return results   

## routeRequest()


def validateRequest(request):
    
    # validate the key
    devStoreKey = utils.validateDevKey(request.get('key'))
    if devStoreKey is None:
        utils.recordDeveloperRequest(None,utils.GETSTOPS,request.query_string,request.remote_addr,'illegal developer key specified');
        return None
    
    routeID = request.get('routeID')
    if routeID is None or routeID is '':
        utils.recordDeveloperRequest(devStoreKey,type,request.query_string,request.remote_addr,'a routeID must be included');
        return None

    return devStoreKey

## end validateRequest()

application = webapp.WSGIApplication([('/api/v1/getvehicles', MainHandler),
                                      ],
                                     debug=True)

def main():
  logging.getLogger().setLevel(logging.DEBUG)
  run_wsgi_app(application)
  #wsgiref.handlers.CGIHandler().run(application)


if __name__ == '__main__':
  main()
