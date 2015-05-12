from sqlalchemy.orm.exc import NoResultFound

import transaction

from plone.app.testing import login

from .base import FunctionalTestCase, IntegrationTestCase
from .base import MANAGER_ID

from ..sync.questions import syncPloneQuestions, getQuestionAllocation
from ..sync.answers import parseAnswerQueue


class GetCoinAwardTest(FunctionalTestCase):
    maxDiff = None

    def test_award_templateqn_aced(self):
        portal = self.layer['portal']
        login(portal, MANAGER_ID)

        # Create students
        creators = [self.createTestStudent('creator%d' % i) for i in range(1,3)]
        reviewers = [self.createTestStudent('reviewer%d' % i) for i in range(1,11)]

        # Create a lecture with 2 template questions
        lectureObj = self.createTestLecture(qnCount=2, qnOpts=lambda i: dict(
            type_name="tw_questiontemplate",
        ))
        login(portal, creators[0].userName)
        dbLec = lectureObj.restrictedTraverse('@@quizdb-sync').getDbLecture()
        syncPloneQuestions(dbLec, lectureObj)

        # Try each creator
        for (creatorIndex, creator) in enumerate(creators):
            # Generate 7 questions and review each of them
            for qnCount in range(7):
                # user 1 generates a question (assign, answer), don't get any coin for that
                login(portal, creator.userName)
                creatorAllocs = getQuestionAllocation(dbLec, creator, portal.absolute_url(), {})

                creatorAq = parseAnswerQueue(dbLec.lectureId, lectureObj, creator, [
                    dict(
                        synced=False,
                        uri=creatorAllocs[0]['uri'],
                        student_answer=dict(
                            text=u"My %dth question" % qnCount,
                            explanation=u"I'm getting the hang of it",
                            choices=[dict(answer="Good?", correct=True), dict(answer="Bad?", correct=False)],
                        ),
                        correct=True,
                        quiz_time=  1000000000 + creatorIndex * 100000 + qnCount * 1000,
                        answer_time=1000000000 + creatorIndex * 100000 + qnCount * 1000 + 1,
                        grade_after=0.1,
                    ),
                    dict(
                        synced=False,
                        uri=creatorAllocs[1]['uri'],
                        student_answer=dict(
                            text=u"My %dth question (that people actually review)" % qnCount,
                            explanation=u"I'm getting the hang of it",
                            choices=[dict(answer="Good?", correct=True), dict(answer="Bad?", correct=False)],
                        ),
                        correct=True,
                        quiz_time=  1000000000 + creatorIndex * 100000 + qnCount * 1000 + 100,
                        answer_time=1000000000 + creatorIndex * 100000 + qnCount * 1000 + 100 + 1,
                        grade_after=0.1,
                    ),
                ], {})
                self.assertEqual([a['coins_awarded'] for a in creatorAq][-2:], [0, 0])

                # Start reviewing question
                for (i, reviewer) in enumerate(reviewers):
                    login(portal, reviewer.userName)
                    reviewerAllocs = getQuestionAllocation(dbLec, reviewer, portal.absolute_url(), {})
                    # Don't know which of reviewerAllocs matches creatorAq[-1], so guess
                    try:
                        parseAnswerQueue(dbLec.lectureId, lectureObj, reviewer, [
                            dict(
                                uri='%s?question_id=%s' % (reviewerAllocs[0]['uri'], creatorAq[-1]['student_answer']['question_id']),
                                question_type='usergenerated',
                                student_answer=dict(choice=3, rating=75, comments="monkey!"),
                                quiz_time=  1000000000 + creatorIndex * 100000 + qnCount * 1000 + 100 + i * 10,
                                answer_time=1000000000 + creatorIndex * 100000 + qnCount * 1000 + 100 + i * 10 + 1,
                            ),
                        ], {})
                    except ValueError as e:
                        # Should be complaining that can't find question
                        if creatorAq[-1]['student_answer']['question_id'] not in e.message:
                            self.fail()
                        parseAnswerQueue(dbLec.lectureId, lectureObj, reviewer, [
                            dict(
                                uri='%s?question_id=%s' % (reviewerAllocs[1]['uri'], creatorAq[-1]['student_answer']['question_id']),
                                question_type='usergenerated',
                                student_answer=dict(choice=4, rating=75, comments="monkey!"),
                                quiz_time=  1000000000 + creatorIndex * 100000 + qnCount * 1000 + 100 + i * 10,
                                answer_time=1000000000 + creatorIndex * 100000 + qnCount * 1000 + 100 + i * 10 + 1,
                            ),
                        ], {})

                    # User-generated question gets more coins once high reviews are majority
                    creatorAq = parseAnswerQueue(dbLec.lectureId, lectureObj, creator, [], {})
                    self.assertEqual(sorted([a['coins_awarded'] for a in creatorAq][-2:]), [0, 10000] if i >= 4 and qnCount < 5 else [0, 0])

            # Awarded coins for first 5 instances of the question that people review, even after first creator maxed out
            self.assertEqual(
                [a['coins_awarded'] for a in parseAnswerQueue(dbLec.lectureId, lectureObj, creator, [], {})],
                [0, 10000, 0, 10000, 0, 10000, 0, 10000, 0, 10000, 0, 0, 0, 0],
            )

        # Reviewers didn't get anything throughout entire process
        self.assertEqual(
            [a['coins_awarded'] for a in parseAnswerQueue(dbLec.lectureId, lectureObj, reviewers[0], [], {})],
            [0, 0, 0, 0, 0, 0, 0] * 2,
        )
