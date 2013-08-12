import json

from z3c.saconfig import Session

from sqlalchemy.orm.exc import NoResultFound

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
        except Exception, ex:
            self.request.response.setStatus(500)
            self.request.response.setHeader("Content-type", "application/json")
            return json.dumps(dict(
                error=ex.__class__.__name__,
                message=str(ex),
            ))

    def getCurrentStudent(self):
        #TODO: What if anonymous?
        mb = self.context.portal_membership.getAuthenticatedMember()
        return self.getDbStudent(mb.getUserName())

    ### Database operations (move these elsewhere?)

    def getDbStudent(self, username):
        """Return the datbase student, creating if necessary"""
        try:
            return Session.query(db.Student) \
                .filter(db.Student.userName == username).one()
        except NoResultFound:
            dbstudent = db.Student(userName=username)
            Session.add(dbstudent)
            return dbstudent
