import random
import transaction

from Acquisition import aq_parent
from Products.CMFCore.utils import getToolByName

from plone.app.testing import login

from .base import FunctionalTestCase, IntegrationTestCase
from .base import USER_A_ID, USER_B_ID, USER_C_ID, MANAGER_ID

from ..sync.questions import syncPloneQuestions, getQuestionAllocation


class GetQuestionAllocationTest(FunctionalTestCase):
    maxDiff = None

    def logs(self, name='sqlalchemy'):
        return [x.getMessage() for x in self.loghandlers[name].records]

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

        def getAllocStats(lectureId, student, targetDifficulty, settings = {}):
            (allocs, _) = getQuestionAllocation(lectureId, student, 'http://x', settings, targetDifficulty=targetDifficulty)
            difficulty = [float(qn['correct']) / qn['chosen'] for qn in allocs]
            mean = sum(difficulty) / len(difficulty)
            variance = sum((x - mean) **2 for x in difficulty) / len(difficulty)
            return dict(difficulty=difficulty, mean=mean, variance=variance)

        # Create a lecture that has a range of questions, put them in DB
        qnCount = 250
        def questionOpts(i):
            return dict(
                timesanswered=qnCount,
                timescorrect=qnCount - i,
            )
        lectureObj = self.createTestLecture(qnCount=qnCount, qnOpts=questionOpts)
        login(portal, USER_A_ID)
        lectureId = lectureObj.restrictedTraverse('@@quizdb-sync').getLectureId()
        syncPloneQuestions(portal, lectureId, lectureObj)

        # A should get an even spread, B focuses on easy, C focuses on hard
        statsA = getAllocStats(lectureId, self.studentA, None)
        statsB = getAllocStats(lectureId, self.studentB, 0.175)
        statsC = getAllocStats(lectureId, self.studentC, 0.925)
        self.assertTrue(abs(0.500 - statsA['mean']) < 0.15)
        self.assertTrue(abs(0.175 - statsB['mean']) < 0.15)
        self.assertTrue(abs(0.925 - statsC['mean']) < 0.15)
        self.assertTrue(abs(0.08 - statsA['variance']) < 0.05)
        self.assertTrue(abs(0.01 - statsB['variance']) < 0.05)
        self.assertTrue(abs(0.01 - statsC['variance']) < 0.05)

    def tearDown(self):
        portal = self.layer['portal']
        login(portal, MANAGER_ID)

        # Remove any temporary Plone objects
        for l in reversed(getattr(self, 'tempObjects', [])):
            del aq_parent(l)[l.id]

        transaction.commit()
        super(GetQuestionAllocationTest, self).tearDown()

    def createTestLecture(self, qnCount=10, qnOpts=lambda i: {}):
        portal = self.layer['portal']
        login(portal, MANAGER_ID)
        tutorial = portal.restrictedTraverse('dept1/tut1')

        # Create some content, merging in specified options
        def createContent(parent, defaults, i=random.randint(1000000, 9999999)):
            # Autogenerate id, title
            opts = dict(
                id="%s-%d" % (dict(
                    tw_department="dept",
                    tw_tutorial="tut",
                    tw_lecture="lec",
                    tw_latexquestion="qn",
                )[defaults['type_name']], i),
                title="Unittest %s %d" % (defaults['type_name'], i),
            )

            # Merge in supplied opts
            opts.update(defaults)
            if defaults['type_name'] == 'tw_latexquestion':
                opts.update(qnOpts(i))

            obj = parent[parent.invokeFactory(**opts)]
            if not hasattr(self, 'tempObjects'):
                self.tempObjects = []
            self.tempObjects.append(obj)
            return obj

        # Create dept/tutorial/lecture
        deptObj = createContent(portal, dict(type_name="tw_department"))
        tutorialObj = createContent(deptObj, dict(type_name="tw_tutorial"))
        lectureObj = createContent(tutorialObj, dict(type_name="tw_lecture"))

        # Create required questions inside
        for i in xrange(qnCount):
            createContent(lectureObj, dict(
                type_name="tw_latexquestion",
                choices=[dict(text="orange", correct=False), dict(text="green", correct=True)],
                finalchoices=[],
            ), i)

        transaction.commit()
        return lectureObj
