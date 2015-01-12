import collections
import datetime
import dateutil.parser
import json
import logging
import random
import re
import time

from sqlalchemy import func
from sqlalchemy.orm import aliased
from sqlalchemy.orm.exc import NoResultFound
from sqlalchemy.sql import expression

from AccessControl import Unauthorized
from zope.publisher.interfaces import NotFound
from z3c.saconfig import Session

from tutorweb.content.schema import IQuestion
from tutorweb.quizdb import db
from .base import JSONBrowserView

# logging.getLogger('sqlalchemy.engine').setLevel(logging.DEBUG)
logger = logging.getLogger(__name__)

DEFAULT_QUESTION_CAP = 100  # Maximum number of questions to assign to user
INTEGER_SETTINGS = ['grade_s', 'grade_nmin', 'grade_nmax']  # Randomly-chosen questions that should result in an integer value


class SyncTutorialView(JSONBrowserView):
    def asDict(self, data):
        # If there's a incoming tutorial, break up lectures so each can be updated
        tutorial = data or dict()
        lectureDict = dict(
            (l['uri'].replace(self.context.absolute_url() + '/', ''), l)
            for l
            in tutorial.get('lectures', [])
        )

        # Fetch a list of all lectures
        lectureUrls = (
            l.id + '/quizdb-sync'
            for l
            in self.context.restrictedTraverse('@@folderListing')(
                portal_type='tw_lecture',
                sort_on='id',
            )
        )

        return dict(
            uri=self.context.absolute_url() + '/quizdb-sync',
            title=self.context.title,
            lectures=[
                self.context.restrictedTraverse(url).asDict(lectureDict.get(url, None))
                for url
                in lectureUrls
            ],
        )


