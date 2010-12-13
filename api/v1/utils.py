import os
import logging
import time
import re

from google.appengine.api import users
from google.appengine.api import memcache
from google.appengine.ext import db
        

def validateDevKey(devKey):
    
    # special dev key
    if devKey == 'nomar': 
        logging.info("found the magic dev key...")
        return 1
    
    if devKey is None:
        return None
   
    storeKey = memcache.get(dev)
    if storeKey is None:
        q = db.GqlQuery("SELECT __key__ FROM DeveloperKeys WHERE developerKey = :1", devKey)
        storeKey = q.get()
        if storeKey is None:
            return None
        else:
            memcache.put(devKey, storeKey)
    
    return storeKey
    
## end validateDevKey()

def inthepast(time):
    
    if computeCountdownMinutes(time) < 0:
        return True
    else:
        return False
    
## end inthepast


def getLocalTimestamp():
    
    # get the local, server time
    ltime = time.localtime()
    ltime_hour = ltime.tm_hour - 5  # convert to madison time
    ltime_hour += 24 if ltime_hour < 0 else 0
    ltime_min = ltime_hour * 60 + ltime.tm_min
    logging.debug("local time... %s (%s:%s) day minutes %s" % (ltime,ltime_hour,ltime.tm_min,ltime_min))
    
    tstamp_min = str(ltime.tm_min) if ltime.tm_min >= 10 else ("0"+str(ltime.tm_min))
    tstamp_hour = str(ltime_hour) if ltime_hour <=12 else str(ltime_hour-12)
    tstamp_label = "pm" if ltime_hour > 11 else "am"

    return(tstamp_hour+':'+tstamp_min+tstamp_label)

## end getLocalTimestamp()

def computeCountdownMinutes(arrivalTime):

    # compute current time in minutes
    ltime = time.localtime()
    ltime_hour = ltime.tm_hour - 5
    ltime_hour += 24 if ltime_hour < 0 else 0
    ltime_min = ltime_hour * 60 + ltime.tm_min
    #logging.info("local time: %s hours %s minutes", (ltime_hour,ltime_min))
    
    # pull out the time
    m = re.search('(\d+):(\d+)\s(.*?)',arrivalTime)
    btime_hour = arrival_hour = int(m.group(1))
    btime_min = int(m.group(2))
    #logging.info("computing countdown with %s - %s hours %s minutes", (arrivalTime,btime_hour,btime_min))
                 
    # determine whether we're in the morning or afternoon
    # and adjust hours accordingly
    if arrivalTime.find('PM') > -1:
        btime_hour += 12 if btime_hour < 12 else 0
 
    delta_in_min = (btime_hour*60 + btime_min) - ltime_min
    return(delta_in_min)

## end computeCountdownMinutes()
