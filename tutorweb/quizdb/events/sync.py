import logging

from tutorweb.quizdb.sync.tw_class import syncClassSubscriptions, removeClassSubscriptions

logger = logging.getLogger(__package__)

def classAdded(obj, event):
    logger.debug("Class %s added" % obj.id)
    syncClassSubscriptions(obj)

def classModified(obj, event):
    logger.debug("Class %s modified" % obj.id)
    syncClassSubscriptions(obj)

def classRemoved(obj, event):
    logger.debug("Class %s removed" % obj.id)
    removeClassSubscriptions('/'.join(event.oldParent.getPhysicalPath() + (event.oldName,)))
