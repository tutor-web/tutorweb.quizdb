# -*- coding: utf8 -*-
import transaction

from plone.app.testing import login
from plone.namedfile.file import NamedBlobFile

from .base import FunctionalTestCase, IntegrationTestCase
from .base import USER_A_ID, USER_B_ID, USER_C_ID, MANAGER_ID

from ..sync.questions import syncPloneQuestions, getQuestionAllocation


class SyncPloneQuestionsTest(IntegrationTestCase):
    maxDiff = None

    def getAllocation(self, alloc, user):
        portal = self.layer['portal']
        login(portal, USER_A_ID)
        view = portal.restrictedTraverse('quizdb-get-question')
        view.questionId = alloc.replace("http://x/quizdb-get-question/", "")
        return view.asDict({})

    def test_questionPacks(self):
        """A question pack should be stored as a bunch of separate questions"""
        portal = self.layer['portal']
        login(portal, MANAGER_ID)

        # Create a question pack
        lectureObj = portal['dept1']['tut1']['lec1']
        qnPack = lectureObj[lectureObj.invokeFactory(
            type_name="tw_questionpack",
            id='qnpack01',
            questionfile=NamedBlobFile(
                data="""
%ID umGen1-0
%title Einföld Umröðun
%format latex
Einangrið og finnið þannig gildi $x$ í eftirfarandi jöfnu. Merkið við þann möguleika sem best á við.
$$\frac{7}{4x-8}-8=3$$

a.true) $\frac{95}{44}$
b) $-\frac{95}{44}$
c) $-\frac{19}{4}$
d) $\frac{19}{4}$

%Explanation
Við leggjum 8 við báðum megin við jafnaðarmerkið, og fáum þá $\frac{7}{4x-8}=11$
%===
%ID Ag10q16
%title Táknmál mengjafræðinnar - mengi
%format latex
%image data:image/gif;base64,R0lGODlhAQABAAAAACH5BAEKAAEALAAAAAABAAEAAAICTAEAOw==
Hvert af eftirtöldu er rétt fyrir öll mengi $A,B,C$?

a.true) $\left((A \cup B) \cap C \right) \backslash B \subset A \cap C$
b) $\left((A \cup B) \cap C \right) \backslash B =  \emptyset $
c) $\left((A \cup B) \cap C \right) \backslash B \supset  A \cap C$

%Explanation
Stak sem er í annaðhvort $A$ eða $B$ og er í $C$ en
                """,
                contentType='text/x-tex',
                filename=u'qnpackcontent.tex',
            ),
        )]
        dbLec = lectureObj.restrictedTraverse('@@quizdb-sync').getDbLecture()
        syncPloneQuestions(dbLec, lectureObj)

        # Allocate to user A, should get all questions seperately
        login(portal, USER_A_ID)
        self.studentA = portal.restrictedTraverse('dept1/tut1/lec1/@@quizdb-sync').getCurrentStudent()
        (allocs, _) = getQuestionAllocation(dbLec, self.studentA, 'http://x', dict(question_cap=10))
        self.assertEqual(sorted(self.getAllocation(qn['uri'], USER_A_ID)['title'] for qn in allocs), [
            u'Einf\xf6ld Umr\xf6\xf0un',
            u'T\xe1knm\xe1l mengjafr\xe6\xf0innar - mengi',
            u'Unittest D1 T1 L1 Q1',
            u'Unittest D1 T1 L1 Q2',
        ])


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

        def getAllocStats(dbLec, student, targetDifficulty, settings = dict(question_cap=10)):
            (allocs, _) = getQuestionAllocation(dbLec, student, 'http://x', settings, targetDifficulty=targetDifficulty)
            difficulty = [float(qn['correct']) / qn['chosen'] for qn in allocs if qn['chosen'] > 10]
            mean = sum(difficulty) / len(difficulty)
            variance = sum((x - mean) **2 for x in difficulty) / len(difficulty)
            return dict(difficulty=difficulty, mean=mean, variance=variance)

        # Create a lecture that has a range of questions, put them in DB
        qnCount = 205
        def questionOpts(i):
            if i >= 200:
                # Add some questions with very little feedback
                return dict(
                    timesanswered=i - 200,
                    timescorrect=max(i - 202, 0),
                )
            return dict(
                timesanswered=qnCount,
                timescorrect=qnCount - i,
            )
        lectureObj = self.createTestLecture(qnCount=qnCount, qnOpts=questionOpts)
        login(portal, USER_A_ID)
        dbLec = lectureObj.restrictedTraverse('@@quizdb-sync').getDbLecture()
        syncPloneQuestions(dbLec, lectureObj)

        # A should get an even spread, B focuses on easy, C focuses on hard
        statsA = getAllocStats(dbLec, self.studentA, None)
        statsB = getAllocStats(dbLec, self.studentB, 0.175)
        statsC = getAllocStats(dbLec, self.studentC, 0.925)
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
        dbLec = lectureObj.restrictedTraverse('@@quizdb-sync').getDbLecture()
        syncPloneQuestions(dbLec, lectureObj)

        def gqa(targetDifficulty, reAllocQuestions, student=self.studentA):
            (allocs, _) = getQuestionAllocation(
                dbLec,
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
