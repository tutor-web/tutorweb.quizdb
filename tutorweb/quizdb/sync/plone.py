"""
Manage syncing between Plone<->QuizDB
"""
import datetime
import json
import pytz

from sqlalchemy.orm.exc import NoResultFound
from z3c.saconfig import Session

from tutorweb.content.schema import IQuestion
from tutorweb.quizdb import db
from tutorweb.quizdb.utils import getDbHost, getDbStudent

def syncClassSubscriptions(classObj):
    """
    Make sure all students in a class are subscribed
    """
    ploneClassPath = '/'.join(classObj.getPhysicalPath())

    for s in (classObj.students or []):
        dbStudent = getDbStudent(s)

        try:
            dbSub = (Session.query(db.Subscription)
                     .filter_by(student=dbStudent)
                     .filter_by(plonePath=ploneClassPath)
                     .one())
        except NoResultFound:
            Session.add(db.Subscription(
                student=dbStudent,
                plonePath=ploneClassPath,
            ))
        Session.flush()


def removeClassSubscriptions(ploneClassPath):
    """
    Remove any subscriptions for the class we're removing
    """
    dbSub = (Session.query(db.Subscription)
             .filter_by(plonePath=ploneClassPath)
             .delete())
    Session.flush()


def syncPloneLecture(lectureObj):
    """A lecture was updated in Plone, sync our representation"""
    def compareLgs(dbLec, globalSettings):
        """Compare stored settings to what plone returned"""
        dbKeys = []
        for dbLgs in (Session.query(db.LectureGlobalSetting)
                      .filter_by(lectureId=dbLec.lectureId)
                      .filter_by(lectureVersion=dbLec.currentVersion)
                     ):
            dbKeys.append(dbLgs.key)

            # Does DB key exist in Plone?
            if dbLgs.key not in globalSettings:
                return False

            # Do each of the values set for it match?
            for (k, v) in globalSettings[dbLgs.key].iteritems():
                if getattr(dbLgs, k) != v:
                    return False

        # Are there are keys in plone we did not consider?
        if set(dbKeys) != set(globalSettings.keys()):
            return False

        return True

    # Create Lecture object if not available in DB
    dbHost = getDbHost()
    plonePath = '/'.join(lectureObj.getPhysicalPath())
    try:
        dbLec = Session.query(db.Lecture).with_lockmode('update') \
            .filter(db.Lecture.hostId == dbHost.hostId) \
            .filter(db.Lecture.plonePath == plonePath).one()
    except NoResultFound:
        #TODO: Does the lecture actually have questions? If not this is pointless
        dbLec = db.Lecture(
            plonePath=plonePath,
            hostId=dbHost.hostId,
        )
        Session.add(dbLec)
        Session.flush()

    # Fetch current settings object
    globalSettings = lectureObj.unrestrictedTraverse('@@drill-settings').asDict()

    # If the settings don't match, bump the version and repopulate
    if not compareLgs(dbLec, globalSettings):
        dbLec.currentVersion += 1
        for (key, values) in globalSettings.iteritems():
            dbLgs = db.LectureGlobalSetting(
                lectureId=dbLec.lectureId,
                lectureVersion=dbLec.currentVersion,
                key=key,
                **values)
            Session.add(dbLgs)
        Session.flush()

    return dbLec


def removePloneLecture(lectureObj):
    """Mark this lecture as inactive"""
    pass # TODO:

def _toUTCDateTime(t):
    """Convert Zope DateTime into UTC datetime object"""
    # NB: MySQL cannae store less than second resolution
    return t.asdatetime().astimezone(pytz.utc).replace(microsecond=0, tzinfo=None)


def _ploneQuestionDict(listing):
    ploneQns = {}
    for l in listing:
        try:
            obj = l.getObject()
        except KeyError:
            # NB: Deletion in unit tests isn't working, this bodges around it
            continue
        data = obj.unrestrictedTraverse('@@data')
        # objPath is the canonical location of the question
        objPath = '/'.join(obj._target.getPhysicalPath()) \
                  if getattr(obj, 'isAlias', False) else l.getPath()

        if l['portal_type'] == 'tw_questionpack':
            # Expand question pack out into individual questions
            for (id, qn) in data.allQuestionsDict().iteritems():
                ploneQns['%s?question_id=%s' % (objPath, id)] = dict(
                    qnType='tw_latexquestion',
                    lastUpdate=_toUTCDateTime(l['modified']),
                    correctChoices=[i for (i, x) in enumerate(qn['choices']) if x['correct']],
                    incorrectChoices=[i for (i, x) in enumerate(qn['choices']) if not x['correct']],
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

            ploneQns[objPath] = dict(
                qnType=l['portal_type'],
                lastUpdate=_toUTCDateTime(l['modified']),
                correctChoices=[i for i, a in enumerate(allChoices) if a['correct']],
                incorrectChoices=[i for i, a in enumerate(allChoices) if not a['correct']],
                timesAnswered=getattr(obj, 'timesanswered', 0),
                timesCorrect=getattr(obj, 'timescorrect', 0),
            )
    return ploneQns


#TODO: Should this get merged with the above, and all tests use events?
def syncPloneQuestions(dbLec, lectureObj):
    """Ensure database has same questions as Plone"""
    # Get all plone questions, turn it into a dict by path
    if getattr(lectureObj, 'isAlias', False):
        lectureObj = lectureObj._target
    listing = lectureObj.portal_catalog.unrestrictedSearchResults(
        path={'query': '/'.join(lectureObj.getPhysicalPath()), 'depth': 1},
        object_provides=IQuestion.__identifier__
    )

    # Sort questions into a dict by path
    ploneQns = _ploneQuestionDict(listing)

    # Get all questions currently in the database
    for dbQn in (Session.query(db.Question).filter(db.Question.lectures.contains(dbLec))):
        qn = ploneQns.get(dbQn.plonePath, None)
        if qn is not None:
            # Question still there (or returned), update
            dbQn.active = True
            dbQn.correctChoices = json.dumps(qn['correctChoices'])
            dbQn.incorrectChoices = json.dumps(qn['incorrectChoices'])
            dbQn.lastUpdate = qn['lastUpdate']
            # Dont add this question later
            del ploneQns[dbQn.plonePath]
        elif dbQn.active and not(dbQn.plonePath.startswith(dbLec.plonePath)):
            # Remove slave symlink question from lecture
            dbQn.lectures = [l for l in dbQn.lectures if l != dbLec]
            dbQn.active = len(dbQn.lectures) > 0
            dbQn.lastUpdate = datetime.datetime.utcnow()
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
                incorrectChoices=json.dumps(qn['incorrectChoices']),
                timesAnswered=qn['timesAnswered'],
                timesCorrect=qn['timesCorrect'],
                lectures=[dbLec],
            ))

    dbLec.lastUpdate = datetime.datetime.utcnow()
    Session.flush()
    return True