class SyncLectureView(JSONBrowserView):
    def getStudentSettings(self, student):
        """Return a dict of lecture / tutorial settings, choosing a random value if required"""
        lectureId = self.getLectureId()

        # Fetch settings from lecture
        settings=dict(
            (i['key'], i['value'])
            for i
            in (self.context.aq_parent.settings or []) + (self.context.settings or [])
        )

        # Get all current settings as a dict, removing old ones
        allSettings = {}
        for dbS in (Session.query(db.LectureSetting)
                .filter(db.LectureSetting.lectureId == lectureId)
                .filter(db.LectureSetting.studentId == student.studentId)
                .all()):
            if dbS.key not in settings.keys() and dbS.key + ':max' not in settings.keys():
                # No longer in Plone, remove it here too
                Session.delete(dbS)
            else:
                allSettings[dbS.key] = dbS.value

        ignoreKey = {}
        for k in settings.keys():
            # Only update settings that have changed
            if k in allSettings and allSettings[k] == settings[k]:
                continue

            # If a variable setting has changed, assign a value and write this also
            if not(ignoreKey.get(k, False)) and (k.endswith(':max') or k.endswith(':min')):
                base_key = k.replace(":max", "").replace(":min", "")
                if base_key + ":max" not in settings:
                    raise ValueError(base_key + ":max not set in lecture")

                # Don't assign another value if/when other half shows up
                ignoreKey[base_key + ":min"] = True
                ignoreKey[base_key + ":max"] = True

                # Assign new value, rounding if appropriate
                new_value = random.uniform(
                    float(settings.get(base_key + ":min", 0)),
                    float(settings.get(base_key + ":max", None)),
                )
                if base_key in INTEGER_SETTINGS:
                    new_value = str(int(round(new_value)))
                else:
                    new_value = str(round(new_value, 3))

                Session.merge(db.LectureSetting(
                    lectureId=lectureId,
                    studentId=student.studentId,
                    key=base_key,
                    value=new_value,
                ))
                allSettings[base_key] = new_value

            # Add / update DB
            Session.merge(db.LectureSetting(
                lectureId=lectureId,
                studentId=student.studentId,
                key=k,
                value=settings[k],
            ))
            allSettings[k] = settings[k]

        Session.flush()
        return allSettings

    def getAnswerSummary(self, student):
        """Fetch answerSummary row for student"""
        try:
            dbAnsSummary = (Session.query(db.AnswerSummary)
                .with_lockmode('update')
                .filter(db.AnswerSummary.lectureId == self.getLectureId())
                .filter(db.AnswerSummary.studentId == student.studentId)
                .one())
        except NoResultFound:
            dbAnsSummary = db.AnswerSummary(
                lectureId=self.getLectureId(),
                studentId=student.studentId,
                grade=0,
            )
            Session.add(dbAnsSummary)

        # Update based on answer table
        (
            dbAnsSummary.lecAnswered,
            dbAnsSummary.lecCorrect,
            dbAnsSummary.practiceAnswered,
            dbAnsSummary.practiceCorrect,
        ) = (int(x) for x in Session.query(
            func.count(),
            func.ifnull(func.sum(db.Answer.correct), 0),
            func.ifnull(func.sum(db.Answer.practice), 0),
            func.ifnull(func.sum(expression.case([(db.Answer.practice & db.Answer.correct, 1)], else_=0)), 0),
        ).filter(db.Answer.lectureId == self.getLectureId()).filter(db.Answer.studentId == student.studentId).one())
        return dbAnsSummary

    def getCoinAward(self, student, dbAnsSummary, a, settings):
        """How many coins does this earn a student?"""
        newGrade = a.get('grade_after', None)
        out = 0

        # Got 8 questions right
        if dbAnsSummary.gradeHighWaterMark < 5.000 and newGrade >= 5.000:
            out += round(float(settings.get('award_lecture_answered', "1000")))

        # Has the lecture just been aced?
        if dbAnsSummary.gradeHighWaterMark < 9.998 and newGrade >= 9.998:
            out += round(float(settings.get('award_lecture_aced', "10000")))

            # Fetch all sibling lectures
            siblingPaths = [
                b.getPath()
                for b
                in self.context.aq_parent.restrictedTraverse('@@folderListing')(portal_type='tw_lecture')
                if b.getPath() != '/'.join(self.context.getPhysicalPath())
            ]

            # Is every other lecture aced?
            if (Session.query(db.AnswerSummary)
                    .join(db.Lecture)
                    .filter(db.AnswerSummary.studentId == student.studentId)
                    .filter(db.Lecture.plonePath.in_(siblingPaths))
                    .filter(db.AnswerSummary.gradeHighWaterMark > 9.998)
                    .count() > 0):
                out += round(float(settings.get('award_tutorial_aced', "100000")))
        return out

    def parseAnswerQueue(self, student, rawAnswerQueue, settings):
        # Filter nonsense out of answerQueue
        answerQueue = []
        uriSplit = re.compile('\/quizdb-get-question\/|\?')
        for a in rawAnswerQueue:
            if a.get('synced', False):
                continue
            if 'student_answer' not in a:
                continue
            if 'answer_time' not in a:
                logger.debug("Unanswered question passed to sync")
                continue
            if '/quizdb-get-question/' not in a['uri']:
                logger.warn("Question ID %s malformed" % a['uri'])
                continue
            answerQueue.append((uriSplit.split(a['uri'])[1], a))

        # Fetch all questions for allocations, locking for update
        dbQns = {}
        if len(answerQueue) > 0:
            for (dbQn, publicId) in (Session.query(db.Question, db.Allocation.publicId)
                .with_lockmode('update')
                .join(db.Allocation)
                .filter(db.Allocation.studentId == student.studentId)
                .filter(db.Allocation.publicId.in_(publicId for (publicId, a) in answerQueue))
                .all()):

                dbQns[publicId] = dbQn

        # Fetch summary
        dbAnsSummary = self.getAnswerSummary(student)

        for (publicId, a) in answerQueue:
            # Fetch question for allocation
            dbQn = dbQns.get(publicId, None)
            if dbQn is None:
                logger.error("No record of allocation %s for student %s" % (
                    publicId,
                    student.userName,
                ))
                continue

            if dbQn.qnType == 'tw_questiontemplate' and a.get('question_type', '') == 'usergenerated':
                # Evaluated a user-generated question, write it to the DB
                if 'question_id' not in a:
                    logger.warn("Missing ID of the question being answered")
                    continue

                ugAns = db.UserGeneratedAnswer(
                        studentId=student.studentId,
                        ugQuestionId=a['question_id'],
                        chosenAnswer=a['student_answer'].get('choice', None),
                        questionRating=a['student_answer'].get('rating', None),
                        comments=a['student_answer'].get('comments', ""),
                        studentGrade=a.get('grade_after', None),
                )
                Session.add(ugAns)

                # Store ID of full answer row
                Session.flush()
                a['student_answer'] = ugAns.ugAnswerId

            elif dbQn.qnType == 'tw_questiontemplate':
                if a['correct']:
                    # Write question to database
                    ugQn = db.UserGeneratedQuestion(
                        studentId=student.studentId,
                        questionId=dbQn.questionId,
                        text=a['student_answer']['text'],
                        explanation=a['student_answer']['explanation'],
                    )
                    for i, c in enumerate(a['student_answer']['choices']):
                        setattr(ugQn, 'choice_%d_answer' % i, c['answer'])
                        setattr(ugQn, 'choice_%d_correct' % i, c['correct'])
                    Session.add(ugQn)

                    # student_answer should contain the ID of our answer
                    Session.flush()
                    a['student_answer'] = ugQn.ugQuestionId
                else:
                    # Student skipped (and got an incorrect mark)
                    a['student_answer'] = None

            else: # A tw_latexquestion, probably
                # Check against plone to ensure student was right
                try:
                    ploneQn = self.portalObject().unrestrictedTraverse(str(dbQn.plonePath) + '/@@data')
                    a['correct'] = True if a['student_answer'] is not None and ploneQn.allChoices()[a['student_answer']]['correct'] else False
                    if a['correct']:
                        dbQn.timesCorrect += 1
                    dbQn.timesAnswered += 1  # NB: Do this once we know question is valid
                    #TODO: Recalculate grade at this point, instead of relying on JS?
                    # Write back stats to Plone
                    ploneQn.updateStats(dbQn.timesAnswered, dbQn.timesCorrect)
                except (KeyError, NotFound):
                    logger.error("Cannot find Plone question at %s" % dbQn.plonePath)
                    continue
                except (TypeError, IndexError):
                    logger.warn("Student answer %d out of range" % a['student_answer'])
                    continue

            # Update student summary rows
            dbAnsSummary.lecAnswered += 1 # NB: Including practice questions is intentional
            if a.get('correct', None):
                dbAnsSummary.lecCorrect += 1
            if a.get('practice', False):
                dbAnsSummary.practiceAnswered += 1
                if a.get('correct', None):
                    dbAnsSummary.practiceCorrect += 1

            # Does this earn the student any coins?
            coinsAwarded = self.getCoinAward(student, dbAnsSummary, a, settings)

            # Post-awards, update grade
            if a.get('grade_after', None) is not None:
                dbAnsSummary.grade = a['grade_after']
                if a['grade_after'] > dbAnsSummary.gradeHighWaterMark:
                    dbAnsSummary.gradeHighWaterMark = a['grade_after']

            # Update database with this answer
            Session.add(db.Answer(
                lectureId=self.getLectureId(),
                studentId=student.studentId,
                questionId=dbQn.questionId,
                chosenAnswer=a['student_answer'],
                correct=a.get('correct', None),
                grade=a.get('grade_after', None),
                timeStart=datetime.datetime.fromtimestamp(a['quiz_time']),
                timeEnd=datetime.datetime.fromtimestamp(a['answer_time']),
                practice=a.get('practice', False),
                coinsAwarded=coinsAwarded,
            ))
            a['synced'] = True
        Session.flush()

        # Get all previous real answers and send them back.
        dbAnswers = (Session.query(db.Answer)
            .filter(db.Answer.lectureId == self.getLectureId())
            .filter(db.Answer.studentId == student.studentId)
            .filter(db.Answer.practice == False)
            .order_by(db.Answer.timeEnd.desc())
            .all())
        out = [dict(  # NB: Not fully recreating what JS creates, but shouldn't be a problem
            correct=dbAns.correct,
            quiz_time=int(time.mktime(dbAns.timeStart.timetuple())),
            answer_time=int(time.mktime(dbAns.timeEnd.timetuple())),
            student_answer=dbAns.chosenAnswer,
            grade_after=dbAns.grade,
            synced=True,
        ) for dbAns in reversed(dbAnswers)]

        # Tell student how many questions they have answered
        if len(out) > 0:
            out[-1]['lec_answered'] = dbAnsSummary.lecAnswered
            out[-1]['lec_correct'] = dbAnsSummary.lecCorrect
            out[-1]['practice_answered'] = dbAnsSummary.practiceAnswered
            out[-1]['practice_correct'] = dbAnsSummary.practiceCorrect

        return out

    def getQuestionAllocation(self, student, questions, settings):
        removedQns = []

        # Get all plone questions, turn it into a dict by path
        listing = self.portalObject().portal_catalog.unrestrictedSearchResults(
            path={'query': '/'.join(self.context.getPhysicalPath()), 'depth': 1},
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
            .filter(db.Question.lectureId == self.getLectureId()) \
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
                    removedQns.append(self.questionUrl(dbQn, dbAlloc.publicId))
                    dbAllocs[i] = (dbQn, None)

        # Add any questions missing from DB
        for (path, brain) in ploneQns.iteritems():
            obj = brain.getObject()
            dbQn = db.Question(
                plonePath=path,
                qnType=obj.portal_type,
                lectureId=self.getLectureId(),
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
                    removedQns.append(self.questionUrl(dbAllocs[i][0], dbAllocs[i][1].publicId))
                    Session.delete(dbAllocs[i][1])  # NB: Should probably mark as deleted instead
                    dbAllocs[i] = (dbAllocs[i][0], None)
        Session.flush()

        # Return all active questions
        return (
            [dict(
                _type="template" if dbQn.qnType == 'tw_questiontemplate' else None,
                uri=self.questionUrl(dbQn, dbAlloc.publicId),
                chosen=dbQn.timesAnswered,
                correct=dbQn.timesCorrect,
                online_only = (dbQn.qnType == 'tw_questiontemplate'),
            ) for (dbQn, dbAlloc) in dbAllocs if dbAlloc is not None],
            removedQns,
        )

    def questionUrl(self, dbQn, publicId):
        if not hasattr(self, '_portalUrl'):
            self._portalUrl = self.portalObject().absolute_url()
        return self._portalUrl + '/quizdb-get-question/' + publicId

    def asDict(self, data):
        student = self.getCurrentStudent()
        settings = self.getStudentSettings(student)

        # Check we're the right user, given the data
        lecture = data or dict()
        if lecture.get('user', None) and lecture['user'] != student.userName:
            raise Unauthorized('This drill is for user ' + lecture['user'] + ', not ' + student.userName)

        # Build lecture dict
        (questions, removedQuestions) = self.getQuestionAllocation(
            student,
            lecture.get('questions', []),
            settings,
        )
        return dict(
            uri=self.context.absolute_url() + '/quizdb-sync',
            user=student.userName,
            question_uri=self.context.absolute_url() + '/quizdb-all-questions',
            slide_uri=self.context.absolute_url() + '/slide-html',
            review_uri=self.context.absolute_url() + '/quizdb-review-ugqn',
            title=self.context.title,
            settings=settings,
            answerQueue=self.parseAnswerQueue(student, lecture.get('answerQueue', []), settings),
            questions=questions,
            removed_questions=removedQuestions,
        )
