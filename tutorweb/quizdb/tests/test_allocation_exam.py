from .base import FunctionalTestCase
from .base import USER_A_ID, USER_B_ID, USER_C_ID, USER_D_ID, MANAGER_ID

class ExamAllocationTest(FunctionalTestCase):
    maxDiff = None

    def test_allocation(self):
        # Shortcut for making answerQueue entries
        aqTime = [1377000000]
        def aqEntry(alloc, qnIndex, correct, grade_after, user=USER_A_ID):
            qnData = self.getJson(alloc['questions'][qnIndex]['uri'], user=user)
            aqTime[0] += 120
            return dict(
                uri=qnData.get('uri', alloc['questions'][qnIndex]['uri']),
                type='tw_latexquestion',
                synced=False,
                correct=correct,
                student_answer=self.findAnswer(qnData, correct),
                quiz_time=aqTime[0] - 50,
                answer_time=aqTime[0] - 20,
                grade_after=grade_after,
            )

        # Create a lecture which uses exam
        lecObj = self.createTestLecture(qnCount=5, lecOpts=lambda i: dict(settings=[
            dict(key="allocation_method", value="exam"),
        ]))
        lecPath = 'http://nohost/' + '/'.join(lecObj.getPhysicalPath())

        # Syncing returns a list of questions
        aAlloc = self.getJson(lecPath + '/@@quizdb-sync', user=USER_A_ID)
        self.assertEqual([a['uri'] for a in aAlloc['questions']], [
            u'http://nohost/plone/quizdb-get-question/1:qn-0',
            u'http://nohost/plone/quizdb-get-question/1:qn-1',
            u'http://nohost/plone/quizdb-get-question/1:qn-2',
            u'http://nohost/plone/quizdb-get-question/1:qn-3',
            u'http://nohost/plone/quizdb-get-question/1:qn-4',
        ])

        # Can get questions, they're in order
        allQns = self.getJson(aAlloc['question_uri'], user=USER_A_ID)
        self.assertEqual(dict((k, qn['title']) for k, qn in allQns.iteritems()), {
            u'http://nohost/plone/quizdb-get-question/1:qn-0': u'Unittest tw_latexquestion 0',
            u'http://nohost/plone/quizdb-get-question/1:qn-1': u'Unittest tw_latexquestion 1',
            u'http://nohost/plone/quizdb-get-question/1:qn-2': u'Unittest tw_latexquestion 2',
            u'http://nohost/plone/quizdb-get-question/1:qn-3': u'Unittest tw_latexquestion 3',
            u'http://nohost/plone/quizdb-get-question/1:qn-4': u'Unittest tw_latexquestion 4',
        })
        # And just the one
        self.assertEqual(
            self.getJson(aAlloc['questions'][0]['uri'], user=USER_A_ID)['title'],
            u'Unittest tw_latexquestion 0',
        )
        self.assertEqual(
            self.getJson(aAlloc['questions'][4]['uri'], user=USER_A_ID)['title'],
            u'Unittest tw_latexquestion 4',
        )

        # Can't fall off the end
        self.getJson(u'http://nohost/plone/quizdb-get-question/1:qn-99', user=USER_A_ID, expectedStatus=404)

        # Can write questions back
        aAlloc = self.getJson(lecPath + '/@@quizdb-sync', user=USER_A_ID, body=dict(
            answerQueue=[
                aqEntry(aAlloc, 0, True, 0.3, user=USER_A_ID),
                aqEntry(aAlloc, 1, True, 0.4, user=USER_A_ID),
                aqEntry(aAlloc, 2, True, 0.5, user=USER_A_ID),
            ],
        ))
        self.assertEqual([a['grade_after'] for a in aAlloc['answerQueue']], [
            0.3,
            0.4,
            0.5,
        ])
