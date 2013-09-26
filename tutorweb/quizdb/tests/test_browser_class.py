import logging

from zope.testing.loggingsupport import InstalledHandler

from plone.app.testing import login, logout

from Products.CMFCore.utils import getToolByName

from tutorweb.content.tests.base import setRelations
from .base import IntegrationTestCase
from .base import MANAGER_ID, USER_A_ID, USER_B_ID, USER_C_ID


class StudentResultsViewTest(IntegrationTestCase):
    maxDiff = None

    def setUp(self):
        """Set up a class ready for testing"""
        portal = self.layer['portal']
        login(portal, MANAGER_ID)

        if 'classa' not in portal:
            portal.invokeFactory(
                type_name="tw_class",
                id="classa",
                title="Unittest ClassA",
                students=[USER_A_ID, USER_C_ID, USER_B_ID],
                lectures=[],
            )
        else:
            portal['classa'].lectures = []

        self.loghandlers = dict(
            sqlalchemy=InstalledHandler('sqlalchemy.engine'),
            sync=InstalledHandler('tutorweb.quizdb.browser.sync')
        )

    def logs(self, name='sqlalchemy'):
        return [x.getMessage() for x in self.loghandlers[name].records]

    def test_lecturesInClass(self):
        """lecturesInClass should match obj.lectures"""
        portal = self.layer['portal']
        login(portal, MANAGER_ID)

        # A class without lectures returns nothing
        self.assertEqual(self.getView().lecturesInClass(), [
        ])

        # Add some lectures
        setRelations(portal['classa'], 'lectures', [
            portal['dept1']['tut1']['lec2'],
            portal['dept1']['tut1']['lec1'],
        ])
        self.assertEqual(self.getView().lecturesInClass(), [
            {'id': 'lec2', 'url': 'http://nohost/plone/dept1/tut1/lec2'},
            {'id': 'lec1', 'url': 'http://nohost/plone/dept1/tut1/lec1'},
        ])

    def test_allStudentGrades(self):
        """Get contents of table"""
        portal = self.layer['portal']
        lec1 = portal['dept1']['tut1']['lec1']
        lec2 = portal['dept1']['tut1']['lec2']
        login(portal, MANAGER_ID)

        # No lectures, but get students in specified order
        self.assertEqual(self.getView().allStudentGrades(), [
            dict(username=USER_A_ID, grades=[]),
            dict(username=USER_C_ID, grades=[]),
            dict(username=USER_B_ID, grades=[]),
        ])

        # Add lectures, get blank value for each
        setRelations(portal['classa'], 'lectures', [lec2, lec1])
        self.assertEqual(self.getView().allStudentGrades(), [
            dict(username=USER_A_ID, grades=['-', '-']),
            dict(username=USER_C_ID, grades=['-', '-']),
            dict(username=USER_B_ID, grades=['-', '-']),
        ])

        # Arnold answers a question
        self.updateAnswerQueue(USER_A_ID, lec1, [0.1, 0.3])
        self.assertEqual(self.getView().allStudentGrades(), [
            dict(username=USER_A_ID, grades=['-', 0.3]),
            dict(username=USER_C_ID, grades=['-', '-']),
            dict(username=USER_B_ID, grades=['-', '-']),
        ])

        # More answers appear
        self.updateAnswerQueue(USER_A_ID, lec2, [0.4, 0.8])
        self.updateAnswerQueue(USER_B_ID, lec2, [0.2])
        self.assertEqual(self.getView().allStudentGrades(), [
            dict(username=USER_A_ID, grades=[0.8, 0.3]),
            dict(username=USER_C_ID, grades=['-', '-']),
            dict(username=USER_B_ID, grades=[0.2, '-']),
        ])

        # Overwrite old answers
        self.updateAnswerQueue(USER_A_ID, lec2, [0.4, 0.8, 1.0])
        self.assertEqual(self.getView().allStudentGrades(), [
            dict(username=USER_A_ID, grades=[1.0, 0.3]),
            dict(username=USER_C_ID, grades=['-', '-']),
            dict(username=USER_B_ID, grades=[0.2, '-']),
        ])

    def updateAnswerQueue(self, user, lecture, grades):
        """Log in as user, run the answer queue part of sync"""
        login(self.layer['portal'], user)
        syncView = lecture.restrictedTraverse('@@quizdb-sync')
        student = syncView.getCurrentStudent()
        if not hasattr(self, 'timestamp'):
            self.timestamp = 1377000000
        else:
            self.timestamp += 100

        # Get an allocation, write back an answer, updating the grade
        qns = syncView.getQuestionAllocation(student, [])
        out = syncView.parseAnswerQueue(student, [dict(
            synced=False,
            uri=qns[0]['uri'],
            student_answer=0,
            correct=True,
            quiz_time=self.timestamp,
            answer_time=self.timestamp + 10,
            grade_after=grade,
        ) for grade in grades])
        login(self.layer['portal'], MANAGER_ID)
        import transaction ; transaction.commit()
        return out

    def getView(self):
        """Look up view for class"""
        c = self.layer['portal']['classa']
        return c.restrictedTraverse('student-results')
