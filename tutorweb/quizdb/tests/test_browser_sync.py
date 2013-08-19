from .base import FunctionalTestCase
from .base import USER_A_ID, USER_B_ID


class SyncViewTest(FunctionalTestCase):
    maxDiff = None

    def test_anonymous(self):
        """Anonymous users should get a 403 (not a redirect to login)"""
        out = self.getJson('http://nohost/plone/dept1/tut1/lec1/@@quizdb-sync', expectedStatus=403, user=None)
        self.assertEqual(out['error'], 'Unauthorized')

    def test_allocate(self):
        """Allocate some questions"""
        # Allocate lecture 1 to user A
        aAlloc = self.getJson('http://nohost/plone/dept1/tut1/lec1/@@quizdb-sync', user=USER_A_ID)
        self.assertEquals(aAlloc['title'], u'Unittest D1 T1 L1')
        self.assertEquals(aAlloc['uri'], u'http://nohost/plone/dept1/tut1/lec1/quizdb-sync')
        self.assertEquals(aAlloc['question_uri'], u'http://nohost/plone/dept1/tut1/lec1/quizdb-all-questions')
        self.assertEquals(len(aAlloc['questions']), 2)
        self.assertEquals(
            sorted([self.getJson(qn['uri'])['title'] for qn in aAlloc['questions']]),
            [u'Unittest D1 T1 L1 Q1', u'Unittest D1 T1 L1 Q2'],
        )

        # Allocate lecture 2 to user A, should get all-new questions.
        aAlloc2 = self.getJson('http://nohost/plone/dept1/tut1/lec2/@@quizdb-sync', user=USER_A_ID)
        self.assertEquals(aAlloc2['title'], u'Unittest D1 T1 L2')
        self.assertEquals(aAlloc2['uri'], u'http://nohost/plone/dept1/tut1/lec2/quizdb-sync')
        self.assertEquals(aAlloc2['question_uri'], u'http://nohost/plone/dept1/tut1/lec2/quizdb-all-questions')
        self.assertEquals(len(aAlloc2['questions']), 2)
        self.assertEquals(
            sorted([self.getJson(qn['uri'])['title'] for qn in aAlloc2['questions']]),
            [u'Unittest D1 T1 L2 Q1', u'Unittest D1 T1 L2 Q2'],
        )

        # User B gets a different allocation
        bAlloc = self.getJson('http://nohost/plone/dept1/tut1/lec1/@@quizdb-sync', user=USER_B_ID)
        self.assertEquals(bAlloc['title'], u'Unittest D1 T1 L1')
        self.assertEquals(bAlloc['uri'], u'http://nohost/plone/dept1/tut1/lec1/quizdb-sync')
        self.assertEquals(bAlloc['question_uri'], u'http://nohost/plone/dept1/tut1/lec1/quizdb-all-questions')
        self.assertEquals(len(bAlloc['questions']), 2)
        self.assertTrue(aAlloc['questions'][0]['uri'] != bAlloc['questions'][0]['uri'])
        self.assertTrue(aAlloc['questions'][0]['uri'] != bAlloc['questions'][1]['uri'])
        self.assertTrue(aAlloc['questions'][1]['uri'] != bAlloc['questions'][0]['uri'])
        self.assertTrue(aAlloc['questions'][1]['uri'] != bAlloc['questions'][1]['uri'])

        # Still get the same allocations if we call again
        aAlloc1 = self.getJson('http://nohost/plone/dept1/tut1/lec1/@@quizdb-sync', user=USER_A_ID)
        bAlloc1 = self.getJson('http://nohost/plone/dept1/tut1/lec1/@@quizdb-sync', user=USER_B_ID)
        self.assertTrue(aAlloc['questions'][0]['uri'] == aAlloc1['questions'][0]['uri'])
        self.assertTrue(aAlloc['questions'][1]['uri'] == aAlloc1['questions'][1]['uri'])
        self.assertTrue(bAlloc['questions'][0]['uri'] == bAlloc1['questions'][0]['uri'])
        self.assertTrue(bAlloc['questions'][1]['uri'] == bAlloc1['questions'][1]['uri'])
