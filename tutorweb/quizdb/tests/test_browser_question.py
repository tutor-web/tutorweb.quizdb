import transaction

from plone.app.testing import login

from .base import FunctionalTestCase
from .base import USER_A_ID, USER_B_ID, MANAGER_ID


class GetQuestionViewTest(FunctionalTestCase):
    maxDiff = None

    def test_invalidUrl(self):
        """Test some definitely broken cases"""
        # Not supplying a question id is bad
        out = self.getJson(
            'http://nohost/plone/quizdb-get-question/',
            expectedStatus=404,
            user=USER_A_ID,
        )
        # Making up question IDs also bad
        out = self.getJson(
            'http://nohost/plone/quizdb-get-question/camelcamelcamel',
            expectedStatus=404,
            user=USER_A_ID,
        )

    def test_permission(self):
        """Who can get at questions?"""
        # Allocate lecture 1 & 2 to user A & B
        aAlloc = self.getJson('http://nohost/plone/dept1/tut1/lec1/@@quizdb-sync', user=USER_A_ID)
        bAlloc = self.getJson('http://nohost/plone/dept1/tut1/lec2/@@quizdb-sync', user=USER_B_ID)

        # A can get A's question (but not the path to the question)
        self.assertTrue('/quizdb-get-question/' in aAlloc['questions'][0]['uri'])
        out = self.getJson(aAlloc['questions'][0]['uri'], expectedStatus=200, user=USER_A_ID)
        self.assertTrue('path' not in out)
        self.assertTrue(out['title'].startswith('Unittest D1 T1 L1 Q'))
        out = self.getJson(aAlloc['questions'][0]['uri'], expectedStatus=404, user=USER_B_ID)

        # B can get B's question (but not the path to the question)
        self.assertTrue('/quizdb-get-question/' in bAlloc['questions'][0]['uri'])
        out = self.getJson(bAlloc['questions'][0]['uri'], expectedStatus=200, user=USER_B_ID)
        self.assertTrue('path' not in out)
        self.assertTrue(out['title'].startswith('Unittest D1 T1 L2 Q'))
        out = self.getJson(bAlloc['questions'][0]['uri'], expectedStatus=404, user=USER_A_ID)

        # Unauthorized people aren't allowed
        out = self.getJson(aAlloc['questions'][0]['uri'], expectedStatus=403, user=None)
        out = self.getJson(bAlloc['questions'][0]['uri'], expectedStatus=403, user=None)

        # Manager can see everything
        out = self.getJson(aAlloc['questions'][0]['uri'], expectedStatus=200, user=MANAGER_ID)
        self.assertTrue(out['title'].startswith('Unittest D1 T1 L1 Q'))
        self.assertEqual(out['path'], '/plone/dept1/tut1/lec1/qn' + out['title'][-1])
        out = self.getJson(bAlloc['questions'][0]['uri'], expectedStatus=200, user=MANAGER_ID)
        self.assertTrue(out['title'].startswith('Unittest D1 T1 L2 Q'))
        self.assertEqual(out['path'], '/plone/dept1/tut1/lec2/qn' + out['title'][-1])

    def test_questionDeletion(self):
        """After a question is deleted, can't get it"""
        # Create a temporary question
        login(self.layer['portal'], MANAGER_ID)
        self.layer['portal']['dept1']['tut1']['lec1'].invokeFactory(
            type_name="tw_latexquestion",
            id="qntmp",
            title="Unittest D1 T1 L1 QTmp",
        )
        transaction.commit()

        # Get qb1, q2, qntmp
        aAlloc = self.getJson('http://nohost/plone/dept1/tut1/lec1/@@quizdb-sync', user=USER_A_ID)
        self.assertTrue(len(aAlloc['questions']), 3)
        qntmp = [
            qn['uri'] for qn
            in aAlloc['questions']
            if self.getJson(qn['uri'])['title'] == 'Unittest D1 T1 L1 QTmp'
        ][0]

        # Delete QTmp
        browser = self.getBrowser('http://nohost/plone/dept1/tut1/lec1/qntmp/delete_confirmation', user=MANAGER_ID)
        browser.getControl('Delete').click()

        # Can't fetch qntmp no more
        self.getJson(qntmp, expectedStatus=404, user=USER_A_ID)

        # Sync again, only get q1 & q2
        aAlloc = self.getJson('http://nohost/plone/dept1/tut1/lec1/@@quizdb-sync', user=USER_A_ID)
        self.assertTrue(len(aAlloc['questions']), 2)

        # Still can't fetch qntmp no more
        self.getJson(qntmp, expectedStatus=404, user=USER_A_ID)

class GetLectureQuestionsViewTest(FunctionalTestCase):
    maxDiff = None

    def test_questionDeletion(self):
        """Don't return questions after they have been deleted"""
        # Create a temporary question
        login(self.layer['portal'], MANAGER_ID)
        self.layer['portal']['dept1']['tut1']['lec1'].invokeFactory(
            type_name="tw_latexquestion",
            id="qntmp",
            title="Unittest D1 T1 L1 QTmp",
        )
        transaction.commit()

        # Allocate to user A, should get questions
        aAlloc = self.getJson('http://nohost/plone/dept1/tut1/lec1/@@quizdb-sync', user=USER_A_ID)
        self.assertTrue('/quizdb-all-questions' in aAlloc['question_uri'])
        self.assertEqual(
            sorted([q['title'] for q in self.getJson(aAlloc['question_uri']).values()]),
            [u'Unittest D1 T1 L1 Q1', u'Unittest D1 T1 L1 Q2', u'Unittest D1 T1 L1 QTmp'],
        )

        # Delete QTmp
        browser = self.getBrowser('http://nohost/plone/dept1/tut1/lec1/qntmp/delete_confirmation', user=MANAGER_ID)
        browser.getControl('Delete').click()

        # Qntmp goes, as question data can't be got
        self.assertEqual(
            sorted([q['title'] for q in self.getJson(aAlloc['question_uri']).values()]),
            [u'Unittest D1 T1 L1 Q1', u'Unittest D1 T1 L1 Q2'],
        )

        # After sync, qntmp still gone
        aAlloc = self.getJson('http://nohost/plone/dept1/tut1/lec1/@@quizdb-sync', user=USER_A_ID)
        self.assertEqual(
            sorted([q['title'] for q in self.getJson(aAlloc['question_uri']).values()]),
            [u'Unittest D1 T1 L1 Q1', u'Unittest D1 T1 L1 Q2'],
        )
