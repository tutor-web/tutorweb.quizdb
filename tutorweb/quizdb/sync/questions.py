import datetime
import logging
import random
import pytz

from sqlalchemy.orm import aliased
from sqlalchemy.sql.expression import func

from z3c.saconfig import Session

from tutorweb.content.schema import IQuestion
from tutorweb.quizdb import db

# logging.getLogger('sqlalchemy.engine').setLevel(logging.DEBUG)
logger = logging.getLogger(__package__)

DEFAULT_QUESTION_CAP = 100  # Maximum number of questions to assign to user


def toUTCDateTime(t):
    # Convert Zope DateTime into UTC datetime object
    # NB: MySQL cannae store less than second resolution
    return t.asdatetime().astimezone(pytz.utc).replace(microsecond=0, tzinfo=None)


def syncPloneQuestions(lectureId, lectureObj):
    """Ensure database has same questions as Plone"""

    # Get all plone questions, turn it into a dict by path
    listing = lectureObj.portal_catalog.unrestrictedSearchResults(
        path={'query': '/'.join(lectureObj.getPhysicalPath()), 'depth': 1},
        object_provides=IQuestion.__identifier__
    )
    ploneQns = dict((b.getPath(), b) for b in listing)

    # Get all questions currently in the database
    for dbQn in (Session.query(db.Question).filter(db.Question.lectureId == lectureId)):
        brain = ploneQns.get(dbQn.plonePath, None)
        if brain is not None:
            # Question still there (or returned), update
            dbQn.active = True
            dbQn.lastUpdate = toUTCDateTime(brain['modified'])
            # Dont add this question later
            del ploneQns[dbQn.plonePath]
        elif dbQn.active:
            # Question has been removed, disable in database & record when we did it
            dbQn.active = False
            dbQn.lastUpdate = datetime.datetime.utcnow()
        else:
            # No question & already removed from DB
            pass

    # Insert any remaining questions
    for (path, brain) in ploneQns.iteritems():
        obj = brain.getObject()
        Session.add(db.Question(
            plonePath=path,
            qnType=obj.portal_type,
            lectureId=lectureId,
            lastUpdate=toUTCDateTime(brain['modified']),
            timesAnswered=getattr(obj, 'timesanswered', 0),
            timesCorrect=getattr(obj, 'timescorrect', 0),
        ))

    Session.flush()


def getQuestionAllocation(lectureId, student, questionRoot, settings, targetDifficulty=None, reAllocQuestions=False):
    def questionUrl(publicId):
        return questionRoot + '/quizdb-get-question/' + publicId

    # Get all existing allocations from the DB and their questions
    allocsByType = dict(
        tw_latexquestion=[],
        tw_questiontemplate=[],
        # NB: Need to add rows for each distinct question type, otherwise won't try and assign them
    )
    removedQns = []
    for (dbAlloc, dbQn) in (Session.query(db.Allocation, db.Question)
            .join(db.Question)
            .filter(db.Allocation.studentId == student.studentId)
            .filter(db.Allocation.active == True)
            .filter(db.Question.lectureId == lectureId)):
        if not(dbQn.active) or (dbAlloc.allocationTime < dbQn.lastUpdate):
            # Question has been removed or is stale
            removedQns.append(questionUrl(dbAlloc.publicId))
            dbAlloc.active = False
        else:
            # Still around, so save it
            allocsByType[dbQn.qnType].append(dict(alloc=dbAlloc, question=dbQn))

    # Each question type should have at most question_cap questions
    for (qnType, allocs) in allocsByType.items():
        questionCap = int(settings.get('question_cap', DEFAULT_QUESTION_CAP))

        # If there's too many allocs, throw some away
        for i in sorted(random.sample(xrange(len(allocs)), max(len(allocs) - questionCap, 0)), reverse=True):
            removedQns.append(questionUrl(allocs[i]['alloc'].publicId))
            allocs[i]['alloc'].active = False
            del allocs[i]

        # If there's questions to spare, and requested to do so, reallocate questions
        if len(allocs) == questionCap and reAllocQuestions:
            if targetDifficulty is None:
                raise ValueError("Must have a target difficulty to know what to remove")

            # Make ranking how likely questions are, based on targetDifficulty
            suitability = []
            for a in allocs:
                if a['question'].timesAnswered == 0:
                    # New questions should be added regardless
                    suitability.append(1)
                else:
                    suitability.append(1 - abs(targetDifficulty - float(a['question'].timesCorrect) / a['question'].timesAnswered))
            ranking = sorted(range(len(allocs)), key=lambda k: suitability[k])

            # Remove the least likely tenth
            for i in sorted(ranking[0:len(allocs) / 10 + 1], reverse=True):
                allocs[i]['alloc'].active = False
                del allocs[i]

        # Assign required questions randomly
        if len(allocs) < questionCap:
            if targetDifficulty is None:
                targetExp = None
            else:
                targetExp = func.abs(round(targetDifficulty * 50) - func.round((50.0 * db.Question.timesCorrect) / db.Question.timesAnswered))
            for dbQn in (Session.query(db.Question)
                    .filter(db.Question.lectureId == lectureId)
                    .filter(~db.Question.questionId.in_([a['alloc'].questionId for a in allocs]))
                    .filter(db.Question.qnType == qnType)
                    .filter(db.Question.active == True)
                    .order_by(targetExp)
                    .order_by(func.random())
                    .limit(max(questionCap - len(allocs), 0))):
                dbAlloc = db.Allocation(
                    studentId=student.studentId,
                    questionId=dbQn.questionId,
                    allocationTime=datetime.datetime.utcnow(),
                )
                Session.add(dbAlloc)
                allocs.append(dict(alloc=dbAlloc, question=dbQn))

    Session.flush()

    # Return all active questions
    return (
        [dict(
            _type="template" if a['question'].qnType == 'tw_questiontemplate' else None,
            uri=questionUrl(a['alloc'].publicId),
            chosen=a['question'].timesAnswered,
            correct=a['question'].timesCorrect,
            online_only = (a['question'].qnType == 'tw_questiontemplate'),
        ) for allocs in allocsByType.values() for a in allocs],
        removedQns,
    )
