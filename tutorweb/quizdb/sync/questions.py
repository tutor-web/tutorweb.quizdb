import datetime
import json
import logging
import random
import pytz

from sqlalchemy.orm import aliased
from sqlalchemy.orm.exc import NoResultFound
from sqlalchemy.sql.expression import func

from z3c.saconfig import Session

from tutorweb.content.schema import IQuestion
from tutorweb.quizdb import db
from tutorweb.quizdb.allocation.base import Allocation

# logging.getLogger('sqlalchemy.engine').setLevel(logging.DEBUG)
logger = logging.getLogger(__package__)


def toUTCDateTime(t):
    # Convert Zope DateTime into UTC datetime object
    # NB: MySQL cannae store less than second resolution
    return t.asdatetime().astimezone(pytz.utc).replace(microsecond=0, tzinfo=None)

def _ploneQuestionDict(listing):
    ploneQns = {}
    for l in listing:
        obj = l.getObject()
        data = obj.unrestrictedTraverse('@@data')
        # objPath is the canonical location of the question
        objPath = '/'.join(obj._target.getPhysicalPath()) \
                  if getattr(obj, 'isAlias', False) else l.getPath()

        if l['portal_type'] == 'tw_questionpack':
            # Expand question pack out into individual questions
            for (id, qn) in data.allQuestionsDict().iteritems():
                ploneQns['%s?question_id=%s' % (objPath, id)] = dict(
                    qnType='tw_latexquestion',
                    lastUpdate=toUTCDateTime(l['modified']),
                    correctChoices=[i for (i, x) in enumerate(qn['choices']) if x['correct']],
                    timesAnswered=qn.get('timesanswered', 0),
                    timesCorrect=qn.get('timescorrect', 0),
                )
        else:
            # Add individual question
            try:
                allChoices = data.allChoices()
            except AttributeError:
                # Template questions don't have correct answers
                allChoices = []
            correctChoices = [i for i, a in enumerate(allChoices) if a['correct']]

            ploneQns[objPath] = dict(
                qnType=l['portal_type'],
                lastUpdate=toUTCDateTime(l['modified']),
                correctChoices=correctChoices,
                timesAnswered=getattr(obj, 'timesanswered', 0),
                timesCorrect=getattr(obj, 'timescorrect', 0),
            )
    return ploneQns

def syncPloneQuestions(dbLec, lectureObj):
    """Ensure database has same questions as Plone"""
    # Get all plone questions, turn it into a dict by path
    if getattr(lectureObj, 'isAlias', False):
        lectureObj = lectureObj._target
    listing = lectureObj.portal_catalog.unrestrictedSearchResults(
        path={'query': '/'.join(lectureObj.getPhysicalPath()), 'depth': 1},
        object_provides=IQuestion.__identifier__
    )

    # If the lecture has same number of questions as before...
    if len(listing) == Session.query(db.Question).filter(db.Question.lectures.contains(dbLec)).count():
        # ...and we updated since the last question was inserted/updated
        if dbLec.lastUpdate > toUTCDateTime(max(l['modified'] for l in listing)):
            # ...don't do anything
            return False

    # Sort questions into a dict by path
    ploneQns = _ploneQuestionDict(listing)

    # Get all questions currently in the database
    for dbQn in (Session.query(db.Question).filter(db.Question.lectures.contains(dbLec))):
        qn = ploneQns.get(dbQn.plonePath, None)
        if qn is not None:
            # Question still there (or returned), update
            dbQn.active = True
            dbQn.correctChoices = json.dumps(qn['correctChoices'])
            dbQn.lastUpdate = qn['lastUpdate']
            # Dont add this question later
            del ploneQns[dbQn.plonePath]
# TODO: This is gibberish, obj/qn isn't there to test to see if it's an alias
#        elif dbQn.active and getattr(obj, 'isAlias', False):
#            # Remove symlink question from lecture
#            dbQn.lectures = [l for l in dbQn.lectures if l != dbLec]
#            dbQn.active = len(dbQn.lectures) > 0
#            dbQn.lastUpdate = datetime.datetime.utcnow()
        elif dbQn.active:
            # Remove question from all lectures and mark as inactive
            dbQn.lectures = []
            dbQn.active = False
            dbQn.lastUpdate = datetime.datetime.utcnow()
        else:
            # No question & already removed from DB
            pass

    # Insert any remaining questions
    for (path, qn) in ploneQns.iteritems():
        try:
            # If question already exists, add it to this lecture.
            dbQn = Session.query(db.Question).filter(db.Question.plonePath == path).one()
            dbQn.lectures.append(dbLec)
            dbQn.active = True
        except NoResultFound:
            Session.add(db.Question(
                plonePath=path,
                qnType=qn['qnType'],
                lastUpdate=qn['lastUpdate'],
                correctChoices=json.dumps(qn['correctChoices']),
                timesAnswered=qn['timesAnswered'],
                timesCorrect=qn['timesCorrect'],
                lectures=[dbLec],
            ))

    dbLec.lastUpdate = datetime.datetime.utcnow()
    Session.flush()
    return True


def getQuestionAllocation(dbLec, student, questionRoot, settings, targetDifficulty=None, reAllocQuestions=False):
    alloc = Allocation.allocFor(
        student=student,
        dbLec=dbLec,
        urlBase=questionRoot,
    )
    # Return all active questions
    for questionUri, pubType, dbQn in alloc.updateAllocation(settings, targetDifficulty=targetDifficulty, reAllocQuestions=reAllocQuestions):
        yield dict(
            _type=pubType,
            uri=questionUri,
            chosen=dbQn.timesAnswered,
            correct=dbQn.timesCorrect,
            online_only=dbQn.onlineOnly,
        )
