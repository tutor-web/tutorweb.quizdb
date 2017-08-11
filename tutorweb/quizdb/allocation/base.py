import re
import urllib2
import importlib

from z3c.saconfig import Session

from tutorweb.quizdb import db
from ..sync.student import getStudentSettings

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
        settings = getStudentSettings(dbLec, student)
        alloc_method = settings.get('allocation_method', 'original')

        return allocation_module(alloc_method)(
            student=student,
            dbLec=dbLec,
            urlBase=urlBase,
        )

    @classmethod
    def allocFromUri(cls, student, uri, urlBase="/"):
        """Return the correct Allocation Method instance based on a question URI"""
        # NB: URIs Need to be unique for localStorage's sake
        uri = urllib2.unquote(uri.rsplit('/', 1)[-1])
        m = re.match(r'(\d+):([^/]*)$', uri)

        if m:
            # Should be of form (lecture-id):(stuff).
            dbLec = Session.query(db.Lecture).filter_by(lectureId=int(m.group(1))).one()
            return cls.allocFor(
                student=student,
                dbLec=dbLec,
                urlBase=urlBase,
            )

        # Fall back to OriginalAllocation
        from .original import OriginalAllocation
        return OriginalAllocation.allocFromUri(student, uri, urlBase)

    def __init__(self, student, dbLec, urlBase="/"):
        self.student = student
        self.dbLec = dbLec
        self.urlBase = urlBase
        self.targetDifficulty = None
        self.reAllocQuestions = False

    def getQuestion(self, uri, **kwargs):
        qns = list(self.getQuestions(uris=[uri], **kwargs))
        if len(qns) != 1:
            return None
        return qns[0][1]

    def getAllQuestions(self, **kwargs):
        return self.getQuestions(uris=None, **kwargs)

    def publicQnType(self, qn):
        if qn.qnType == 'tw_questiontemplate':
            return 'template'
        else:
            # "regular" question
            return None
