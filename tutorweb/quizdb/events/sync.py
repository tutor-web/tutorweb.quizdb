import logging

from tutorweb.quizdb.sync.plone import syncClassSubscriptions, removeClassSubscriptions, syncPloneLecture, syncPloneQuestions

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


def lectureModified(obj, event):
    portal_workflow = getToolByName(obj, "portal_workflow")
    logger.debug("lecture %s modified" % obj.id)

    status = portal_workflow.getStatusOf("plone_workflow", obj)
    if status and status.get("review_state", None) == "published":
        syncPloneLecture(obj)
        syncPloneQuestions(obj)
    else:
        removePloneLecture(obj)
    #TODO: Adding questions should also trigger lectureModified.


def lectureRemoved(obj, event):
    logger.debug("lecture %s removed" % obj.id)

    removePloneLecture(obj)


def tutorialModified(obj, event):
    logger.debug("tutorial %s modified" % obj.id)

    for l in _childrenOfType(obj, "tw_lecture"):
        # Make sure lectures inheriting settings are up-to-date
        syncPloneLecture(obj)


def tutorialModified(obj, event):
    logger.debug("tutorial %s modified" % obj.id)

    for l in _childrenOfType(obj, "tw_lecture"):
        removePloneLecture(obj)


def registryUpdated(obj, event):
    logger.debug("registry object %s updated" % obj.id)
    for l in _childrenOfType(portal, "tw_lecture"):
        # Make sure lectures inheriting settings are up-to-date
        syncPloneLecture(l)



def _childrenOfType(obj, portal_type):
    """Generate list of children objects with a portal type"""
    portal_catalog = getToolByName(obj, "portal_catalog")

    for b in portal_catalog.searchResults(portal_type=portal_type)
        yield b.getObject()
