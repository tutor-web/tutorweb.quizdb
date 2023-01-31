import logging

from zope.component import adapter
from zope.component.hooks import getSite
from plone.registry.interfaces import IRecordModifiedEvent
from Products.CMFCore.utils import getToolByName

from tutorweb.content.schema import ILectureSettings
from tutorweb.quizdb.sync.plone import \
    syncClassSubscriptions, removeClassSubscriptions, \
    syncPloneLecture, movePloneLecture, removePloneLecture, \
    syncPloneQuestions

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


def lectureModified(obj, event=None):
    portal_workflow = getToolByName(obj, "portal_workflow")
    logger.debug("lecture %s modified" % obj.id)

    # NB: This event includes question addition (but questions will not have content included)
    status = portal_workflow.getStatusOf("simple_publication_workflow", obj)
    if status and status.get("review_state", None) == "published":
        dbLec = syncPloneLecture(obj)
        syncPloneQuestions(dbLec, obj)
    else:
        removePloneLecture(obj)


def lectureMoved(obj, event=None):
    movePloneLecture(
        '/'.join(event.oldParent.getPhysicalPath() + (event.oldName,)),
        '/'.join(event.newParent.getPhysicalPath() + (event.newName,)),
    )

def lectureRemoved(obj, event=None):
    logger.debug("lecture %s removed" % obj.id)

    removePloneLecture(obj)


def tutorialModified(obj, event=None):
    logger.debug("tutorial %s modified" % obj.id)

    for l in _childrenOfType(obj, "tw_lecture"):
        # Make sure lectures inheriting settings are up-to-date
        syncPloneLecture(l)


def tutorialRemoved(obj, event=None):
    logger.debug("tutorial %s removed" % obj.id)

    for l in _childrenOfType(obj, "tw_lecture"):
        removePloneLecture(l)


def questionAdded(obj, event=None):
    logger.debug("question %s added" % obj.id)

    # NB: A question addition will fire
    #     -> questionAdded
    #     -> lectureModified
    #     -> questionModified
    # ... content only available at final step. So wait


def questionModified(obj, event=None):
    logger.debug("question %s modified" % obj.id)

    # NB: Ideally we just sync the questions, but need the dbLec anyway
    syncPloneQuestions(syncPloneLecture(obj.aq_parent), obj.aq_parent)


def questionRemoved(obj, event):
    logger.debug("question %s removed" % obj.id)

    # NB: Ideally we just sync the questions, but need the dbLec anyway
    if event.oldParent.portal_type == 'tw_lecture':
        syncPloneQuestions(syncPloneLecture(event.oldParent), event.oldParent)


@adapter(ILectureSettings, IRecordModifiedEvent)
def registryUpdated(obj, event=None):
    logger.debug("registry object updated")
    for l in _childrenOfType(getSite(), "tw_lecture"):
        # Make sure lectures inheriting settings are up-to-date
        syncPloneLecture(l)


def _childrenOfType(obj, portal_type):
    """Generate list of children objects with a portal type"""
    portal_catalog = getToolByName(obj, "portal_catalog")

    for b in portal_catalog.searchResults(portal_type=portal_type):
        yield b.getObject()
