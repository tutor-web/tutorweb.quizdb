import json
import logging

from AccessControl import Unauthorized
from zope.publisher.interfaces import NotFound
from z3c.saconfig import Session

from sqlalchemy.orm.exc import NoResultFound

from Products.CMFCore.utils import getToolByName
from Products.Five.browser import BrowserView

from tutorweb.quizdb import db


class JSONBrowserView(BrowserView):
    def asDict(self):
        """Return dict to be turned into JSON"""
        raise NotImplementedError

    def __call__(self):
        try:
            out = self.asDict()
            self.request.response.setStatus(200)
            self.request.response.setHeader("Content-type", "application/json")
            return json.dumps(out)
        except Unauthorized, ex:
            self.request.response.setStatus(403)
            self.request.response.setHeader("Content-type", "application/json")
            return json.dumps(dict(
                error=ex.__class__.__name__,
                message=str(ex),
            ))
        except NotFound, ex:
            self.request.response.setStatus(404)
            self.request.response.setHeader("Content-type", "application/json")
            return json.dumps(dict(
                error=ex.__class__.__name__,
                message=str(ex),
            ))
        except Exception, ex:
            logging.error("Failed call: " + self.request['URL'])
            logging.exception(ex)
            self.request.response.setStatus(500)
            self.request.response.setHeader("Content-type", "application/json")
            return json.dumps(dict(
                error=ex.__class__.__name__,
                message=str(ex),
            ))

    def getCurrentStudent(self):
        """Try fetching the current student, create if they don't exist"""
        membership = self.context.portal_membership
        if membership.isAnonymousUser():
            raise Unauthorized
        mb = membership.getAuthenticatedMember()
        try:
            dbStudent = Session.query(db.Student) \
                .filter(db.Student.userName == mb.getUserName()).one()
        except NoResultFound:
            dbStudent = db.Student(userName=mb.getUserName())
            Session.add(dbStudent)
        dbStudent.eMail = mb.getProperty('email')
        Session.flush()
        return dbStudent

    def getLectureId(self):
        """Return database ID for the current lecture"""
        if self.context.portal_type != 'tw_lecture':
            # Could go up to find lecture at this point, but no need yet.
            raise NotImplementedError
        plonePath = '/'.join(self.context.getPhysicalPath())
        try:
            dbLec = Session.query(db.Lecture) \
                .filter(db.Lecture.plonePath == plonePath).one()
            return dbLec.lectureId
        except NoResultFound:
            dbLec = db.Lecture(plonePath=plonePath)
            Session.add(dbLec)
            Session.flush()
            return dbLec.lectureId

    ### Database operations (move these elsewhere?)

    def portalObject(self):
        """Get the portal object, caching it"""
        if getattr(self, '_portal', None) is None:
            pu = getToolByName(self.context, "portal_url")
            self._portal = pu.getPortalObject()
        return self._portal
