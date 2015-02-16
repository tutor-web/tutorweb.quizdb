import random
import transaction
from zope.testing.loggingsupport import InstalledHandler

from plone.app.testing import login

from ..browser.sync import DEFAULT_QUESTION_CAP
from .base import FunctionalTestCase, IntegrationTestCase
from .base import USER_A_ID, USER_B_ID, USER_C_ID, MANAGER_ID

def uniDict(**kwargs):
    def unicodify(o):
        if isinstance(o, str):
            return unicode(o)
        return o

    return dict(
        (unicodify(k), unicodify(v))
        for k, v in kwargs.items()
    )


class SyncViewIntegration(IntegrationTestCase):
    def test_getStudentSettings(self):
        """Can get student, and parameters get set if required"""
        def getSettings(userId=USER_A_ID, lecSettings=None, tutSettings=None):
            def toList(d):
                # Bodge actual dicts into what we're storing.
                return [dict(key=k, value=v) for (k, v) in d.items()]

            portal = self.layer['portal']
            if lecSettings:
                portal.restrictedTraverse('dept1/tut1/lec1').settings = toList(lecSettings)
                transaction.commit()
            if tutSettings:
                portal.restrictedTraverse('dept1/tut1').settings = toList(tutSettings)
                transaction.commit()
            login(portal, userId)
            view = portal.restrictedTraverse('dept1/tut1/lec1/@@quizdb-sync')
            student = view.getCurrentStudent()
            self.assertEqual(student.userName, userId)
            settings = view.getStudentSettings(student)

            # Should never leak :min and :max
            self.assertEqual([k for k in settings.keys() if ':min' in k], [])
            self.assertEqual([k for k in settings.keys() if ':max' in k], [])

            return settings

        # Get no settings when none are set
        self.assertEquals(
            getSettings(),
            dict(),
        )

        # Lecture settings override tutorial settings
        self.assertEquals(
            getSettings(
                tutSettings=dict(hist_sel='0.5'),
                lecSettings=dict(),
            ),
            dict(hist_sel='0.5'),
        )
        self.assertEquals(
            getSettings(
                tutSettings=dict(hist_sel='0.5'),
                lecSettings=dict(hist_sel='0.3'),
            ),
            dict(hist_sel='0.3'),
        )

        # Random items can be generated between ranges
        alpha = {}
        for userId in [USER_A_ID, USER_B_ID, USER_C_ID]:
            alpha[userId] = getSettings(lecSettings={
                'grade_alpha:min': '0.3',
                'grade_alpha:max': '0.5',
            }, userId=userId)['grade_alpha']

        self.assertTrue(alpha[USER_A_ID] != alpha[USER_B_ID]
            or alpha[USER_A_ID] != alpha[USER_C_ID]
            or alpha[USER_B_ID] != alpha[USER_C_ID])

        for userId in [USER_A_ID, USER_B_ID, USER_C_ID]:
            self.assertTrue(isinstance(alpha[userId], basestring))
            self.assertTrue(float(alpha[userId]) >= 0.3)
            self.assertTrue(float(alpha[userId]) <= 0.5)

        # Fetching again results in the same value
        for userId in [USER_A_ID, USER_B_ID, USER_C_ID] * 10:
            self.assertEqual(
                alpha[userId],
                getSettings(lecSettings={
                    'grade_alpha:min': '0.3',
                    'grade_alpha:max': '0.5',
                }, userId=userId)['grade_alpha']
            )

        # As S is an integer column, should get back int values.
        s = {}
        for userId in [USER_A_ID, USER_B_ID, USER_C_ID]:
            s[userId] = getSettings(lecSettings={
                'grade_s:max': '90',  # NB: no min, assume 0
            }, userId=userId)['grade_s']

        self.assertTrue(s[USER_A_ID] != s[USER_B_ID]
            or s[USER_A_ID] != s[USER_C_ID]
            or s[USER_B_ID] != s[USER_C_ID])

        for userId in [USER_A_ID, USER_B_ID, USER_C_ID]:
            self.assertTrue(isinstance(s[userId], basestring))
            self.assertEqual(int(s[userId]), float(s[userId]))
            self.assertTrue(int(s[userId]) >= 0)
            self.assertTrue(int(s[userId]) <= 90)

        # Keeping the same range means we get the same value back
        for userId in [USER_A_ID, USER_B_ID, USER_C_ID] * 10:
            self.assertEqual(
                s[userId],
                getSettings(lecSettings={
                    'grade_s:max': '90',
                }, userId=userId)['grade_s']
            )

        # Changing range causes new value to be assigned
        s2 = {}
        for userId in [USER_A_ID, USER_B_ID, USER_C_ID]:
            s2[userId] = getSettings(lecSettings={
                'grade_s:min': '91',
                'grade_s:max': '99',
            }, userId=userId)['grade_s']
            self.assertNotEqual(s[userId], s2[userId])
            self.assertTrue(91 <= int(s2[userId]) <= 99)

        # But still keep getting the same value back
        for userId in [USER_A_ID, USER_B_ID, USER_C_ID] * 10:
            self.assertEqual(
                s2[userId],
                getSettings(lecSettings={
                    'grade_s:max': '91',
                    'grade_s:max': '99',
                }, userId=userId)['grade_s']
            )

