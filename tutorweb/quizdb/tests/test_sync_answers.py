from sqlalchemy.orm.exc import NoResultFound

import transaction

from plone.app.testing import login

from z3c.saconfig import Session

from .base import FunctionalTestCase, IntegrationTestCase
from .base import MANAGER_ID, USER_A_ID

from tutorweb.quizdb import db
from ..sync.questions import getQuestionAllocation
from ..sync.answers import parseAnswerQueue
from ..sync.student import getStudentSettings
from ..utils import getDbLecture, getDbStudent


class GetCoinAwardTest(FunctionalTestCase):
    maxDiff = None

    def test_tutorial_ace(self):
        """If turned on, should"""
        # Shortcut for making answerQueue entries
        aqTime = [1400000000]
        def aqEntry(alloc, qnIndex, correct, grade_after, user=USER_A_ID):
            qnData = self.getJson(alloc[qnIndex]['uri'], user=user)
            aqTime[0] += 10
            return dict(
                uri=qnData.get('uri', alloc[qnIndex]['uri']),
                type='tw_latexquestion',
                synced=False,
                correct=correct,
                student_answer=self.findAnswer(qnData, correct),
                quiz_time=aqTime[0] - 5,
                answer_time=aqTime[0] - 9,
                grade_after=grade_after,
            )

        portal = self.layer['portal']
        login(portal, MANAGER_ID)
        tutorial = portal['dept1'][portal['dept1'].invokeFactory(
            type_name='tw_tutorial',
            id='tut_awards',
            title='Unittest awards test',
            settings=[
                dict(key='award_lecture_answered', value=1 * 1000),
                dict(key='award_lecture_aced',     value=10 * 1000),
                dict(key='award_tutorial_aced',    value=100 * 1000),
            ],
        )]
        lectureObjs = [
            self.createTestLecture(qnCount=2, tutorialObj=tutorial),
            self.createTestLecture(qnCount=2, tutorialObj=tutorial),
        ]
        dbLecs = [
            lectureObj.restrictedTraverse('@@quizdb-sync').getDbLecture()
            for lectureObj in lectureObjs
        ]
        for i in xrange(len(dbLecs)):
            self.objectPublish(lectureObjs[i])
        self.objectPublish(portal['dept1']['tut1']['lec1'])

        # Sync other lectures, to make sure these don't figure in our calculations
        for l in [portal['dept1']['tut1']['lec1'], portal['dept1']['tut1']['lec2']]:
            self.objectPublish(portal['dept1']['tut1']['lec1'])
            self.objectPublish(portal['dept1']['tut1']['lec2'])

        # Log in, get allocations
        login(portal, USER_A_ID)
        dbStudent = lectureObjs[0].restrictedTraverse('@@quizdb-sync').getCurrentStudent()
        aAllocs = [
            list(getQuestionAllocation(dbLecs[0], dbStudent, portal.absolute_url(), {})),
            list(getQuestionAllocation(dbLecs[1], dbStudent, portal.absolute_url(), {})),
        ]
        import transaction ; transaction.commit()

        # Student answers lecture1
        aAq = parseAnswerQueue(dbLecs[0], lectureObjs[0], dbStudent, [
            aqEntry(aAllocs[0], 0, True, 5.5),
        ], {})
        import transaction ; transaction.commit()
        self.assertEqual(
            portal.unrestrictedTraverse('@@quizdb-student-award').asDict()['coin_available'],
            1 * 1000
        )

        # Student aces lecture1
        aAq = parseAnswerQueue(dbLecs[0], lectureObjs[0], dbStudent, [
            aqEntry(aAllocs[0], 0, True, 9.9),
        ], {})
        import transaction ; transaction.commit()
        self.assertEqual(
            portal.unrestrictedTraverse('@@quizdb-student-award').asDict()['coin_available'],
            11 * 1000,
        )

        # Student answers lecture2
        aAq = parseAnswerQueue(dbLecs[1], lectureObjs[1], dbStudent, [
            aqEntry(aAllocs[1], 0, True, 5.5),
        ], {})
        import transaction ; transaction.commit()
        self.assertEqual(
            portal.unrestrictedTraverse('@@quizdb-student-award').asDict()['coin_available'],
            12 * 1000
        )

        # Student aces lecture2, gets tutorial award
        aAq = parseAnswerQueue(dbLecs[1], lectureObjs[1], dbStudent, [
            aqEntry(aAllocs[1], 0, True, 9.9),
        ], {})
        import transaction ; transaction.commit()
        self.assertEqual(
            portal.unrestrictedTraverse('@@quizdb-student-award').asDict()['coin_available'],
            122 * 1000
        )

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

        # Try each creator
        for (creatorIndex, creator) in enumerate(creators):
            # Generate 7 questions and review each of them
            for qnCount in range(7):
                # user 1 generates a question (assign, answer), don't get any coin for that
                login(portal, creator.userName)
                creatorAllocs = list(getQuestionAllocation(dbLec, creator, portal.absolute_url(), {}))

                creatorAq = parseAnswerQueue(dbLec, lectureObj, creator, [
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
                    reviewerAllocs = list(getQuestionAllocation(dbLec, reviewer, portal.absolute_url(), {}))
                    # Don't know which of reviewerAllocs matches creatorAq[-1], so guess
                    try:
                        parseAnswerQueue(dbLec, lectureObj, reviewer, [
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
                        parseAnswerQueue(dbLec, lectureObj, reviewer, [
                            dict(
                                uri='%s?question_id=%s' % (reviewerAllocs[1]['uri'], creatorAq[-1]['student_answer']['question_id']),
                                question_type='usergenerated',
                                student_answer=dict(choice=4, rating=75, comments="monkey!"),
                                quiz_time=  1000000000 + creatorIndex * 100000 + qnCount * 1000 + 100 + i * 10,
                                answer_time=1000000000 + creatorIndex * 100000 + qnCount * 1000 + 100 + i * 10 + 1,
                            ),
                        ], {})

                    # User-generated question gets more coins once high reviews are majority
                    creatorAq = parseAnswerQueue(dbLec, lectureObj, creator, [], {})
                    self.assertEqual(sorted([a['coins_awarded'] for a in creatorAq][-2:]), [0, 10000] if i >= 4 and qnCount < 5 else [0, 0])

            # Awarded coins for first 5 instances of the question that people review, even after first creator maxed out
            self.assertEqual(
                [a['coins_awarded'] for a in parseAnswerQueue(dbLec, lectureObj, creator, [], {})],
                [0, 10000, 0, 10000, 0, 10000, 0, 10000, 0, 10000, 0, 0, 0, 0],
            )

        # Reviewers didn't get anything throughout entire process
        self.assertEqual(
            [a['coins_awarded'] for a in parseAnswerQueue(dbLec, lectureObj, reviewers[0], [], {})],
            [0, 0, 0, 0, 0, 0, 0] * 2,
        )

    def test_chat_competent_lecture(self):
        """If turned on, should"""
        # Shortcut for making answerQueue entries
        aqTime = [1400000000]
        def aqEntry(alloc, qnIndex, correct, grade_after, user=USER_A_ID):
            qnData = self.getJson(alloc[qnIndex]['uri'], user=user)
            aqTime[0] += 10
            return dict(
                uri=qnData.get('uri', alloc[qnIndex]['uri']),
                type='tw_latexquestion',
                synced=False,
                correct=correct,
                student_answer=self.findAnswer(qnData, correct),
                quiz_time=aqTime[0] - 5,
                answer_time=aqTime[0] - 9,
                grade_after=grade_after,
            )

        portal = self.layer['portal']
        login(portal, MANAGER_ID)
        lectureObj = portal['dept1']['tut1']['lec1']
        self.objectPublish(lectureObj)
        dbLec = lectureObj.restrictedTraverse('@@quizdb-sync').getDbLecture()

        # Also sync lec2, so coins knows about it below
        self.objectPublish(portal['dept1']['tut1']['lec2'])

        # Student isn't a tutor yet
        login(portal, USER_A_ID)
        dbStudent = lectureObj.restrictedTraverse('@@quizdb-sync').getCurrentStudent()
        self.assertEqual(dbStudent.chatTutor, [])

        # Student aces lecture1, but this doesn't make them a tutor
        aAllocs = list(getQuestionAllocation(dbLec, dbStudent, portal.absolute_url(), {}))
        import transaction ; transaction.commit()
        aAq = parseAnswerQueue(dbLec, lectureObj, dbStudent, [
            aqEntry(aAllocs, 0, True, 0.5),
            aqEntry(aAllocs, 0, True, 3.5),
            aqEntry(aAllocs, 0, True, 8.5),
            aqEntry(aAllocs, 0, True, 9.5),
            aqEntry(aAllocs, 0, True, 9.9),
        ], {})
        self.assertEqual(
            [a['coins_awarded'] for a in aAq],
            [0, 0, 1000, 0, 10000],
        )
        dbStudent = lectureObj.restrictedTraverse('@@quizdb-sync').getCurrentStudent()
        self.assertEqual(dbStudent.chatTutor, [])

        # Student stays below threshold for lecture2, isn't competent
        lectureObj = portal['dept1']['tut1']['lec2']
        dbLec = lectureObj.restrictedTraverse('@@quizdb-sync').getDbLecture()
        self.notifyModify(lectureObj)
        aAllocs = list(getQuestionAllocation(dbLec, dbStudent, portal.absolute_url(), {}))
        import transaction ; transaction.commit()
        aAq = parseAnswerQueue(dbLec, lectureObj, dbStudent, [
            aqEntry(aAllocs, 0, True, 0.5),
            aqEntry(aAllocs, 0, True, 3.5),
        ], dict(chat_competent_grade=5))
        dbStudent = lectureObj.restrictedTraverse('@@quizdb-sync').getCurrentStudent()
        self.assertEqual(dbStudent.chatTutor, [])

        # Goes above threshold, is competent
        aAq = parseAnswerQueue(dbLec, lectureObj, dbStudent, [
            aqEntry(aAllocs, 0, True, 4.5),
            aqEntry(aAllocs, 0, True, 5.5),
        ], dict(chat_competent_grade=5))
        dbStudent = lectureObj.restrictedTraverse('@@quizdb-sync').getCurrentStudent()
        self.assertEqual(dbStudent.chatTutor[0].tutorStudent, dbStudent)
        self.assertEqual(
            [l.plonePath for l in dbStudent.chatTutor[0].competentLectures],
            [u'/plone/dept1/tut1/lec2'],
        )

    def test_lectureVersion(self):
        """We can return the lecture version"""
        aqTime = [1400000000]
        def aqEntry(alloc, qnIndex, correct, grade_after, user=USER_A_ID):
            qnData = self.getJson(alloc[qnIndex]['uri'], user=user)
            aqTime[0] += 10
            return dict(
                uri=qnData.get('uri', alloc[qnIndex]['uri']),
                type='tw_latexquestion',
                synced=False,
                correct=correct,
                student_answer=self.findAnswer(qnData, correct),
                quiz_time=aqTime[0] - 5,
                answer_time=aqTime[0] - 9,
                grade_after=grade_after,
            )

        portal = self.layer['portal']
        lecObj = portal['dept1']['tut1']['lec1']
        self.objectPublish(lecObj)

        dbLec = getDbLecture('/'.join(lecObj.getPhysicalPath()))
        dbStudent = getDbStudent(USER_A_ID)

        # Get an allocation from the first version
        settings = getStudentSettings(dbLec, dbStudent)
        aAlloc = [x for x in getQuestionAllocation(dbLec, dbStudent, portal.absolute_url(), {})]
        self.assertEqual(settings['lecture_version'], '1')
        self.assertEqual(settings['timeout_max'], '10')
        transaction.commit()  # So we can fetch questions later

        # Update the lecture, so we go onto version 2
        lecObj.settings = [
            dict(key='timeout_max', value='20')
        ]
        self.notifyModify(lecObj)
        newSettings = getStudentSettings(dbLec, dbStudent)
        self.assertEqual(newSettings['lecture_version'], '2')
        self.assertEqual(newSettings['timeout_max'], '20')

        # Parse an answerQueue, hand old settings as student settings
        aAq = parseAnswerQueue(dbLec, lecObj, dbStudent, [
            aqEntry(aAlloc, 0, True, 5.5),
        ], newSettings, studentSettings=settings)
        transaction.commit()

        # Parse an answerQueue, hand new settings as student settings
        aAq = parseAnswerQueue(dbLec, lecObj, dbStudent, [
            aqEntry(aAlloc, 0, True, 6.5),
        ], newSettings, studentSettings=newSettings)
        transaction.commit()

        # Dig into DB, should see one with old one with new settings
        results = (Session.query(db.Answer.lectureVersion, db.Answer.grade)
            .filter_by(lectureId=dbLec.lectureId)
            .filter_by(studentId=dbStudent.studentId)
            .all())
        self.assertEqual(results, [
            (1, 5.5),
            (2, 6.5),
        ])
