import collections
import dateutil.parser
import logging
import random

from sqlalchemy.orm import aliased

from z3c.saconfig import Session

from tutorweb.content.schema import IQuestion
from tutorweb.quizdb import db

# logging.getLogger('sqlalchemy.engine').setLevel(logging.DEBUG)
logger = logging.getLogger(__package__)

DEFAULT_QUESTION_CAP = 100  # Maximum number of questions to assign to user


def questionUrl(portalObj, dbQn, publicId):
    return portalObj.absolute_url() + '/quizdb-get-question/' + publicId


def getQuestionAllocation(portalObj, lectureId, lectureObj, student, questions, settings):
    removedQns = []

    # Get all plone questions, turn it into a dict by path
    listing = portalObj.portal_catalog.unrestrictedSearchResults(
        path={'query': '/'.join(lectureObj.getPhysicalPath()), 'depth': 1},
        object_provides=IQuestion.__identifier__
    )
    ploneQns = dict((b.getPath(), b) for b in listing)

    # Get all questions from DB and their allocations
    subquery = aliased(
        db.Allocation,
        Session.query(db.Allocation).filter(
            db.Allocation.studentId == student.studentId
        ).subquery(),
    )
    dbAllocs = Session.query(db.Question, subquery) \
        .outerjoin(subquery) \
        .filter(db.Question.lectureId == lectureId) \
        .all()

    # Update / delete any existing questions
    usedAllocs = collections.defaultdict(list)
    spareAllocs = collections.defaultdict(list)
    for (i, (dbQn, dbAlloc)) in enumerate(dbAllocs):
        if dbQn.plonePath in ploneQns:
            # Already have dbQn, don't need to create it
            del ploneQns[dbQn.plonePath]
            dbQn.active = True
            if dbAlloc is not None:
                usedAllocs[dbQn.qnType].append(i)
            else:
                spareAllocs[dbQn.qnType].append(i)
        else:
            # Question isn't in Plone, so deactivate in DB
            dbQn.active = False
            if dbAlloc:
                # Remove allocation, so users don't take this question any more
                removedQns.append(questionUrl(portalObj, dbQn, dbAlloc.publicId))
                dbAllocs[i] = (dbQn, None)

    # Add any questions missing from DB
    for (path, brain) in ploneQns.iteritems():
        obj = brain.getObject()
        dbQn = db.Question(
            plonePath=path,
            qnType=obj.portal_type,
            lectureId=lectureId,
            lastUpdate=dateutil.parser.parse(brain['ModificationDate']),
            timesAnswered=getattr(obj, 'timesanswered', 0),
            timesCorrect=getattr(obj, 'timescorrect', 0),
        )
        Session.add(dbQn)
        spareAllocs[dbQn.qnType].append(len(dbAllocs))
        dbAllocs.append((dbQn, None))
    Session.flush()

    # Each question type should have at most question_cap questions
    for qnType in set(usedAllocs.keys() + spareAllocs.keys()):
        # Count questions that aren't allocated, and allocate more if needed
        neededAllocs = min(
            int(settings.get('question_cap', DEFAULT_QUESTION_CAP)),
            len(usedAllocs[qnType]) + len(spareAllocs[qnType]),
        ) - len(usedAllocs[qnType])
        if neededAllocs > 0:
            # Need more questions, so assign randomly
            for i in random.sample(spareAllocs[qnType], neededAllocs):
                dbAlloc = db.Allocation(
                    studentId=student.studentId,
                    questionId=dbAllocs[i][0].questionId,
                )
                Session.add(dbAlloc)
                dbAllocs[i] = (dbAllocs[i][0], dbAlloc)
        elif neededAllocs < 0:
            # Need less questions
            for i in random.sample(usedAllocs[qnType], abs(neededAllocs)):
                removedQns.append(questionUrl(portalObj, dbAllocs[i][0], dbAllocs[i][1].publicId))
                Session.delete(dbAllocs[i][1])  # NB: Should probably mark as deleted instead
                dbAllocs[i] = (dbAllocs[i][0], None)
    Session.flush()

    # Return all active questions
    return (
        [dict(
            _type="template" if dbQn.qnType == 'tw_questiontemplate' else None,
            uri=questionUrl(portalObj, dbQn, dbAlloc.publicId),
            chosen=dbQn.timesAnswered,
            correct=dbQn.timesCorrect,
            online_only = (dbQn.qnType == 'tw_questiontemplate'),
        ) for (dbQn, dbAlloc) in dbAllocs if dbAlloc is not None],
        removedQns,
    )
