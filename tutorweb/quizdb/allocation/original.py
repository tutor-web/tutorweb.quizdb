import datetime
import random

from sqlalchemy.sql import func
from z3c.saconfig import Session

from tutorweb.quizdb import db
from .base import Allocation as BaseAllocation, DEFAULT_QUESTION_CAP


class OriginalAllocation(BaseAllocation):
    @classmethod
    def allocFromUri(cls, student, uri, urlBase="/"):
        # No lecture in URI, so fall back to querying database
        publicId = uri.rsplit("/", 1)[-1]

        # NB: This isn't very efficient, but in theory it's transitional
        query = Session.query(db.Question, db.Allocation, db.Lecture) \
            .join(db.Allocation).join(db.Lecture) \
            .filter(db.Allocation.publicId == publicId) \
            .filter(db.Question.active == True)
        (dbQn, dbAlloc, dbLec) = query.one()

        return OriginalAllocation(
            student=student,
            dbLec=dbLec,
            urlBase=urlBase,
        )

    def _questionUrl(self, publicId):
        return u'%s/quizdb-get-question/%s' % (
            self.urlBase,
            publicId,
        )

    def getAllQuestions(self):
        # Used in GetLectureQuestionsView
        # A function that gets all userGeneratedQuestions for an alloc too? Or at least filter what's there

        # Get all questions from DB and their allocations
        dbAllocs = Session.query(db.Question, db.Allocation) \
            .join(db.Allocation) \
            .filter(db.Question.lectures.contains(self.dbLec)) \
            .filter(db.Question.active == True) \
            .filter(db.Allocation.active == True) \
            .filter(db.Allocation.lectureId == self.dbLec.lectureId) \
            .filter(db.Question.onlineOnly == False) \
            .filter(db.Question.qnType != 'tw_questiontemplate') \
            .filter(db.Allocation.studentId == self.student.studentId) \
            .all()

        # Render each question into a dict
        for (dbQn, dbAlloc) in dbAllocs:
            yield (self._questionUrl(dbAlloc.publicId), dbQn)

    def getQuestions(self, uris=None, lockForUpdate=False, isAdmin=False, active=True):
        query = Session.query(db.Question, db.Allocation).join(db.Allocation)

        if lockForUpdate:
            query = query.with_lockmode('update')

        if uris is not None:
            query = query.filter(db.Allocation.publicId.in_(
                u.rsplit('/', 1)[-1] for u in uris
            ))
        else:
            # TODO: Use this instead of getAllQuestions
            query = query.filter(db.Question.lectures.contains(self.dbLec)) \
                .filter(db.Allocation.lectureId == self.dbLec.lectureId)
            query = query.filter(db.Question.onlineOnly == False)
            query = query.filter(db.Question.active == True)

        if active is not None:
            query = query.filter(db.Question.active == active)
        # If not an admin, ensure we're the right user
        if not isAdmin:
            query = query.filter(db.Allocation.studentId == self.student.studentId)

        for (dbQn, dbAlloc) in query:
            yield (self._questionUrl(dbAlloc.publicId), dbQn)

    def updateAllocation(self, settings, question_cap=DEFAULT_QUESTION_CAP, targetDifficulty=None, reAllocQuestions=False):
        # Get all existing allocations from the DB and their questions
        allocsByType = dict(
            tw_latexquestion=[],
            tw_questiontemplate=[],
            # NB: Need to add rows for each distinct question type, otherwise won't try and assign them
        )
        for (dbAlloc, dbQn) in (Session.query(db.Allocation, db.Question)
                .join(db.Question)
                .filter(db.Allocation.studentId == self.student.studentId)
                .filter(db.Allocation.active == True)
                .filter(db.Allocation.lectureId == self.dbLec.lectureId)):
            if not(dbQn.active) or (dbAlloc.allocationTime < dbQn.lastUpdate):
                # Question has been removed or is stale
                dbAlloc.active = False
            else:
                # Still around, so save it
                allocsByType[dbQn.qnType].append(dict(alloc=dbAlloc, question=dbQn))

        # Each question type should have at most question_cap questions
        for (qnType, allocs) in allocsByType.items():
            questionCap = int(settings.get('question_cap', DEFAULT_QUESTION_CAP))

            # If there's too many allocs, throw some away
            for i in sorted(random.sample(xrange(len(allocs)), max(len(allocs) - questionCap, 0)), reverse=True):
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
                        .filter(db.Question.lectures.contains(self.dbLec))
                        .filter(~db.Question.questionId.in_([a['alloc'].questionId for a in allocs]))
                        .filter(db.Question.qnType == qnType)
                        .filter(db.Question.active == True)
                        .order_by(targetExp)
                        .order_by(func.random())
                        .limit(max(questionCap - len(allocs), 0))):
                    dbAlloc = db.Allocation(
                        studentId=self.student.studentId,
                        questionId=dbQn.questionId,
                        lectureId=self.dbLec.lectureId,
                        allocationTime=datetime.datetime.utcnow(),
                    )
                    Session.add(dbAlloc)
                    allocs.append(dict(alloc=dbAlloc, question=dbQn))

        Session.flush()
        for allocs in allocsByType.values():
            for a in allocs:
                yield (self._questionUrl(a['alloc'].publicId), a['question'])
