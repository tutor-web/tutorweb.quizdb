import base64
import json

import transaction
from zope.testing.loggingsupport import InstalledHandler

from plone.app.testing import login

from .base import FunctionalTestCase
from .base import USER_A_ID, USER_B_ID, MANAGER_ID


class ReviewUgQnViewTest(FunctionalTestCase):
    maxDiff = None

    def setUp(self):
        """Set up a class ready for testing"""
        self.loghandlers = dict(
            sqlalchemy=InstalledHandler('sqlalchemy.engine'),
            sync=InstalledHandler('tutorweb.quizdb.browser.sync')
        )

    def logs(self, name='sqlalchemy'):
        return [x.getMessage() for x in self.loghandlers[name].records]

    def test_empty(self):
        """Works when there isn't anything to report"""
        out = self.getJson('http://nohost/plone/dept1/tut1/lec1/@@quizdb-review-ugqn', user=USER_A_ID)
        self.assertEqual(out, [])

    def texToHTML(self, f):
        """Encode TeX in f into HTML"""
        from Products.CMFCore.utils import getToolByName
        if not f:
            return f
        if getattr(self, '_pt', None) is None:
            self._pt = getToolByName(self.layer['portal'], 'portal_transforms')
        return self._pt.convertTo(
            'text/html',
            f.encode('utf-8'),
            mimetype='text/x-tex',
            encoding='utf-8',
        ).getData().decode('utf-8')

    def test_writeQuestions(self):
        """User generated questions are stored and displayed in review"""
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
                dict(key='prob_template_eval', value='1'),
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
        self.assertEquals(
            sorted([self.getJson(qn['uri'])['title'] for qn in aAlloc['questions']]),
            [u'Unittest tmpllec tmplQ%d' % i for i in range(0,5)],
        )

        # Write some answers back
        aAlloc = self.getJson('http://nohost/plone/dept1/tmpltut/tmpllec/@@quizdb-sync', user=USER_A_ID, body=dict(
            answerQueue=[
                dict(
                    synced=False,
                    uri=aAlloc['questions'][0]['uri'],
                    student_answer=dict(
                        text=u"Want some rye?",
                        explanation=u"moo",
                        choices=[
                            dict(answer="Course you do", correct=True),
                            dict(answer="You keep that.", correct=False),
                        ],
                    ),
                    correct=True,
                    quiz_time=1377000000,
                    answer_time=1377000010,
                    grade_after=0.1,
                ),
                dict(
                    synced=False,
                    uri=aAlloc['questions'][1]['uri'],
                    student_answer=dict(
                        text=u"Who's like us?",
                        explanation=u"moo",
                        choices=[
                            dict(answer="Here's to us.", correct=False),
                            dict(answer="Who's like us?", correct=False),
                            dict(answer="Damn few!", correct=True),
                            dict(answer="And they're all dead!", correct=False),
                        ],
                    ),
                    correct=True,
                    quiz_time=1377000000,
                    answer_time=1377000010,
                    grade_after=0.1,
                ),
            ],
        ))

        # A's questions now appear in the review
        self.assertEquals(
            self.getJson('http://nohost/plone/dept1/tmpltut/tmpllec/@@quizdb-review-ugqn', user=USER_A_ID),
            [
                {u'id':1, u'text': self.texToHTML(u"Want some rye?"), u'choices':[
                    {u'answer': self.texToHTML(u'Course you do'), u'correct':True},
                    {u'answer': self.texToHTML(u'You keep that.'), u'correct':False}
                ], u'answers': [
                ]},
                {u'id':2, u'text': self.texToHTML(u"Who's like us?"), u'choices':[
                    {u'answer': self.texToHTML(u"Here's to us."), u'correct':False},
                    {u'answer': self.texToHTML(u"Who's like us?"), u'correct':False},
                    {u'answer': self.texToHTML(u"Damn few!"), u'correct':True},
                    {u'answer': self.texToHTML(u"And they're all dead!"), u'correct':False}
                ], u'answers': [
                ]},
            ]
        )
        # A has nothing in another lecture
        self.assertEquals(
            self.getJson('http://nohost/plone/dept1/tut1/lec1/@@quizdb-review-ugqn', user=USER_A_ID),
            []
        )
        # B hasn't done anything yet
        self.assertEquals(
            self.getJson('http://nohost/plone/dept1/tut1/lec1/@@quizdb-review-ugqn', user=USER_B_ID),
            []
        )

        # Allocate to user B, filter out templates
        bAlloc = self.getJson('http://nohost/plone/dept1/tmpltut/tmpllec/@@quizdb-sync', user=USER_B_ID)
        bUgQns = [x for x in [self.getJson(qn['uri'], user=USER_B_ID) for qn in bAlloc['questions']] if x['_type'] == u'usergenerated']
        self.assertEqual(len(bUgQns), 2)
        if 'Want some rye' in bUgQns[1]['text']:
            # We need them to be in the right order for test to work
            bUgQns.reverse()

        # Answer user generated questions
        bAlloc = self.getJson('http://nohost/plone/dept1/tmpltut/tmpllec/@@quizdb-sync', user=USER_B_ID, body=dict(
            answerQueue=[
                dict(
                    synced=False,
                    uri=bUgQns[0]['uri'],
                    question_type='usergenerated',
                    question_id=bUgQns[0]['question_id'],
                    selected_answer="0",
                    student_answer=dict(
                        rating=25,
                        comments="I've never played Return to Zork",
                    ),
                    correct=False,
                    quiz_time=1377000000,
                    answer_time=1377000010,
                    grade_after=0.1,
                ),
                dict(
                    synced=False,
                    uri=bUgQns[1]['uri'],
                    question_type='usergenerated',
                    question_id=bUgQns[1]['question_id'],
                    selected_answer="0",
                    student_answer=dict(
                        rating=-1,
                        comments="You don't actually respond like this, you tip the drink into the plant pot",
                    ),
                    correct=False,
                    quiz_time=1377000000,
                    answer_time=1377000010,
                    grade_after=0.1,
                ),
            ],
        ))

        # B has no more to answer
        bUgQns = [x for x in [self.getJson(qn['uri'], user=USER_B_ID) for qn in bAlloc['questions']] if x['_type'] == u'usergenerated']
        self.assertEqual(len(bUgQns), 0)

        # B's answer now appears in A's review
        self.assertEquals(
            self.getJson('http://nohost/plone/dept1/tmpltut/tmpllec/@@quizdb-review-ugqn', user=USER_A_ID),
            [
                {u'id':1, u'text': self.texToHTML(u"Want some rye?"), u'choices':[
                    {u'answer': self.texToHTML(u'Course you do'), u'correct':True},
                    {u'answer': self.texToHTML(u'You keep that.'), u'correct':False}
                ], u'answers': [
                    {u'comments': u"I've never played Return to Zork", u'id': 1, u'rating': 25},
                ]},
                {u'id':2, u'text': self.texToHTML(u"Who's like us?"), u'choices':[
                    {u'answer': self.texToHTML(u"Here's to us."), u'correct':False},
                    {u'answer': self.texToHTML(u"Who's like us?"), u'correct':False},
                    {u'answer': self.texToHTML(u"Damn few!"), u'correct':True},
                    {u'answer': self.texToHTML(u"And they're all dead!"), u'correct':False}
                ], u'answers': [
                    {u'comments': u"You don't actually respond like this, you tip the drink into the plant pot", u'id': 2, u'rating': -1},
                ]},
            ]
        )
        # B still hasn't done anything yet
        self.assertEquals(
            self.getJson('http://nohost/plone/dept1/tut1/lec1/@@quizdb-review-ugqn', user=USER_B_ID),
            []
        )
