import base64
import json

import transaction

from plone.app.testing import login

from .base import FunctionalTestCase
from .base import USER_A_ID, USER_B_ID, USER_C_ID, USER_D_ID, MANAGER_ID


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

    def test_userGeneratedQuestions(self):
        """Should occasionally get user generated questions"""
        portal = self.layer['portal']
        login(portal, MANAGER_ID)

        # Create a lecture with one question template
        portal['dept1'].invokeFactory(
            type_name="tw_tutorial",
            id="tmpltut",
            title=u"Tutorial with a question cap of 5",
            settings=[
                dict(key='question_cap', value='5'),
                dict(key='prob_template_eval', value='0.8'),
                dict(key='cap_template_qns', value='3'),
                dict(key='cap_template_qn_reviews', value='2'),
            ],
        )
        portal['dept1']['tmpltut'].invokeFactory(
            type_name="tw_lecture",
            id="tmpllec",
            title=u"Lecture with no question cap (but uses default of 5)",
        )
        portal['dept1']['tmpltut']['tmpllec'].invokeFactory(
            type_name="tw_questiontemplate",
            id="tmplqn0",
            title="Unittest tmpllec tmplQ0",
        )
        transaction.commit()

        # User A should get assigned the template question
        aAlloc = self.getJson('http://nohost/plone/dept1/tmpltut/tmpllec/@@quizdb-sync', user=USER_A_ID)
        self.assertEquals(
            [self.getJson(qn['uri'])['title'] for qn in aAlloc['questions']],
            [u'Unittest tmpllec tmplQ0'],
        )

        # Write a question back
        aAlloc = self.getJson('http://nohost/plone/dept1/tmpltut/tmpllec/@@quizdb-sync', user=USER_A_ID, body=dict(
            answerQueue=[
                dict(
                    synced=False,
                    uri=aAlloc['questions'][0]['uri'],
                    student_answer=dict(
                        text=u"Want some rye?",
                        choices=[
                            dict(answer="Course you do", correct=True),
                            dict(answer="No thanks", correct=False),
                        ],
                        explanation=u'So you can get the keys',
                    ),
                    correct=True,
                    quiz_time=1377000000,
                    answer_time=1377000010,
                    grade_after=0.1,
                ),
            ],
        ))

        # Helper to order questions by type
        def qnsByType(uri, user=USER_A_ID, loops=20):
            out = {}
            for i in range(loops):
                qn = self.getJson(uri, user=user)
                if qn['_type'] not in out:
                    out[qn['_type']] = []
                out[qn['_type']].append(qn)
            return out

        # User A still only gets to write questions
        qns = qnsByType(aAlloc['questions'][0]['uri'], user=USER_A_ID)
        self.assertTrue(qns.keys(), ['template'])

        # User B might get to answer that question though
        bAlloc = self.getJson('http://nohost/plone/dept1/tmpltut/tmpllec/@@quizdb-sync', user=USER_B_ID)
        qns = qnsByType(bAlloc['questions'][0]['uri'], user=USER_B_ID)
        self.assertTrue(qns.keys(), ['template', 'usergenerated'])
        self.assertTrue('Want some rye?' in qns['usergenerated'][0]['text'])
        self.assertTrue('Course you do' in qns['usergenerated'][0]['choices'][0])
        self.assertTrue('No thanks' in qns['usergenerated'][0]['choices'][1])
        self.assertEqual(
            qns['usergenerated'][0]['question_id'],
            aAlloc['answerQueue'][0]['student_answer'],
        )
        self.assertEqual(qns['usergenerated'][0]['shuffle'], [0, 1])
        answer = json.loads(base64.b64decode(qns['usergenerated'][0]['answer']))
        self.assertTrue('So you can get the keys' in answer['explanation'])
        self.assertEqual(answer['correct'], [0])

        # So might user C & D
        cAlloc = self.getJson('http://nohost/plone/dept1/tmpltut/tmpllec/@@quizdb-sync', user=USER_C_ID)
        self.assertTrue(qnsByType(cAlloc['questions'][0]['uri'], user=USER_C_ID).keys(), ['template', 'usergenerated'])
        dAlloc = self.getJson('http://nohost/plone/dept1/tmpltut/tmpllec/@@quizdb-sync', user=USER_D_ID)
        self.assertTrue(qnsByType(dAlloc['questions'][0]['uri'], user=USER_D_ID).keys(), ['template', 'usergenerated'])

        # The URI generated has the question_id appended to the end
        self.assertEqual(
            qns['usergenerated'][0]['uri'],
            '%s?question_id=%d' % (bAlloc['questions'][0]['uri'], qns['usergenerated'][0]['question_id']),
        )

        # Can fetch it directly using this URL
        self.assertEqual(
            self.getJson(qns['usergenerated'][0]['uri'], user=USER_B_ID),
            qns['usergenerated'][0],
        )

        # If B answers it, doesn't get to answer it again
        bAlloc = self.getJson('http://nohost/plone/dept1/tmpltut/tmpllec/@@quizdb-sync', user=USER_B_ID, body=dict(
            answerQueue=[
                dict(
                    synced=False,
                    uri=bAlloc['questions'][0]['uri'],
                    question_type='usergenerated',
                    question_id=self.getJson(bAlloc['questions'][0]['uri'], user=USER_B_ID)['question_id'],
                    selected_answer=1,
                    student_answer=dict(
                        rating=75,
                        comments="Don't know much about zork",
                    ),
                    quiz_time=1377000000,
                    answer_time=1377000010,
                    grade_after=0.1,
                ),
            ],
        ))
        qns = qnsByType(bAlloc['questions'][0]['uri'], user=USER_B_ID)
        self.assertTrue(qns.keys(), ['template'])

        # Keep on writing questions, will eventually hit cap
        aAlloc = self.getJson('http://nohost/plone/dept1/tmpltut/tmpllec/@@quizdb-sync', user=USER_A_ID, body=dict(
            answerQueue=[
                dict(
                    synced=False,
                    uri=aAlloc['questions'][0]['uri'],
                    student_answer=dict(
                        text=u"Here's to us!",
                        choices=[
                            dict(answer="Course you do", correct=True),
                            dict(answer="No thanks", correct=False),
                        ],
                        explanation=u'So you can get the keys',
                    ),
                    correct=True,
                    quiz_time=1377000000,
                    answer_time=1377000010,
                    grade_after=0.1,
                ),
            ],
        ))
        self.assertTrue(qnsByType(aAlloc['questions'][0]['uri'], user=USER_A_ID).keys(), ['template'])
        aAlloc = self.getJson('http://nohost/plone/dept1/tmpltut/tmpllec/@@quizdb-sync', user=USER_A_ID, body=dict(
            answerQueue=[
                dict(
                    synced=False,
                    uri=aAlloc['questions'][0]['uri'],
                    student_answer=dict(
                        text=u"Damn Few!",
                        choices=[
                            dict(answer="Course you do", correct=True),
                            dict(answer="No thanks", correct=False),
                        ],
                        explanation=u'So you can get the keys',
                    ),
                    correct=True,
                    quiz_time=1377000000,
                    answer_time=1377000010,
                    grade_after=0.1,
                ),
            ],
        ))
        self.assertTrue(
            self.getJson(aAlloc['questions'][0]['uri'], user=USER_A_ID, expectedStatus=400),
            u'User has written 3 questions already')

        # B, C & D are still going
        self.assertEqual(set(qn['text'] for qn in qnsByType(bAlloc['questions'][0]['uri'], user=USER_B_ID)['usergenerated']), set([
            u'<div class="parse-as-tex">Damn Few!</div>',
            u'<div class="parse-as-tex">Here\'s to us!</div>',
            # NB: Already answered first question
        ]))
        self.assertEqual(set(qn['text'] for qn in qnsByType(cAlloc['questions'][0]['uri'], user=USER_C_ID, loops=40)['usergenerated']), set([
            u'<div class="parse-as-tex">Damn Few!</div>',
            u'<div class="parse-as-tex">Here\'s to us!</div>',
            u'<div class="parse-as-tex">Want some rye?</div>',
        ]))
        self.assertEqual(set(qn['text'] for qn in qnsByType(dAlloc['questions'][0]['uri'], user=USER_D_ID, loops=40)['usergenerated']), set([
            u'<div class="parse-as-tex">Damn Few!</div>',
            u'<div class="parse-as-tex">Here\'s to us!</div>',
            u'<div class="parse-as-tex">Want some rye?</div>',
        ]))

        # If C answers first question too, then nobody gets to take it.
        qn = [qn for qn in qnsByType(cAlloc['questions'][0]['uri'], user=USER_C_ID)['usergenerated'] if 'rye?' in qn['text']][0]
        cAlloc = self.getJson('http://nohost/plone/dept1/tmpltut/tmpllec/@@quizdb-sync', user=USER_C_ID, body=dict(
            answerQueue=[
                dict(
                    synced=False,
                    uri=qn['uri'],
                    question_type='usergenerated',
                    question_id=qn['question_id'],
                    selected_answer=1,
                    student_answer=dict(
                        rating=0,
                        comments="Really easy",
                    ),
                    quiz_time=1377000000,
                    answer_time=1377000010,
                    grade_after=0.1,
                ),
            ],
        ))
        self.assertEqual(set(qn['text'] for qn in qnsByType(bAlloc['questions'][0]['uri'], user=USER_B_ID)['usergenerated']), set([
            u'<div class="parse-as-tex">Damn Few!</div>',
            u'<div class="parse-as-tex">Here\'s to us!</div>',
            # NB: Already answered first question
        ]))
        self.assertEqual(set(qn['text'] for qn in qnsByType(cAlloc['questions'][0]['uri'], user=USER_C_ID)['usergenerated']), set([
            u'<div class="parse-as-tex">Damn Few!</div>',
            u'<div class="parse-as-tex">Here\'s to us!</div>',
            # NB: Already answered first question
        ]))
        self.assertEqual(set(qn['text'] for qn in qnsByType(dAlloc['questions'][0]['uri'], user=USER_D_ID)['usergenerated']), set([
            u'<div class="parse-as-tex">Damn Few!</div>',
            u'<div class="parse-as-tex">Here\'s to us!</div>',
            # NB: Haven't answered first, but hit review cap
        ]))

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