class SyncViewFunctional(FunctionalTestCase):
    maxDiff = None

    def setUp(self):
        self.loghandlers = dict(
            sqlalchemy=InstalledHandler('sqlalchemy.engine'),
            sync=InstalledHandler('tutorweb.quizdb.sync')
        )

    def logs(self, name='sqlalchemy'):
        return [x.getMessage() for x in self.loghandlers[name].records]

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
        self.assertEquals(aAlloc['slide_uri'], u'http://nohost/plone/dept1/tut1/lec1/slide-html')
        self.assertEquals(aAlloc['user'], u'Arnold')
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
        self.assertEquals(aAlloc2['slide_uri'], u'http://nohost/plone/dept1/tut1/lec2/slide-html')
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
        self.assertEquals(bAlloc['user'], u'Betty')
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

    def test_adddelete(self):
        """Allocate some questions"""
        portal = self.layer['portal']

        # Start with 2 questions
        aAlloc = self.getJson('http://nohost/plone/dept1/tut1/lec1/@@quizdb-sync', user=USER_A_ID)
        self.assertEquals(
            sorted([self.getJson(qn['uri'])['title'] for qn in aAlloc['questions']]),
            [u'Unittest D1 T1 L1 Q1', u'Unittest D1 T1 L1 Q2'],
        )

        # Add a question3 & 4, appears in sync call
        login(portal, MANAGER_ID)
        portal['dept1']['tut1']['lec1'].invokeFactory(
            type_name="tw_latexquestion",
            id="qn3",
            title="Unittest D1 T1 L1 Q3",
            text=self.rtv("How is this question?"),
            choices=[
                dict(text="Good?", correct=False),
                dict(text="Bad?", correct=True),
                dict(text="Ugly?", correct=False),
            ],
        )
        portal['dept1']['tut1']['lec1'].invokeFactory(
            type_name="tw_latexquestion",
            id="qn4",
            title="Unittest D1 T1 L1 Q4",
        )
        transaction.commit()
        aAlloc = self.getJson('http://nohost/plone/dept1/tut1/lec1/@@quizdb-sync', user=USER_A_ID)
        aQuestions = dict((self.getJson(qn['uri'])['title'], qn['uri']) for qn in aAlloc['questions'])
        self.assertEquals(
            sorted(aQuestions.keys()),
            [u'Unittest D1 T1 L1 Q1', u'Unittest D1 T1 L1 Q2', u'Unittest D1 T1 L1 Q3', u'Unittest D1 T1 L1 Q4'],
        )
        self.assertEquals(aAlloc['removed_questions'], [])

        # Keep this version of question 3
        qn3 = aQuestions[u'Unittest D1 T1 L1 Q3']

        # Delete question3, doesn't appear in sync
        browser = self.getBrowser('http://nohost/plone/dept1/tut1/lec1/qn3/delete_confirmation', user=MANAGER_ID)
        browser.getControl('Delete').click()
        aAlloc = self.getJson('http://nohost/plone/dept1/tut1/lec1/@@quizdb-sync', user=USER_A_ID)
        aQuestions = dict((self.getJson(qn['uri'])['title'], qn['uri']) for qn in aAlloc['questions'])
        self.assertEquals(
            sorted([self.getJson(qn['uri'])['title'] for qn in aAlloc['questions']]),
            [u'Unittest D1 T1 L1 Q1', u'Unittest D1 T1 L1 Q2', u'Unittest D1 T1 L1 Q4'],
        )
        self.assertEquals(aAlloc['removed_questions'], [qn3])

        # Gone completely second time around
        aAlloc = self.getJson('http://nohost/plone/dept1/tut1/lec1/@@quizdb-sync', user=USER_A_ID)
        self.assertEquals(
            sorted([self.getJson(qn['uri'])['title'] for qn in aAlloc['questions']]),
            [u'Unittest D1 T1 L1 Q1', u'Unittest D1 T1 L1 Q2', u'Unittest D1 T1 L1 Q4'],
        )
        self.assertEquals(aAlloc['removed_questions'], [])

        # Recreate it - gets removed and re-added under a different allocation
        portal['dept1']['tut1']['lec1'].invokeFactory(
            type_name="tw_latexquestion",
            id="qn3",
            title="Unittest D1 T1 L1 Q3",
            text=self.rtv("How is this question?"),
            choices=[
                dict(text="Good?", correct=False),
                dict(text="Bad?", correct=True),
                dict(text="Ugly?", correct=False),
            ],
        )
        transaction.commit()
        aAlloc = self.getJson('http://nohost/plone/dept1/tut1/lec1/@@quizdb-sync', user=USER_A_ID)
        aQuestions = dict((self.getJson(qn['uri'])['title'], qn['uri']) for qn in aAlloc['questions'])
        self.assertEquals(
            sorted(aQuestions.keys()),
            [u'Unittest D1 T1 L1 Q1', u'Unittest D1 T1 L1 Q2', u'Unittest D1 T1 L1 Q3', u'Unittest D1 T1 L1 Q4'],
        )
        self.assertEquals(aAlloc['removed_questions'], [])
        self.assertNotEquals(aQuestions[u'Unittest D1 T1 L1 Q3'], qn3)

        # Keep this version of question 3
        qn3a = aQuestions[u'Unittest D1 T1 L1 Q3']

        # Try updating it, should cause the old one to be removed and a new one added
        portal['dept1']['tut1']['lec1']['qn3'].title = u'Unittest D1 T1 L1 Q3b'
        portal['dept1']['tut1']['lec1']['qn3'].reindexObject()
        transaction.commit()
        aAlloc = self.getJson('http://nohost/plone/dept1/tut1/lec1/@@quizdb-sync', user=USER_A_ID)
        aQuestions = dict((self.getJson(qn['uri'])['title'], qn['uri']) for qn in aAlloc['questions'])
        self.assertEquals(
            sorted(aQuestions.keys()),
            [u'Unittest D1 T1 L1 Q1', u'Unittest D1 T1 L1 Q2', u'Unittest D1 T1 L1 Q3b', u'Unittest D1 T1 L1 Q4'],
        )
        self.assertEquals(aAlloc['removed_questions'], [qn3a])
        self.assertNotEquals(aQuestions[u'Unittest D1 T1 L1 Q3b'], qn3)
        self.assertNotEquals(aQuestions[u'Unittest D1 T1 L1 Q3b'], qn3a)

        # Keep this version of question 3
        qn3b = aQuestions[u'Unittest D1 T1 L1 Q3b']

        # Can answer all versions of qn3.
        aAlloc = self.getJson('http://nohost/plone/dept1/tut1/lec1/@@quizdb-sync', user=USER_A_ID, body=dict(
            answerQueue=[
                dict(
                    synced=False,
                    uri=qn3,
                    student_answer=0,
                    correct='wibble',
                    quiz_time=1377000000,
                    answer_time=1377000005,
                    grade_after=0.1,
                ),
                dict(
                    synced=False,
                    uri=qn3a,
                    student_answer=1,
                    correct='wibble',
                    quiz_time=1377000010,
                    answer_time=1377000015,
                    grade_after=0.1,
                ),
                dict(
                    synced=False,
                    uri=qn3b,
                    student_answer=2,
                    correct='wibble',
                    quiz_time=1377000020,
                    answer_time=1377000025,
                    grade_after=0.1,
                ),
            ],
        ))
        self.assertEquals(
            [a['quiz_time'] for a in aAlloc['answerQueue']],
            [1377000000, 1377000010, 1377000020],
        )

    def test_settings(self):
        """Make sure settings are inherited from tutorial"""
        def toList(d):
            # Bodge actual dicts into what we're storing.
            return [dict(key=k, value=v) for (k, v) in d.items()]

        portal = self.layer['portal']

        portal['dept1']['tut1'].settings = [
            dict(key='hist_sel', value='0.8'),
            dict(key='value_a', value='z'),
            dict(key='value_a', value='x'),
            dict(key='value_b', value='x'),
        ]
        portal['dept1']['tut1']['lec1'].settings = toList(dict(
            value_b='y',
            value_c='y',
        ))
        transaction.commit()
        aAlloc = self.getJson('http://nohost/plone/dept1/tut1/lec1/@@quizdb-sync', user=USER_A_ID)
        self.assertEqual(aAlloc['settings'], dict(
            hist_sel='0.8',
            value_a='x',
            value_b='y',
            value_c='y',
        ))

        # Still works if lecture is None
        portal['dept1']['tut1'].settings = toList(dict(
            hist_sel='0.8',
            value_a='x',
            value_b='x',
        ))
        portal['dept1']['tut1']['lec1'].settings = None
        transaction.commit()
        aAlloc = self.getJson('http://nohost/plone/dept1/tut1/lec1/@@quizdb-sync', user=USER_A_ID)
        self.assertEqual(aAlloc['settings'], dict(
            hist_sel='0.8',
            value_a='x',
            value_b='x',
        ))

        # Still works if tutorial is none
        portal['dept1']['tut1'].settings = None
        portal['dept1']['tut1']['lec1'].settings = toList(dict(
            value_b='y',
            value_c='y',
        ))
        transaction.commit()
        aAlloc = self.getJson('http://nohost/plone/dept1/tut1/lec1/@@quizdb-sync', user=USER_A_ID)
        self.assertEqual(aAlloc['settings'], dict(
            value_b='y',
            value_c='y',
        ))

    def test_answerQueuePersistent(self):
        """Make sure answerQueue gets logged and is returned"""
        def getLectureStats():
            lec1 = self.layer['portal']['dept1']['tut1']['lec1']
            return dict(
                answered=lec1['qn1'].timesanswered + lec1['qn2'].timesanswered,
                correct=lec1['qn1'].timescorrect + lec1['qn2'].timescorrect,
            )
        # Allocate to user A
        aAlloc = self.getJson('http://nohost/plone/dept1/tut1/lec1/@@quizdb-sync', user=USER_A_ID)
        aQuestions = dict((self.getJson(qn['uri'])['title'], qn['uri']) for qn in aAlloc['questions'])
        self.assertEquals(sorted(aQuestions.keys()), [u'Unittest D1 T1 L1 Q1', u'Unittest D1 T1 L1 Q2'])
        statsBefore = getLectureStats()

        # Write some answers back
        aAlloc = self.getJson('http://nohost/plone/dept1/tut1/lec1/@@quizdb-sync', user=USER_A_ID, body=dict(
            user='Arnold',
            answerQueue=[
                dict(
                    synced=False,
                    uri=aQuestions[u'Unittest D1 T1 L1 Q1'],
                    student_answer=0,
                    correct='wibble',
                    quiz_time=1377000000,
                    answer_time=1377000010,
                    grade_after=0.1,
                ),
                dict(
                    synced=False,
                    uri=aQuestions[u'Unittest D1 T1 L1 Q2'],
                    student_answer=99,
                    correct=False,
                    quiz_time=1377000020,
                    answer_time=1377000030,
                    grade_after=0.2,
                ),
                dict(
                    synced=False,
                    uri=aQuestions[u'Unittest D1 T1 L1 Q2'],
                    student_answer=2,
                    correct=True,
                    quiz_time=1377000020,
                    answer_time=1377000030,
                    grade_after=0.3,
                ),
            ],
        ))

        # Noticed that middle item wasn't correct
        self.assertEqual(self.logs('sync'), ['Student answer 99 out of range'])
        # Returned answerQueue without dodgy answer
        self.assertEqual(aAlloc['answerQueue'], [
            {
                u'synced': True,
                u'student_answer': 0,
                u'correct': False,
                u'quiz_time': 1377000000,
                u'answer_time': 1377000010,
                u'grade_after': 0.1,
            },
            {
                u'synced': True,
                u'student_answer': 2,
                u'correct': True,
                u'quiz_time': 1377000020,
                u'answer_time': 1377000030,
                u'grade_after': 0.3,
                u'lec_answered': 2,
                u'lec_correct': 1,
                u'practice_answered': 0,
                u'practice_correct': 0,
            },
        ])

        # Question stats have been updated
        statsAfter = getLectureStats()
        self.assertEqual(statsBefore['answered'] + 2, statsAfter['answered'])
        self.assertEqual(statsBefore['correct'] + 1, statsAfter['correct'])

        # Fetching again returns the same queue
        aAlloc = self.getJson('http://nohost/plone/dept1/tut1/lec1/@@quizdb-sync', user=USER_A_ID)
        self.assertEqual(aAlloc['answerQueue'], [
            {
                u'synced': True,
                u'student_answer': 0,
                u'correct': False,
                u'quiz_time': 1377000000,
                u'answer_time': 1377000010,
                u'grade_after': 0.1,
            },
            {
                u'synced': True,
                u'student_answer': 2,
                u'correct': True,
                u'quiz_time': 1377000020,
                u'answer_time': 1377000030,
                u'grade_after': 0.3,
                u'lec_answered': 2,
                u'lec_correct': 1,
                u'practice_answered': 0,
                u'practice_correct': 0,
            },
        ])

        # Writing a third time updates totals
        aAlloc = self.getJson('http://nohost/plone/dept1/tut1/lec1/@@quizdb-sync', user=USER_A_ID, body=dict(
            user='Arnold',
            answerQueue=[
                dict(
                    synced=False,
                    uri=aQuestions[u'Unittest D1 T1 L1 Q2'],
                    student_answer=2,
                    correct=False,  # NB: Sending back false even though question is really true
                    quiz_time=1377000040,
                    answer_time=1377000050,
                    grade_after=0.1,
                ),
            ]
        ))
        self.assertEqual(len(aAlloc['answerQueue']), 3)
        self.assertEqual(aAlloc['answerQueue'][-1]['answer_time'], 1377000050)
        self.assertEqual(aAlloc['answerQueue'][-1]['lec_answered'], 3)
        self.assertEqual(aAlloc['answerQueue'][-1]['lec_correct'], 2)
        self.assertEqual(aAlloc['answerQueue'][-1]['practice_answered'], 0)
        self.assertEqual(aAlloc['answerQueue'][-1]['practice_correct'], 0)
        self.assertEqual(aAlloc['answerQueue'][-1]['correct'], True)

        # Writing an empty answer is still synced
        aAlloc = self.getJson('http://nohost/plone/dept1/tut1/lec1/@@quizdb-sync', user=USER_A_ID, body=dict(
            user='Arnold',
            answerQueue=[
                dict(
                    synced=False,
                    uri=aQuestions[u'Unittest D1 T1 L1 Q2'],
                    student_answer=None,
                    correct=False,  # NB: Sending back false even though question is really true
                    quiz_time=1377000050,
                    answer_time=1377000060,
                    grade_after=0.1,
                ),
            ]
        ))
        self.assertEqual(len(aAlloc['answerQueue']), 4)
        self.assertEqual(aAlloc['answerQueue'][-1]['answer_time'], 1377000060)
        self.assertEqual(aAlloc['answerQueue'][-1]['lec_answered'], 4)
        self.assertEqual(aAlloc['answerQueue'][-1]['lec_correct'], 2)
        self.assertEqual(aAlloc['answerQueue'][-1]['practice_answered'], 0)
        self.assertEqual(aAlloc['answerQueue'][-1]['practice_correct'], 0)
        self.assertEqual(aAlloc['answerQueue'][-1]['correct'], False)

    def test_answerQueueIsolation(self):
        """Make sure answerQueues for students and lectures are separate"""
        # Allocate to user A
        aAlloc = self.getJson('http://nohost/plone/dept1/tut1/lec1/@@quizdb-sync', user=USER_A_ID)
        aQuestions = dict((self.getJson(qn['uri'])['title'], qn['uri']) for qn in aAlloc['questions'])
        self.assertEquals(sorted(aQuestions.keys()), [u'Unittest D1 T1 L1 Q1', u'Unittest D1 T1 L1 Q2'])

        # Write some answers back
        aAlloc = self.getJson('http://nohost/plone/dept1/tut1/lec1/@@quizdb-sync', user=USER_A_ID, body=dict(
            answerQueue=[
                dict(
                    synced=False,
                    uri=aQuestions[u'Unittest D1 T1 L1 Q1'],
                    student_answer=0,
                    correct='wibble',
                    quiz_time=1377000000,
                    answer_time=1377000010,
                    grade_after=0.1,
                ),
                dict(
                    synced=False,
                    uri=aQuestions[u'Unittest D1 T1 L1 Q2'],
                    student_answer=2,
                    correct=True,
                    quiz_time=1377000020,
                    answer_time=1377000030,
                    grade_after=0.3,
                ),
            ],
        ))

        # Get user B, has no answers yet.
        bAlloc = self.getJson('http://nohost/plone/dept1/tut1/lec1/@@quizdb-sync', user=USER_B_ID)
        self.assertEquals(bAlloc['answerQueue'], [
        ])
        bQuestions = dict((self.getJson(qn['uri'], user=USER_B_ID)['title'], qn['uri']) for qn in bAlloc['questions'])

        # Write some answers back, can only write back B's allocation
        bAlloc = self.getJson('http://nohost/plone/dept1/tut1/lec1/@@quizdb-sync', user=USER_B_ID, body=dict(
            user='Betty',
            answerQueue=[
                dict(
                    synced=False,
                    uri=aQuestions[u'Unittest D1 T1 L1 Q1'],
                    student_answer=0,
                    correct=True,
                    quiz_time=1377000040,
                    answer_time=1377000050,
                    grade_after=0.3,
                ),
                dict(
                    synced=False,
                    uri=bQuestions[u'Unittest D1 T1 L1 Q1'],
                    student_answer=0,
                    correct=True,
                    quiz_time=1377000041,
                    answer_time=1377000051,
                    grade_after=0.3,
                ),
            ],
        ))
        self.assertEquals(len(bAlloc['answerQueue']), 1)
        self.assertEquals(bAlloc['answerQueue'][0]['quiz_time'], 1377000041)
        self.assertTrue((
            u'No record of allocation %s for student Betty'
            % aQuestions[u'Unittest D1 T1 L1 Q1'].replace('http://nohost/plone/quizdb-get-question/', '')
        ) in self.logs('sync'))

        # A doesn't see B's answer
        aAlloc = self.getJson('http://nohost/plone/dept1/tut1/lec1/@@quizdb-sync', user=USER_A_ID)
        self.assertEqual(aAlloc['answerQueue'], [
            {
                u'synced': True,
                u'student_answer': 0,
                u'correct': False,
                u'quiz_time': 1377000000,
                u'answer_time': 1377000010,
                u'grade_after': 0.1,
            },
            {
                u'synced': True,
                u'student_answer': 2,
                u'correct': True,
                u'quiz_time': 1377000020,
                u'answer_time': 1377000030,
                u'grade_after': 0.3,
                u'lec_answered': 2,
                u'lec_correct': 1,
                u'practice_answered': 0,
                u'practice_correct': 0,
            },
        ])

        # A can't write back answers for B
        bAlloc = self.getJson('http://nohost/plone/dept1/tut1/lec1/@@quizdb-sync', user=USER_A_ID, body=dict(
            user='Betty',
            answerQueue=[
                dict(
                    synced=False,
                    uri=aQuestions[u'Unittest D1 T1 L1 Q1'],
                    student_answer=2,
                    correct=True,
                    quiz_time=1377000060,
                    answer_time=1377000070,
                    grade_after=0.3,
                ),
            ],
        ), expectedStatus=403)
        bAlloc = self.getJson('http://nohost/plone/dept1/tut1/lec1/@@quizdb-sync', user=USER_B_ID)
        self.assertEquals(len(bAlloc['answerQueue']), 1)
        self.assertEquals(bAlloc['answerQueue'][0]['quiz_time'], 1377000041)

    def test_answerQueueTutorial(self):
        """Make sure answerQueues for entire tutorials get synced"""
        # Allocate tutorial to user A
        tutAlloc = self.getJson('http://nohost/plone/dept1/tut1/@@quizdb-sync', user=USER_A_ID)
        tutQuestions = [dict((self.getJson(qn['uri'])['title'], qn['uri']) for qn in aAlloc['questions']) for aAlloc in tutAlloc['lectures']]
        self.assertEquals(len(tutAlloc['lectures']), 2)
        self.assertEquals(
            sorted(tutQuestions[0].keys()),
            [u'Unittest D1 T1 L1 Q1', u'Unittest D1 T1 L1 Q2'],
        )
        self.assertEquals(
            sorted(tutQuestions[1].keys()),
            [u'Unittest D1 T1 L2 Q1', u'Unittest D1 T1 L2 Q2'],
        )

        #TODO: Create lecture here, to confuse it.

        # Write answers back to both lectures simultaneously
        tutAlloc = self.getJson('http://nohost/plone/dept1/tut1/@@quizdb-sync', user=USER_A_ID, body=dict(
            lectures=[
                dict(uri=tutAlloc['lectures'][0]['uri'], answerQueue=[
                    dict(
                        synced=False,
                        uri=tutQuestions[0][u'Unittest D1 T1 L1 Q1'],
                        student_answer=0,
                        correct='wibble',
                        quiz_time=1379900000,
                        answer_time=1379900010,
                        grade_after=0.1,
                    ),
                ]),
                dict(uri=tutAlloc['lectures'][1]['uri'], answerQueue=[
                    dict(
                        synced=False,
                        uri=tutQuestions[1][u'Unittest D1 T1 L2 Q1'],
                        student_answer=0,
                        correct='wibble',
                        quiz_time=1373300020,
                        answer_time=1373300030,
                        grade_after=0.1,
                    ),
                ]),
            ],
        ))
        self.assertEquals(
            [a['answer_time'] for a in tutAlloc['lectures'][0]['answerQueue']],
            [1379900010],
        )
        self.assertEquals(
            [a['answer_time'] for a in tutAlloc['lectures'][1]['answerQueue']],
            [1373300030],
        )

        # Will see results when syncing just one lecture too
        aAlloc = self.getJson('http://nohost/plone/dept1/tut1/lec1/@@quizdb-sync', user=USER_A_ID, body=dict())
        self.assertEquals(
            [a['answer_time'] for a in aAlloc['answerQueue']],
            [1379900010],
        )

    def test_answerQueueUgQuestions(self):
        """User generated questions are stored too"""
        def createQuestionTemplates(obj, count):
            if not hasattr(self, 'createdTmplQns'):
                self.createdTmplQns = 0
            for i in xrange(count):
                obj.invokeFactory(
                    type_name="tw_questiontemplate",
                    id="tmplqn%d" % (self.createdTmplQns + i),
                    title="Unittest tmpllec tmplQ%d" % (self.createdTmplQns + i),
                )
            self.createdTmplQns = count
            import transaction ; transaction.commit()

        portal = self.layer['portal']
        login(portal, MANAGER_ID)

        # Create a lecture with more questions than capped
        portal['dept1'].invokeFactory(
            type_name="tw_tutorial",
            id="tmpltut",
            title=u"Tutorial with a question cap of 5",
            settings=[
                dict(key='question_cap', value='5'),
                dict(key='prob_template_eval', value='0'),
            ],
        )
        portal['dept1']['tmpltut'].invokeFactory(
            type_name="tw_lecture",
            id="tmpllec",
            title=u"Lecture with no question cap (but uses default of 5)",
        )
        createQuestionTemplates(portal['dept1']['tmpltut']['tmpllec'], 5)

        # Allocate to user A
        aAlloc = self.getJson('http://nohost/plone/dept1/tmpltut/tmpllec/@@quizdb-sync', user=USER_A_ID)
        aQuestions = dict((self.getJson(qn['uri'])['title'], qn['uri']) for qn in aAlloc['questions'])
        self.assertEquals(
            sorted(aQuestions.keys()),
            [u'Unittest tmpllec tmplQ%d' % i for i in range(0,5)],
        )

        # Write some answers back
        aAlloc = self.getJson('http://nohost/plone/dept1/tmpltut/tmpllec/@@quizdb-sync', user=USER_A_ID, body=dict(
            answerQueue=[
                dict(
                    synced=False,
                    uri=aQuestions[u'Unittest tmpllec tmplQ0'],
                    student_answer=dict(
                        text=u"My first question",
                        explanation=u"I'm getting the hang of it",
                        choices=[dict(answer="Good?", correct=True), dict(answer="Bad?", correct=False)],
                    ),
                    correct=True,
                    quiz_time=1377000000,
                    answer_time=1377000010,
                    grade_after=0.1,
                ),
                dict(
                    synced=False,
                    uri=aQuestions[u'Unittest tmpllec tmplQ1'],
                    student_answer=dict(
                        text=u"I bottled it",
                    ),
                    correct=False,
                    quiz_time=1377000020,
                    answer_time=1377000030,
                    grade_after=0.3,
                ),
                dict(
                    synced=False,
                    uri=aQuestions['Unittest tmpllec tmplQ2'],
                    student_answer=dict(
                        text=u"My second question",
                        explanation=u"I'm getting better!",
                        choices=[dict(answer="Good?", correct=True), dict(answer="Bad?", correct=False)],
                    ),
                    correct=True,
                    quiz_time=1377000000,
                    answer_time=1377000040,
                    grade_after=0.1,
                ),
            ],
        ))
        # Answers have been replaced by question IDs (if they were "correct")
        self.assertEquals(
            [[x['correct'], x['student_answer']] for x in aAlloc['answerQueue']],
            [[True, 1], [False, None], [True, 2]],
            )

        # Allocate to user B
        bAlloc = self.getJson('http://nohost/plone/dept1/tmpltut/tmpllec/@@quizdb-sync', user=USER_B_ID)
        bQuestions = dict((self.getJson(qn['uri'], user=USER_B_ID)['title'], qn['uri']) for qn in bAlloc['questions'])
        self.assertEquals(
            sorted(bQuestions.keys()),
            [u'Unittest tmpllec tmplQ%d' % i for i in range(0,5)],
        )

        # Write some answers back
        bAlloc = self.getJson('http://nohost/plone/dept1/tmpltut/tmpllec/@@quizdb-sync', user=USER_B_ID, body=dict(
            answerQueue=[
                dict(
                    synced=False,
                    uri=bQuestions[u'Unittest tmpllec tmplQ0'],
                    student_answer=dict(
                        text=u"My first question",
                        explanation=u"I'm way better than Arthur",
                        choices=[dict(answer="Good?", correct=True), dict(answer="Bad?", correct=False)],
                    ),
                    correct=True,
                    quiz_time=1377000000,
                    answer_time=1377000010,
                    grade_after=0.1,
                ),
            ],
        ))
        # IDs are global, since everything is going in one table
        self.assertEquals(
            [[x['correct'], x['student_answer']] for x in bAlloc['answerQueue']],
            [[True, 3]],
            )

        # Rewrite a question
        aAlloc = self.getJson('http://nohost/plone/dept1/tmpltut/tmpllec/@@quizdb-sync', user=USER_A_ID, body=dict(
            answerQueue=[
                dict(
                    synced=False,
                    uri="%s?author_qn=yes&question_id=%d" % (
                        aQuestions[u'Unittest tmpllec tmplQ0'],
                        aAlloc['answerQueue'][0]['student_answer'],
                    ),
                    student_answer=dict(
                        text=u"My first question, again",
                        explanation=u"I'm much better now",
                        choices=[dict(answer="Good?", correct=True), dict(answer="Bad?", correct=False)],
                    ),
                    correct=True,
                    quiz_time=1377000000,
                    answer_time=1377000010,
                    grade_after=0.1,
                ),
            ],
        ))

        # Old one should be marked as superseded
        self.assertEquals([[r['verdict'], r['text']] for r in self.getJson('http://nohost/plone/dept1/tmpltut/tmpllec/@@quizdb-review-ugqn', user=USER_A_ID)], [
            [-2, u'<div class="parse-as-tex">My first question</div>'],
            [None, u'<div class="parse-as-tex">My second question</div>'],
            [None, u'<div class="parse-as-tex">My first question, again</div>'],
        ])

    def test_answerQueue_getCoinAward(self):
        """Questions should get a suitable award"""
        # Shortcut for making answerQueue entries
        aqTime = [1377000000]
        def aqEntry(alloc, qnIndex, correct, grade_after, practice=False):
            qnData = self.getJson(alloc['questions'][qnIndex]['uri'], user=alloc['user'])
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
                practice=practice,
            )

        # Add extra lecture
        portal = self.layer['portal']
        login(portal, MANAGER_ID)
        portal['dept1']['tut1'].invokeFactory(
            type_name="tw_lecture",
            id="tmplec3",
            title=u"Lecture three",
        )
        portal['dept1']['tut1']['tmplec3'].invokeFactory(
            type_name="tw_latexquestion",
            id="qn0",
            title="Unittest tmplec Q0",
            choices=[dict(text="orange", correct=False), dict(text="green", correct=True)],
            finalchoices=[],
        )
        transaction.commit()

        # Get an allocation to start things off
        lec1Alloc = self.getJson('http://nohost/plone/dept1/tut1/lec1/@@quizdb-sync', user=USER_A_ID)

        # Get 5 right, no points
        lec1Alloc = self.getJson('http://nohost/plone/dept1/tut1/lec1/@@quizdb-sync', user=USER_A_ID, body=dict(
            user='Arnold',
            answerQueue=[
                aqEntry(lec1Alloc, 0, True, 0.1),
                aqEntry(lec1Alloc, 0, True, 0.2),
                aqEntry(lec1Alloc, 0, True, 0.3),
                aqEntry(lec1Alloc, 0, True, 0.4),
                aqEntry(lec1Alloc, 0, True, 0.5),
            ],
        ))
        self.assertEqual(
            self.getJson('http://nohost/plone/@@quizdb-student-award', user=USER_A_ID),
            dict(walletId='', history=[], tx_id=None, coin_available=0),
        )

        # Go over 5, get a point
        lec1Alloc = self.getJson('http://nohost/plone/dept1/tut1/lec1/@@quizdb-sync', user=USER_A_ID, body=dict(
            user='Arnold',
            answerQueue=[
                aqEntry(lec1Alloc, 0, True, 1.0),
                aqEntry(lec1Alloc, 0, True, 2.0),
                aqEntry(lec1Alloc, 0, True, 5.0),
                aqEntry(lec1Alloc, 0, True, 5.0),
            ],
        ))
        self.assertEqual(
            self.getJson('http://nohost/plone/@@quizdb-student-award', user=USER_A_ID),
            dict(coin_available=1000, walletId='', tx_id=None, history=[
                dict(amount=1000, claimed=False, lecture='/plone/dept1/tut1/lec1', time='2013-08-20T13:15:40'),
            ])
        )

        # 5 below cut-off, 4 above makes no difference
        lec1Alloc = self.getJson('http://nohost/plone/dept1/tut1/lec1/@@quizdb-sync', user=USER_A_ID, body=dict(
            user='Arnold',
            answerQueue=([
                aqEntry(lec1Alloc, 0, True, 4.0),
            ] * 5) + ([
                aqEntry(lec1Alloc, 0, True, 6.0),
            ] * 5),
        ))
        self.assertEqual(
            self.getJson('http://nohost/plone/@@quizdb-student-award', user=USER_A_ID),
            dict(coin_available=1000, walletId='', tx_id=None, history=[
                dict(amount=1000, claimed=False, lecture='/plone/dept1/tut1/lec1', time='2013-08-20T13:15:40'),
            ])
        )

        # Acing the lecture gets more points
        lec1Alloc = self.getJson('http://nohost/plone/dept1/tut1/lec1/@@quizdb-sync', user=USER_A_ID, body=dict(
            user='Arnold',
            answerQueue=[
                aqEntry(lec1Alloc, 0, True, 9.998),
            ],
        ))
        self.assertEqual(
            self.getJson('http://nohost/plone/@@quizdb-student-award', user=USER_A_ID),
            dict(coin_available=11000, walletId='', tx_id=None, history=[
                dict(amount=10000, claimed=False, lecture='/plone/dept1/tut1/lec1', time='2013-08-20T13:23:40'),
                dict(amount=1000,  claimed=False, lecture='/plone/dept1/tut1/lec1', time='2013-08-20T13:15:40'),
            ])
        )

        # We can't get these points again
        lec1Alloc = self.getJson('http://nohost/plone/dept1/tut1/lec1/@@quizdb-sync', user=USER_A_ID, body=dict(
            user='Arnold',
            answerQueue=[
                aqEntry(lec1Alloc, 0, False, 9.0),
                aqEntry(lec1Alloc, 0, False, 8.0),
                aqEntry(lec1Alloc, 0, True, 9.0),
                aqEntry(lec1Alloc, 0, True, 9.999999999),
                aqEntry(lec1Alloc, 0, True, 9.999999999),
                aqEntry(lec1Alloc, 0, True, 9.999999999),
                aqEntry(lec1Alloc, 0, True, 9.999999999),
            ],
        ))
        self.assertEqual(
            self.getJson('http://nohost/plone/@@quizdb-student-award', user=USER_A_ID),
            dict(coin_available=11000, walletId='', tx_id=None, history=[
                dict(amount=10000, claimed=False, lecture='/plone/dept1/tut1/lec1', time='2013-08-20T13:23:40'),
                dict(amount=1000,  claimed=False, lecture='/plone/dept1/tut1/lec1', time='2013-08-20T13:15:40'),
            ])
        )

        # Ace lec2 too and we get award for that too
        lec2Alloc = self.getJson('http://nohost/plone/dept1/tut1/lec2/@@quizdb-sync', user=USER_A_ID)
        lec2Alloc = self.getJson('http://nohost/plone/dept1/tut1/lec2/@@quizdb-sync', user=USER_A_ID, body=dict(
            user='Arnold',
            answerQueue=[
                aqEntry(lec2Alloc, 0, True, 9.999999999),
            ] * 10,
        ))
        self.assertEqual(
            self.getJson('http://nohost/plone/@@quizdb-student-award', user=USER_A_ID),
            dict(coin_available=22000, walletId='', tx_id=None, history=[
                dict(amount=11000, claimed=False, lecture='/plone/dept1/tut1/lec2', time='2013-08-20T13:39:40'),
                dict(amount=10000,  claimed=False, lecture='/plone/dept1/tut1/lec1', time='2013-08-20T13:23:40'),
                dict(amount=1000,   claimed=False, lecture='/plone/dept1/tut1/lec1', time='2013-08-20T13:15:40'),
            ])
        )

        # Ace lec3 and we get award for finshing tutorial
        tmplec3Alloc = self.getJson('http://nohost/plone/dept1/tut1/tmplec3/@@quizdb-sync', user=USER_A_ID)
        tmplec3Alloc = self.getJson('http://nohost/plone/dept1/tut1/tmplec3/@@quizdb-sync', user=USER_A_ID, body=dict(
            user='Arnold',
            answerQueue=[
                aqEntry(tmplec3Alloc, 0, True, 9.999999999),
            ] * 10,
        ))
        self.assertEqual(
            self.getJson('http://nohost/plone/@@quizdb-student-award', user=USER_A_ID),
            uniDict(coin_available=133000, walletId='', tx_id=None, history=[
                uniDict(amount=111000, claimed=False, lecture='/plone/dept1/tut1/tmplec3', time='2013-08-20T13:41:40'),
                uniDict(amount=11000, claimed=False, lecture='/plone/dept1/tut1/lec2', time='2013-08-20T13:39:40'),
                uniDict(amount=10000,  claimed=False, lecture='/plone/dept1/tut1/lec1', time='2013-08-20T13:23:40'),
                uniDict(amount=1000,   claimed=False, lecture='/plone/dept1/tut1/lec1', time='2013-08-20T13:15:40'),
            ])
        )

        # B uses practice mode, doesn't get multiple points
        lec1Alloc = self.getJson('http://nohost/plone/dept1/tut1/lec1/@@quizdb-sync', user=USER_B_ID)
        lec1Alloc = self.getJson('http://nohost/plone/dept1/tut1/lec1/@@quizdb-sync', user=USER_B_ID, body=dict(
            user='Betty',
            answerQueue=[
                aqEntry(lec1Alloc, 0, True, 1.0),
                aqEntry(lec1Alloc, 0, True, 2.0),
                aqEntry(lec1Alloc, 0, True, 3.0),
                aqEntry(lec1Alloc, 0, True, 4.0),
                aqEntry(lec1Alloc, 0, True, 5.0),
                aqEntry(lec1Alloc, 0, True, 6.0),
                aqEntry(lec1Alloc, 0, True, 7.0),
                aqEntry(lec1Alloc, 0, True, 9.999999999),
                aqEntry(lec1Alloc, 0, False, 9.999999999, practice = True),
                aqEntry(lec1Alloc, 0, False, 9.999999999, practice = True),
                aqEntry(lec1Alloc, 0, False, 9.999999999, practice = True),
                aqEntry(lec1Alloc, 0, False, 9.999999999, practice = True),
            ],
        ))
        self.assertEqual(
            self.getJson('http://nohost/plone/@@quizdb-student-award', user=USER_B_ID),
            uniDict(coin_available=11000, walletId='', tx_id=None, history=[
                uniDict(amount=10000, claimed=False, lecture='/plone/dept1/tut1/lec1', time='2013-08-20T13:57:40'),
                uniDict(amount=1000, claimed=False, lecture='/plone/dept1/tut1/lec1', time='2013-08-20T13:51:40'),
            ])
        )

        # B only gets 8 right, doesn't get multiple points
        lec1Alloc = self.getJson('http://nohost/plone/dept1/tut1/lec2/@@quizdb-sync', user=USER_B_ID)
        lec1Alloc = self.getJson('http://nohost/plone/dept1/tut1/lec2/@@quizdb-sync', user=USER_B_ID, body=dict(
            user='Betty',
            answerQueue=[
                aqEntry(lec1Alloc, 0, True, 1.0),
                aqEntry(lec1Alloc, 0, True, 2.0),
                aqEntry(lec1Alloc, 0, True, 3.0),
                aqEntry(lec1Alloc, 0, True, 4.0),
                aqEntry(lec1Alloc, 0, True, 5.0),
                aqEntry(lec1Alloc, 0, True, 6.0),
                aqEntry(lec1Alloc, 0, True, 7.0),
                aqEntry(lec1Alloc, 0, True, 8.0),
                aqEntry(lec1Alloc, 0, False, 7.0),
                aqEntry(lec1Alloc, 0, False, 6.0),
                aqEntry(lec1Alloc, 0, False, 5.0),
            ],
        ))
        self.assertEqual(
            self.getJson('http://nohost/plone/@@quizdb-student-award', user=USER_B_ID),
            uniDict(coin_available=12000, walletId='', tx_id=None, history=[
                uniDict(amount=1000, claimed=False, lecture='/plone/dept1/tut1/lec2', time='2013-08-20T14:15:40'),
                uniDict(amount=10000, claimed=False, lecture='/plone/dept1/tut1/lec1', time='2013-08-20T13:57:40'),
                uniDict(amount=1000, claimed=False, lecture='/plone/dept1/tut1/lec1', time='2013-08-20T13:51:40'),
            ])
        )

        # Remove extra lecture
        del portal['dept1']['tut1']['tmplec3']
        transaction.commit()

    def test_answerQueueSummary(self):
        """Make sure answerQueueSummary stays up to date"""
        def answer(alloc, time, correct, grade, practice=False):
            qn = random.sample(aAlloc['questions'], 1)[0]
            title = self.getJson(qn['uri'])['title']

            if title == u'Unittest D1 T1 L1 Q1':
                answer = 1 if correct else 0
            elif title == u'Unittest D1 T1 L1 Q2':
                answer = 2 if correct else 1
            else:
                raise ValueError("Unknown Question " + title)

            return dict(
                synced=False,
                uri=qn['uri'],
                student_answer=answer,
                correct=correct,
                quiz_time=time - 5,
                answer_time=time,
                grade_after=grade,
                practice=practice,
            )

        # Allocate lecture to user A
        aAlloc = self.getJson('http://nohost/plone/dept1/tut1/lec1/@@quizdb-sync', user=USER_A_ID, body=dict(
        ))
        self.assertEquals(
            sorted([self.getJson(qn['uri'])['title'] for qn in aAlloc['questions']]),
            [u'Unittest D1 T1 L1 Q1', u'Unittest D1 T1 L1 Q2'],
        )

        # Write some answers back, stats were filled in on the last item
        aAlloc = self.getJson('http://nohost/plone/dept1/tut1/lec1/@@quizdb-sync', user=USER_A_ID, body=dict(
            answerQueue=[
                answer(aAlloc, 1379900100, True,  0.1),
                answer(aAlloc, 1379900200, True,  0.2),
                answer(aAlloc, 1379900300, True,  0.13, practice=True),
                answer(aAlloc, 1379900400, False, 0.15),
            ],
        ))
        self.assertEqual(
            [a['answer_time'] for a in aAlloc['answerQueue']],
            [1379900100, 1379900200, 1379900400],  # NB: No practice questions in answerQueue
        )
        self.assertEqual(aAlloc['answerQueue'][-1]['lec_answered'], 4)
        self.assertEqual(aAlloc['answerQueue'][-1]['lec_correct'], 3)
        self.assertEqual(aAlloc['answerQueue'][-1]['practice_answered'], 1)
        self.assertEqual(aAlloc['answerQueue'][-1]['practice_correct'], 1)
        self.assertEqual(aAlloc['answerQueue'][-1]['grade_after'], 0.15)

        # Insert answers that predate current work. Should get valid stats
        aAlloc = self.getJson('http://nohost/plone/dept1/tut1/lec1/@@quizdb-sync', user=USER_A_ID, body=dict(
            answerQueue=[
                answer(aAlloc, 1379900110, True,  0.11),
                answer(aAlloc, 1379900120, False, 0.12),
                answer(aAlloc, 1379900130, False, 0.12, practice=True),
            ],
        ))
        self.assertEqual(
            [a['answer_time'] for a in aAlloc['answerQueue']],
            [1379900100, 1379900110, 1379900120, 1379900200, 1379900400],
        )
        self.assertEqual(aAlloc['answerQueue'][-1]['lec_answered'], 7)
        self.assertEqual(aAlloc['answerQueue'][-1]['lec_correct'], 4)
        self.assertEqual(aAlloc['answerQueue'][-1]['practice_answered'], 2)
        self.assertEqual(aAlloc['answerQueue'][-1]['practice_correct'], 1)
        self.assertEqual(aAlloc['answerQueue'][-1]['grade_after'], 0.15)

        # Destroy answerSummary
        from tutorweb.quizdb import ORMBase
        from z3c.saconfig import Session
        Session().execute("DROP TABLE answerSummary")
        ORMBase.metadata.create_all(Session().bind)

        # answerSummary row was recreated
        aAlloc = self.getJson('http://nohost/plone/dept1/tut1/lec1/@@quizdb-sync', user=USER_A_ID, body=dict(
            answerQueue=[
                answer(aAlloc, 1379900510, True,  0.41),
            ],
        ))
        self.assertEqual(
            [a['answer_time'] for a in aAlloc['answerQueue']],
            [1379900100, 1379900110, 1379900120, 1379900200, 1379900400, 1379900510],
        )
        self.assertEqual(aAlloc['answerQueue'][-1]['lec_answered'], 8)
        self.assertEqual(aAlloc['answerQueue'][-1]['lec_correct'], 5)
        self.assertEqual(aAlloc['answerQueue'][-1]['practice_answered'], 2)
        self.assertEqual(aAlloc['answerQueue'][-1]['practice_correct'], 1)
        self.assertEqual(aAlloc['answerQueue'][-1]['grade_after'], 0.41)

    def test_practiceMode(self):
        """Practice mod answers are recorded, but not returned"""
        # Allocate to user A
        aAlloc = self.getJson('http://nohost/plone/dept1/tut1/lec1/@@quizdb-sync', user=USER_A_ID)
        qns = dict((self.getJson(qn['uri'])['title'], qn) for qn in aAlloc['questions'])
        self.assertEquals(sorted(qns.keys()), [u'Unittest D1 T1 L1 Q1', u'Unittest D1 T1 L1 Q2'])

        # Form nice long answerQueue and submit it
        answerQueue = [dict(
            synced=False,
            uri=qns[u'Unittest D1 T1 L1 Q1']['uri'],
            student_answer=i % 2,  # Odd i's should be correct
            correct='wibble',
            quiz_time=1377000000 + (i * 10),
            answer_time=1377000001 + (i * 10),
            grade_after=0.1,
        ) for i in range(0, 13)]
        answerQueue[0]['practice'] = False
        answerQueue[1]['practice'] = False
        # Miss answerQueue[2], should assume it's false
        answerQueue[3]['practice'] = False
        answerQueue[4]['practice'] = True
        answerQueue[5]['practice'] = True
        answerQueue[6]['practice'] = True
        answerQueue[7]['practice'] = True
        answerQueue[8]['practice'] = False
        answerQueue[9]['practice'] = False
        answerQueue[10]['practice'] = False
        answerQueue[11]['practice'] = False
        answerQueue[12]['practice'] = False
        aAlloc = self.getJson('http://nohost/plone/dept1/tut1/lec1/@@quizdb-sync', user=USER_A_ID, body=dict(
            user='Arnold',
            answerQueue=answerQueue,
        ))

        # Skip over practice values
        self.assertEquals([a['quiz_time'] for a in aAlloc['answerQueue']], [
            answerQueue[0]['quiz_time'],
            answerQueue[1]['quiz_time'],
            answerQueue[2]['quiz_time'],
            answerQueue[3]['quiz_time'],
            answerQueue[8]['quiz_time'],
            answerQueue[9]['quiz_time'],
            answerQueue[10]['quiz_time'],
            answerQueue[11]['quiz_time'],
            answerQueue[12]['quiz_time'],
        ])

        # Practice values are included in the count though
        self.assertEquals(aAlloc['answerQueue'][-1]['lec_answered'], 13)
        self.assertEquals(aAlloc['answerQueue'][-1]['lec_correct'], 6)
        self.assertEquals(aAlloc['answerQueue'][-1]['practice_answered'], 4)
        self.assertEquals(aAlloc['answerQueue'][-1]['practice_correct'], 2)

    def test_lotsofquestions(self):
        """Shouldn't go over the question cap when assigning questions"""
        def createQuestions(obj, count):
            if not hasattr(self, 'createdQns'):
                self.createdQns = 0
            for i in xrange(count):
                obj.invokeFactory(
                    type_name="tw_latexquestion",
                    id="qn%d" % (self.createdQns + i),
                    title="Unittest megalec Q%d" % (self.createdQns + i),
                    choices=[dict(text="orange", correct=False), dict(text="green", correct=True)],
                    finalchoices=[],
                )
            self.createdQns = count
            import transaction ; transaction.commit()

        portal = self.layer['portal']
        login(portal, MANAGER_ID)

        # Create a lecture with a reasonable number of questions
        portal['dept1']['tut1'].invokeFactory(
            type_name="tw_lecture",
            id="megalec",
            title="Lecture with a bazillion question",
        )
        createQuestions(portal['dept1']['tut1']['megalec'], 20)

        # Allocate to user A, get 20
        aAlloc = self.getJson('http://nohost/plone/dept1/tut1/megalec/@@quizdb-sync', user=USER_A_ID)
        self.assertEquals(len(aAlloc['questions']), 20)

        # Create even more questions, shouldn't get any more than DEFAULT_QUESTION_CAP
        createQuestions(portal['dept1']['tut1']['megalec'], DEFAULT_QUESTION_CAP)
        aAlloc = self.getJson('http://nohost/plone/dept1/tut1/megalec/@@quizdb-sync', user=USER_A_ID)
        self.assertEquals(len(aAlloc['questions']), DEFAULT_QUESTION_CAP)

        # Allocate to user B, only get DEFAULT_QUESTION_CAP straight away
        bAlloc = self.getJson('http://nohost/plone/dept1/tut1/megalec/@@quizdb-sync', user=USER_B_ID)
        self.assertEquals(len(bAlloc['questions']), DEFAULT_QUESTION_CAP)

        # However, they're a different set of questions
        # NB: There's only 20 spare, so could flap
        self.assertNotEqual(
            sorted([qn['uri'] for qn in aAlloc['questions']]),
            sorted([qn['uri'] for qn in bAlloc['questions']]),
        )

        # A should still get the same set though
        aAlloc1 = self.getJson('http://nohost/plone/dept1/tut1/megalec/@@quizdb-sync', user=USER_A_ID)
        self.assertEqual(
            sorted([qn['uri'] for qn in aAlloc['questions']]),
            sorted([qn['uri'] for qn in aAlloc1['questions']]),
        )

        # B should still get the same set too
        bAlloc1 = self.getJson('http://nohost/plone/dept1/tut1/megalec/@@quizdb-sync', user=USER_B_ID)
        self.assertEqual(
            sorted([qn['uri'] for qn in bAlloc['questions']]),
            sorted([qn['uri'] for qn in bAlloc1['questions']]),
        )

    def test_questioncapsetting(self):
        """Should be able to set question cap"""
        def createQuestions(obj, count):
            if not hasattr(self, 'createdQns'):
                self.createdQns = 0
            for i in xrange(count):
                obj.invokeFactory(
                    type_name="tw_latexquestion",
                    id="qn%d" % (self.createdQns + i),
                    title="Unittest megalec Q%d" % (self.createdQns + i),
                    choices=[dict(text="orange", correct=False), dict(text="green", correct=True)],
                    finalchoices=[],
                )
            self.createdQns = count
            import transaction ; transaction.commit()

        portal = self.layer['portal']
        login(portal, MANAGER_ID)

        # Create lectures to exercise settings
        portal['dept1'].invokeFactory(
            type_name="tw_tutorial",
            id="mediumtut",
            title="Tutorial with a question cap of 10",
            settings=[dict(key='question_cap', value='10')],
        )
        portal['dept1']['mediumtut'].invokeFactory(
            type_name="tw_lecture",
            id="mediumlec",
            title="Lecture with no question cap (but uses default of 10)",
        )
        portal['dept1']['mediumtut'].invokeFactory(
            type_name="tw_lecture",
            id="largelec",
            title="Lecture with a question cap of 15",
            settings=[dict(key='question_cap', value='15')],
        )
        createQuestions(portal['dept1']['mediumtut']['mediumlec'], 20)
        createQuestions(portal['dept1']['mediumtut']['largelec'], 20)

        # Should get 15 for large, 10 for medium
        aAlloc = self.getJson('http://nohost/plone/dept1/mediumtut/largelec/@@quizdb-sync', user=USER_A_ID)
        self.assertEquals(len(aAlloc['questions']), 15)
        aAlloc = self.getJson('http://nohost/plone/dept1/mediumtut/mediumlec/@@quizdb-sync', user=USER_A_ID)
        self.assertEquals(len(aAlloc['questions']), 10)

        # Tune lecture down to 5, questions should be tossed away.
        portal['dept1']['mediumtut']['largelec'].settings = [dict(key='question_cap', value='5')]
        import transaction ; transaction.commit()
        aAlloc = self.getJson('http://nohost/plone/dept1/mediumtut/largelec/@@quizdb-sync', user=USER_A_ID)
        self.assertEquals(len(aAlloc['questions']), 5)
        self.assertEquals(len(aAlloc['removed_questions']), 10)

        # On the second round, we forget about the removed questions
        # NB: This isn't brilliant behaviour, but saves cluttering the DB
        aAlloc = self.getJson('http://nohost/plone/dept1/mediumtut/largelec/@@quizdb-sync', user=USER_A_ID)
        self.assertEquals(len(aAlloc['questions']), 5)
        self.assertEquals(len(aAlloc['removed_questions']), 0)

        # Bump cap back up a bit, should get more questions
        portal['dept1']['mediumtut']['largelec'].settings = [dict(key='question_cap', value='7')]
        import transaction ; transaction.commit()
        aAlloc = self.getJson('http://nohost/plone/dept1/mediumtut/largelec/@@quizdb-sync', user=USER_A_ID)
        self.assertEquals(len(aAlloc['questions']), 7)
        self.assertEquals(len(aAlloc['removed_questions']), 0)

        # Delete some questions, should go back down again
        for qn in [x.id for x in portal['dept1']['mediumtut']['largelec'].getChildNodes()][:15]:
            browser = self.getBrowser('http://nohost/plone/dept1/mediumtut/largelec/%s/delete_confirmation' % qn, user=MANAGER_ID)
            browser.getControl('Delete').click()
        aAlloc = self.getJson('http://nohost/plone/dept1/mediumtut/largelec/@@quizdb-sync', user=USER_A_ID)
        self.assertEquals(len(aAlloc['questions']), 5)

    def test_templatequestions(self):
        """Crowd-sourced questions always come through"""
        def createQuestions(obj, count):
            if not hasattr(self, 'createdQns'):
                self.createdQns = 0
            for i in xrange(count):
                obj.invokeFactory(
                    type_name="tw_latexquestion",
                    id="qn%d" % (self.createdQns + i),
                    title="Unittest tmpllec mcQ%d" % (self.createdQns + i),
                    choices=[dict(text="orange", correct=False), dict(text="green", correct=True)],
                    finalchoices=[],
                )
            self.createdQns = count
            import transaction ; transaction.commit()
        def createQuestionTemplates(obj, count):
            if not hasattr(self, 'createdTmplQns'):
                self.createdTmplQns = 0
            for i in xrange(count):
                obj.invokeFactory(
                    type_name="tw_questiontemplate",
                    id="tmplqn%d" % (self.createdTmplQns + i),
                    title="Unittest tmpllec tmplQ%d" % (self.createdTmplQns + i),
                )
            self.createdTmplQns = count
            import transaction ; transaction.commit()

        portal = self.layer['portal']
        login(portal, MANAGER_ID)

        # Create a lecture with more questions than capped
        portal['dept1'].invokeFactory(
            type_name="tw_tutorial",
            id="tmpltut",
            title=u"Tutorial with a question cap of 5",
            settings=[
                dict(key='question_cap', value='5'),
                dict(key='prob_template_eval', value='0'),
            ],
        )
        portal['dept1']['tmpltut'].invokeFactory(
            type_name="tw_lecture",
            id="tmpllec",
            title=u"Lecture with no question cap (but uses default of 5)",
        )
        createQuestions(portal['dept1']['tmpltut']['tmpllec'], 8)
        createQuestionTemplates(portal['dept1']['tmpltut']['tmpllec'], 8)

        # Should get 10 questions, 5 of each type
        aAlloc = self.getJson('http://nohost/plone/dept1/tmpltut/tmpllec/@@quizdb-sync', user=USER_A_ID)
        self.assertEquals(len(aAlloc['questions']), 10)

        counts = dict(tmplQ=0, mcQ=0)
        for qn in aAlloc['questions']:
            title = self.getJson(qn['uri'])['title']
            if 'tmplQ' in title:
                counts['tmplQ'] += 1
                self.assertEquals(qn['_type'], "template")
                # Question templates are marked with online_only
                self.assertEquals(qn['online_only'], True)
            if 'mcQ' in title:
                counts['mcQ'] += 1
                self.assertNotEquals(qn['_type'], "template")
                self.assertEquals(qn['online_only'], False)
        self.assertEquals(counts['tmplQ'], 5)
        self.assertEquals(counts['mcQ'], 5)
