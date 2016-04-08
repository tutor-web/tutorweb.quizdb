import re
import importlib

from z3c.saconfig import Session

from tutorweb.quizdb import db

DEFAULT_QUESTION_CAP = 100  # Maximum number of questions to assign to user


def allocation_module(mod_name):
    """Load an allocation module and return the allocation class within"""
    mod_name = re.sub('[^A-Z]+', '', mod_name, 0, re.I)
    return getattr(importlib.import_module(
        '..%s' % (mod_name),
        __name__,
    ), '%sAllocation' % mod_name.title())


class Allocation(object):
    @classmethod
    def allocFor(cls, student, dbLec, urlBase="/"):
        """Return the correct Allocation Method instance for this lecture"""
        alloc_method = (Session.query(db.LectureSetting.value)
            .filter(db.LectureSetting.lectureId == dbLec.lectureId)
            .filter(db.LectureSetting.studentId == student.studentId)
            .filter(db.LectureSetting.key == 'allocation_method')
            .first())
        if not alloc_method:
            alloc_method = ['original']

        return allocation_module(alloc_method[0])(
            student=student,
            dbLec=dbLec,
            urlBase=urlBase,
        )

    @classmethod
    def allocFromUri(cls, student, uri, urlBase="/"):
        from .original import OriginalAllocation

        # TODO: If URIs look like (lecture-id):(whatever), can choose on that.
        # NB: URIs Need to be unique for localStorage's sake

        # Fall back to OriginalAllocation
        return OriginalAllocation.allocFromUri(student, uri, urlBase)

    def __init__(self, student, dbLec, urlBase="/"):
        self.student = student
        self.dbLec = dbLec
        self.urlBase = urlBase

    def getQuestion(self, uri, **kwargs):
        qns = list(self.getQuestions(uris=[uri], **kwargs))
        if len(qns) != 1:
            return None
        return qns[0][1]

    def getAllQuestions(self, **kwargs):
        return self.getQuestions(uris=None, **kwargs)
