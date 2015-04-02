import json
import logging
import socket

from AccessControl import Unauthorized
from Globals import DevelopmentMode
from zope.publisher.interfaces import NotFound
from z3c.saconfig import Session
from zExceptions import Redirect, BadRequest

from plone.memoize import view

from sqlalchemy.orm.exc import NoResultFound

from Products.CMFCore.utils import getToolByName
from Products.Five.browser import BrowserView

from tutorweb.quizdb import db


class BrowserViewHelpers(object):
    def getCurrentStudent(self):
        """Try fetching the current student, create if they don't exist"""
        membership = self.context.portal_membership
        if membership.isAnonymousUser():
            raise Unauthorized('You are not logged in')
        mb = membership.getAuthenticatedMember()
        if not mb.getProperty('accept', False):
            raise Redirect, getToolByName(self.context, "portal_url")() + \
                            "/@@personal-information"
        if hasattr(self, 'dbStudent') and self.dbStudent.userName == mb.getUserName():
            return self.dbStudent

        try:
            dbHost = (Session.query(db.Host)
                .filter(db.Host.fqdn == socket.getfqdn())
                .one())
        except NoResultFound:
            dbHost = db.Host(fqdn=socket.getfqdn())
            Session.add(dbHost)
            Session.flush()

        try:
            dbStudent = Session.query(db.Student) \
                .filter(db.Student.hostId == dbHost.hostId) \
                .filter(db.Student.userName == mb.getUserName()).one()
        except NoResultFound:
            dbStudent = db.Student(
                userName=mb.getUserName(),
                hostId=dbHost.hostId,
            )
            Session.add(dbStudent)
        dbStudent.eMail = mb.getProperty('email')
        Session.flush()
        self.dbStudent = dbStudent
        return dbStudent

    @view.memoize
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

    def texToHTML(self, f):
        """Encode TeX in f into HTML"""
        if not f:
            return f
        if getattr(self, '_pt', None) is None:
            self._pt = getToolByName(self.context, 'portal_transforms')
        return self._pt.convertTo(
            'text/html',
            f.encode('utf-8'),
            mimetype='text/x-tex',
            encoding='utf-8',
        ).getData().decode('utf-8')

    ### Database operations (move these elsewhere?)

    def portalObject(self):
        """Get the portal object, caching it"""
        if getattr(self, '_portal', None) is None:
            pu = getToolByName(self.context, "portal_url")
            self._portal = pu.getPortalObject()
        return self._portal

class JSONBrowserView(BrowserView, BrowserViewHelpers):
    def asDict(self, data):
        """Return dict to be turned into JSON"""
        raise NotImplementedError

    def __call__(self):
        try:
            # Is there a request body?
            if self.request.get_header('content_length') > 0:
                # NB: Should be checking self.request.getHeader('Content-Type') ==
                # 'application/json' but zope.testbrowser cannae do that.
                self.request.stdin.seek(0)
                data = json.loads(self.request.stdin.read())
            else:
                data = None

            out = self.asDict(data)
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
        except Redirect, ex:
            # Return as Unauthorized, so Javascript can redirect full page
            self.request.response.setStatus(403)
            self.request.response.setHeader("Content-type", "application/json")
            return json.dumps(dict(
                error=ex.__class__.__name__,
                location=str(ex),
            ))
        except NotFound, ex:
            self.request.response.setStatus(404)
            self.request.response.setHeader("Content-type", "application/json")
            return json.dumps(dict(
                error=ex.__class__.__name__,
                message=str(ex),
            ))
        except BadRequest, ex:
            self.request.response.setStatus(400)
            self.request.response.setHeader("Content-type", "application/json")
            return json.dumps(dict(
                error=ex.__class__.__name__,
                message=str(ex),
            ))
        except Exception, ex:
            if DevelopmentMode:
                import traceback
            logging.error("Failed call: " + self.request['URL'])
            logging.exception(ex)
            self.request.response.setStatus(500)
            self.request.response.setHeader("Content-type", "application/json")
            return json.dumps(dict(
                error=ex.__class__.__name__,
                message=str(ex),
                stacktrace=traceback.format_exc() if DevelopmentMode else '',
            ))
