import transaction

from plone.app.testing import login

from .base import FunctionalTestCase, IntegrationTestCase
from .base import USER_A_ID, USER_B_ID, USER_C_ID, MANAGER_ID

from ..sync.questions import syncPloneQuestions, getQuestionAllocation


class GetQuestionAllocationTest(FunctionalTestCase):
    maxDiff = None

    def setUp(self):
        """Fetch student record for all users"""
        super(GetQuestionAllocationTest, self).setUp()
        portal = self.layer['portal']
        login(portal, MANAGER_ID)

        login(portal, USER_A_ID)
        self.studentA = portal.restrictedTraverse('dept1/tut1/lec1/@@quizdb-sync').getCurrentStudent()
        login(portal, USER_B_ID)
        self.studentB = portal.restrictedTraverse('dept1/tut1/lec1/@@quizdb-sync').getCurrentStudent()
        login(portal, USER_C_ID)
        self.studentC = portal.restrictedTraverse('dept1/tut1/lec1/@@quizdb-sync').getCurrentStudent()

        transaction.commit()

    def test_targetDifficutly(self):
        """Make sure we can influence the target difficulty"""
        portal = self.layer['portal']
        login(portal, MANAGER_ID)

        def getAllocStats(lectureId, student, targetDifficulty, settings = dict(question_cap=10)):
            (allocs, _) = getQuestionAllocation(lectureId, student, 'http://x', settings, targetDifficulty=targetDifficulty)
            difficulty = [float(qn['correct']) / qn['chosen'] for qn in allocs]
            mean = sum(difficulty) / len(difficulty)
            variance = sum((x - mean) **2 for x in difficulty) / len(difficulty)
            return dict(difficulty=difficulty, mean=mean, variance=variance)

        # Create a lecture that has a range of questions, put them in DB
        qnCount = 200
        def questionOpts(i):
            return dict(
                timesanswered=qnCount,
                timescorrect=qnCount - i,
            )
        lectureObj = self.createTestLecture(qnCount=qnCount, qnOpts=questionOpts)
        login(portal, USER_A_ID)
        lectureId = lectureObj.restrictedTraverse('@@quizdb-sync').getLectureId()
        syncPloneQuestions(lectureId, lectureObj)

        # A should get an even spread, B focuses on easy, C focuses on hard
        statsA = getAllocStats(lectureId, self.studentA, None)
        statsB = getAllocStats(lectureId, self.studentB, 0.175)
        statsC = getAllocStats(lectureId, self.studentC, 0.925)
        self.assertLess(abs(0.500 - statsA['mean']), 0.15)
        self.assertLess(abs(0.175 - statsB['mean']), 0.15)
        self.assertLess(abs(0.925 - statsC['mean']), 0.15)
        self.assertLess(abs(0.08 - statsA['variance']), 0.05)
        self.assertLess(abs(0.01 - statsB['variance']), 0.05)
        self.assertLess(abs(0.01 - statsC['variance']), 0.05)

    def test_reAllocQuestions(self):
        """Make sure we can throw away un-needed questions"""
        portal = self.layer['portal']
        login(portal, MANAGER_ID)

        # Create a lecture that has a range of questions, put them in DB
        qnCount = 100
        def questionOpts(i):
            return dict(
                timesanswered=qnCount,
                timescorrect=i,
            )
        lectureObj = self.createTestLecture(qnCount=qnCount, qnOpts=questionOpts)
        login(portal, USER_A_ID)
        lectureId = lectureObj.restrictedTraverse('@@quizdb-sync').getLectureId()
        syncPloneQuestions(lectureId, lectureObj)

        def gqa(targetDifficulty, reAllocQuestions, student=self.studentA):
            (allocs, _) = getQuestionAllocation(
                lectureId,
                student,
                'http://x',
                dict(question_cap=10),
                targetDifficulty=targetDifficulty,
                reAllocQuestions=reAllocQuestions,
            )
            return allocs
        aAllocs = []

        # Assign to A randomly
        aAllocs.append(gqa(None, False))
        self.assertEquals(len(aAllocs[0]), 10)

        # Reassign, with high grade should get rid of easy questions
        aAllocs.append(gqa(0.925, True))
        self.assertEquals(len(aAllocs[1]), 10)

        # Old items should be easy
        oldItems = [a for a in aAllocs[-2] if a not in aAllocs[-1]]
        self.assertEquals(len(oldItems), 2)
        for a in oldItems:
            self.assertLess(a['correct'], 25)

        # New items should be hard
        newItems = [a for a in aAllocs[-1] if a not in aAllocs[-2]]
        self.assertEquals(len(newItems), 2)
        for a in newItems:
            self.assertGreater(a['correct'], 75)

        # Reassign, with low grade should get rid of hard questions
        aAllocs.append(gqa(0.025, True))
        self.assertEquals(len(aAllocs[1]), 10)

        # Old items should be hard
        oldItems = [a for a in aAllocs[-2] if a not in aAllocs[-1]]
        self.assertEquals(len(oldItems), 2)
        for a in oldItems:
            self.assertGreater(a['correct'], 75)

        # New items should be easy
        newItems = [a for a in aAllocs[-1] if a not in aAllocs[-2]]
        self.assertEquals(len(newItems), 2)
        for a in newItems:
            self.assertLess(a['correct'], 25)
