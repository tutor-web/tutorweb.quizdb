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

        # Repeatedly ask for a question until it matches the returned dict
        def searchForQn(uri, match, user=USER_A_ID, emptyOkay=False, loops=50):
            def isMatch(qn, match):
                for k in match.keys():
                    if (k not in qn) or qn[k] != match[k]:
                        return False
                return True

            for i in range(loops):
                qn = self.getJson(uri, user=user, expectedStatus=[200, 400])
                if isMatch(qn, match):
                    return qn
            if emptyOkay:
                return None
            raise ValueError("Could not get a question with %s " % str(match))

        portal = self.layer['portal']
        login(portal, MANAGER_ID)

        # Create a lecture with more questions than capped
        portal['dept1'].invokeFactory(
            type_name="tw_tutorial",
            id="tmpltut",
            title=u"Tutorial with a question cap of 5",
            settings=[
                dict(key='question_cap', value='5'),
                dict(key='prob_template_eval', value='0.5'),
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
            sorted(searchForQn(qn['uri'], {"_type" : "template"}, user=USER_A_ID)['title'] for qn in aAlloc['questions']),
            sorted(u'Unittest tmpllec tmplQ%d' % i for i in range(0,5)),
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
                    answer_time=1377000001,
                    grade_after=0.1,
                ),
                dict(
                    synced=False,
                    uri=aAlloc['questions'][1]['uri'],
                    student_answer=dict(
                        text=u"Who's like us?",
                        explanation=u"oink",
                        choices=[
                            dict(answer="Here's to us.", correct=False),
                            dict(answer="Who's like us?", correct=False),
                            dict(answer="Damn few!", correct=True),
                            dict(answer="And they're all dead!", correct=False),
                        ],
                    ),
                    correct=True,
                    quiz_time=1377000010,
                    answer_time=1377000011,
                    grade_after=0.1,
                ),
            ],
        ))

        # A's questions now appear in the review
        self.assertEquals(
            self.getJson('http://nohost/plone/dept1/tmpltut/tmpllec/@@quizdb-review-ugqn', user=USER_A_ID),
            [
                {u'text': self.texToHTML(u"Who's like us?"), u'explanation': self.texToHTML(u"oink"), u'choices':[
                    {u'answer': self.texToHTML(u"Here's to us."), u'correct':False},
                    {u'answer': self.texToHTML(u"Who's like us?"), u'correct':False},
                    {u'answer': self.texToHTML(u"Damn few!"), u'correct':True},
                    {u'answer': self.texToHTML(u"And they're all dead!"), u'correct':False}
                ], u'answers': [
                ], u'verdict': None, u'uri': "%s?author_qn=yes&question_id=%s" % (aAlloc['questions'][1]['uri'], aAlloc['answerQueue'][1]['student_answer']) },
                {u'text': self.texToHTML(u"Want some rye?"), u'explanation': self.texToHTML(u"moo"), u'choices':[
                    {u'answer': self.texToHTML(u'Course you do'), u'correct':True},
                    {u'answer': self.texToHTML(u'You keep that.'), u'correct':False}
                ], u'answers': [
                ], u'verdict': None, u'uri': "%s?author_qn=yes&question_id=%s" % (aAlloc['questions'][0]['uri'], aAlloc['answerQueue'][0]['student_answer']) },
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
        bUgQns = [searchForQn(qn['uri'], {"_type" : "usergenerated"}, user=USER_B_ID, emptyOkay=True) for qn in bAlloc['questions']]
        bUgQns = [x for x in bUgQns if x is not None]
        if 'Want some rye' in bUgQns[1]['text']:
            # We need them to be in the right order for test to work
            bUgQns.reverse()
        self.assertEqual(len(bUgQns), 2)
        self.assertTrue('Want some rye?' in bUgQns[0]['text'])
        self.assertTrue('like us?' in bUgQns[1]['text'])

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
                    quiz_time=1377000020,
                    answer_time=1377000021,
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
                    quiz_time=1377000030,
                    answer_time=1377000031,
                    grade_after=0.1,
                ),
            ],
        ))

        # B has no more to answer
        bUgQns = [searchForQn(qn['uri'], {"_type" : "usergenerated"}, user=USER_B_ID, emptyOkay=True) for qn in bAlloc['questions']]
        bUgQns = [x for x in bUgQns if x is not None]
        self.assertEqual(len(bUgQns), 0)

        # B's answer now appears in A's review
        aReview = self.getJson('http://nohost/plone/dept1/tmpltut/tmpllec/@@quizdb-review-ugqn', user=USER_A_ID)
        self.assertEquals(
            aReview,
            [
                {u'text': self.texToHTML(u"Want some rye?"), u'explanation': self.texToHTML(u"moo"), u'choices':[
                    {u'answer': self.texToHTML(u'Course you do'), u'correct':True},
                    {u'answer': self.texToHTML(u'You keep that.'), u'correct':False}
                ], u'answers': [
                    {u'comments': u"I've never played Return to Zork", u'id': 1, u'rating': 25},
                ], u'verdict': 25, u'uri': "%s?author_qn=yes&question_id=%s" % (aAlloc['questions'][0]['uri'], aAlloc['answerQueue'][0]['student_answer']) },
                {u'text': self.texToHTML(u"Who's like us?"), u'explanation': self.texToHTML(u"oink"), u'choices':[
                    {u'answer': self.texToHTML(u"Here's to us."), u'correct':False},
                    {u'answer': self.texToHTML(u"Who's like us?"), u'correct':False},
                    {u'answer': self.texToHTML(u"Damn few!"), u'correct':True},
                    {u'answer': self.texToHTML(u"And they're all dead!"), u'correct':False}
                ], u'answers': [
                    {u'comments': u"You don't actually respond like this, you tip the drink into the plant pot", u'id': 2, u'rating': -1},
                ], u'verdict': -1, u'uri': "%s?author_qn=yes&question_id=%s" % (aAlloc['questions'][1]['uri'], aAlloc['answerQueue'][1]['student_answer']) },
            ]
        )
        # B still hasn't done anything yet
        self.assertEquals(
            self.getJson('http://nohost/plone/dept1/tut1/lec1/@@quizdb-review-ugqn', user=USER_B_ID),
            []
        )

        # A writes a replacement question
        aAlloc = self.getJson('http://nohost/plone/dept1/tmpltut/tmpllec/@@quizdb-sync', user=USER_A_ID, body=dict(
            answerQueue=[
                dict(
                    synced=False,
                    uri=aReview[0]['uri'],
                    student_answer=dict(
                        text=u"Want some more rye?",
                        explanation=u"moo",
                        choices=[
                            dict(answer="Course you do", correct=True),
                            dict(answer="You keep that.", correct=False),
                        ],
                    ),
                    correct=True,
                    quiz_time=1377000040,
                    answer_time=1377000041,
                    grade_after=0.1,
                ),
            ]
        ))

        # Original question no longer in review
        aReview = self.getJson('http://nohost/plone/dept1/tmpltut/tmpllec/@@quizdb-review-ugqn', user=USER_A_ID)
        self.assertEquals(
            aReview,
            [
                {u'text': self.texToHTML(u"Who's like us?"), u'explanation': self.texToHTML(u"oink"), u'choices':[
                    {u'answer': self.texToHTML(u"Here's to us."), u'correct':False},
                    {u'answer': self.texToHTML(u"Who's like us?"), u'correct':False},
                    {u'answer': self.texToHTML(u"Damn few!"), u'correct':True},
                    {u'answer': self.texToHTML(u"And they're all dead!"), u'correct':False}
                ], u'answers': [
                    {u'comments': u"You don't actually respond like this, you tip the drink into the plant pot", u'id': 2, u'rating': -1},
                ], u'verdict': -1, u'uri': "%s?author_qn=yes&question_id=%s" % (aAlloc['questions'][1]['uri'], aAlloc['answerQueue'][1]['student_answer']) },
                {u'text': self.texToHTML(u"Want some more rye?"), u'explanation': self.texToHTML(u"moo"), u'choices':[
                    {u'answer': self.texToHTML(u'Course you do'), u'correct':True},
                    {u'answer': self.texToHTML(u'You keep that.'), u'correct':False}
                ], u'answers': [
                ], u'verdict': None, u'uri': "%s?author_qn=yes&question_id=%s" % (aAlloc['questions'][0]['uri'], aAlloc['answerQueue'][2]['student_answer']) },
            ]
        )
