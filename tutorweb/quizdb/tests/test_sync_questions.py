# -*- coding: utf8 -*-
import transaction

from z3c.relationfield import RelationValue
from zope.intid.interfaces import IIntIds
from zope.component import getUtility

from Products.CMFCore.utils import getToolByName
from plone.app.testing import login
from plone.namedfile.file import NamedBlobFile

from .base import FunctionalTestCase, IntegrationTestCase
from .base import USER_A_ID, USER_B_ID, USER_C_ID, MANAGER_ID

from ..sync.plone import syncPloneQuestions

def getAllocation(portal, alloc, user):
    login(portal, USER_A_ID)
    view = portal.restrictedTraverse('quizdb-get-question')
    view.request.set('URL', alloc)
    view.questionId = alloc.replace("http://nohost/plone/quizdb-get-question/", "")
    return view.asDict({})


class SyncPloneQuestionsTest(IntegrationTestCase):
    maxDiff = None

    def setUp(self):
        super(SyncPloneQuestionsTest, self).setUp()
        self.objectPublish(self.layer['portal']['dept1']['tut1']['lec1'])
        self.objectPublish(self.layer['portal']['dept1']['tut1']['lec2'])

    def test_emptyLecture(self):
        """Empty lectures shouldn't do much, but still work"""
        lectureObj = self.createTestLecture(qnCount=0)
        dbLec = lectureObj.restrictedTraverse('@@quizdb-sync').getDbLecture()
        syncPloneQuestions(dbLec, lectureObj)
        self.assertEqual(dbLec.questions, [])

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
        allocs = list(self.allocGetQuestionAllocation(dbLec, self.studentA, dict(question_cap=10)))
        self.assertEqual(sorted(getAllocation(portal, qn['uri'], USER_A_ID)['title'] for qn in allocs), [
            u'Einf\xf6ld Umr\xf6\xf0un',
            u'T\xe1knm\xe1l mengjafr\xe6\xf0innar - mengi',
            u'Unittest D1 T1 L1 Q1',
            u'Unittest D1 T1 L1 Q2',
        ])


class GetQuestionAllocationTest(FunctionalTestCase):
    maxDiff = None

    def removeQn(self, parent, id):
        oldObj = parent[id]
        parent.manage_delObjects([id])
        parent.reindexObject()
        self.notifyDelete(oldObj)

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

        self.objectPublish(self.layer['portal']['dept1']['tut1']['lec1'])
        self.objectPublish(self.layer['portal']['dept1']['tut1']['lec2'])

        transaction.commit()

    def test_targetDifficutly(self):
        """Make sure we can influence the target difficulty"""
        portal = self.layer['portal']
        login(portal, MANAGER_ID)

        def getAllocStats(dbLec, student, targetDifficulty, settings = dict(question_cap=10)):
            allocs = list(self.allocGetQuestionAllocation(dbLec, student, settings, targetDifficulty=targetDifficulty))
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
            # NB: targetDifficulty and reAllocQuestions aren't parameters any more, but
            # we keep them here to keep tests working
            allocs = list(self.allocGetQuestionAllocation(
                dbLec,
                student,
                dict(question_cap=10),
                targetDifficulty=targetDifficulty,
                reAllocQuestions=reAllocQuestions,
            ))
            return allocs
        aAllocs = []

        # Assign to A randomly
        aAllocs.append(gqa(None, False))
        self.assertEquals(len(aAllocs[0]), 10)

        # Reassign, with high grade
        aAllocs.append(gqa(0.925, True))
        self.assertEquals(len(aAllocs[1]), 10)

        # Should have picked off the 2 oldest items
        oldItems = [a for a in aAllocs[-2] if a not in aAllocs[-1]]
        self.assertEquals(len(oldItems), 2)
        self.assertEqual(
            oldItems,
            aAllocs[-2][0:2]
        )

        # New items should be hard
        newItems = [a for a in aAllocs[-1] if a not in aAllocs[-2]]
        self.assertEquals(len(newItems), 2)
        for a in newItems:
            self.assertGreater(a['correct'], 75)

        # Reassign, with low grade
        aAllocs.append(gqa(0.025, True))
        self.assertEquals(len(aAllocs[1]), 10)

        # Should have picked off the 2 oldest items
        oldItems = [a for a in aAllocs[-2] if a not in aAllocs[-1]]
        self.assertEquals(len(oldItems), 2)
        self.assertEqual(
            oldItems,
            aAllocs[-2][0:2]
        )

        # New items should be easy
        newItems = [a for a in aAllocs[-1] if a not in aAllocs[-2]]
        self.assertEquals(len(newItems), 2)
        for a in newItems:
            self.assertLess(a['correct'], 25)

    def test_lectureSymlink(self):
        portal = self.layer['portal']
        login(portal, MANAGER_ID)

        # Make a symlink of lec1
        origLec = portal['dept1']['tut1']['lec1']
        pt = getToolByName(portal, 'portal_types')
        linkLec = portal['dept1']['tut1'][pt.constructContent(
            type_name="collective.alias",
            container=portal['dept1']['tut1'],
            id="linkLec",
            _aliasTarget=RelationValue(getUtility(IIntIds).getId(origLec))
        )]
        self.objectPublish(origLec)
        self.objectPublish(linkLec)
        transaction.commit()

        dbOrigLec = origLec.restrictedTraverse('@@quizdb-sync').getDbLecture()
        syncView = linkLec.restrictedTraverse('@@quizdb-sync')
        dbLinkLec = syncView.getDbLecture()
        self.assertNotEqual(dbOrigLec.lectureId, dbLinkLec.lectureId)

        # Allocate questions from here to user A, will get lecture 1 questions
        login(portal, USER_A_ID)
        student = syncView.getCurrentStudent()
        syncPloneQuestions(dbLinkLec, linkLec)
        allocs = list(self.allocGetQuestionAllocation(
            dbLinkLec,
            student,
            dict(question_cap=10),
        ))
        self.assertEqual(sorted(getAllocation(portal, qn['uri'], USER_A_ID)['title'] for qn in allocs), [
            u'Unittest D1 T1 L1 Q1',
            u'Unittest D1 T1 L1 Q2',
        ])

        # Add a question to lecture 1
        login(portal, MANAGER_ID)
        origLec.invokeFactory(
            type_name="tw_latexquestion",
            id="qn99",
            title="Unittest D1 T1 L1 Q99",
            choices=[dict(text="pink", correct=False), dict(text="purple", correct=True)],
            finalchoices=[],
        )
        transaction.commit()

        # User A will see it when taking the link lecture
        login(portal, USER_A_ID)
        syncPloneQuestions(dbLinkLec, linkLec)
        allocs = list(self.allocGetQuestionAllocation(
            dbLinkLec,
            student,
            dict(question_cap=10),
        ))
        self.assertEqual(sorted(getAllocation(portal, qn['uri'], USER_A_ID)['title'] for qn in allocs), [
            u'Unittest D1 T1 L1 Q1',
            u'Unittest D1 T1 L1 Q2',
            u'Unittest D1 T1 L1 Q99',
        ])

    def test_questionSymLink(self):
        portal = self.layer['portal']
        login(portal, MANAGER_ID)

        # Create a question pack in lec1
        origLec = portal['dept1']['tut1']['lec1']
        qnPack = origLec[origLec.invokeFactory(
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

        # Create a new lecture, with 2 of it's own questions, and links to question pack and another question
        testLec = self.createTestLecture(2)
        getToolByName(portal, 'portal_types').constructContent(
            type_name="collective.alias",
            container=testLec,
            id=qnPack.id,
            _aliasTarget=RelationValue(getUtility(IIntIds).getId(qnPack))
        )
        getToolByName(portal, 'portal_types').constructContent(
            type_name="collective.alias",
            container=testLec,
            id=origLec['qn1'].id,
            _aliasTarget=RelationValue(getUtility(IIntIds).getId(origLec['qn1']))
        )
        self.objectPublish(origLec)
        self.objectPublish(testLec)
        transaction.commit()

        # Assign questions, get combination of linked and original questions
        login(portal, USER_A_ID)
        syncView = testLec.restrictedTraverse('@@quizdb-sync')
        dbLec = syncView.getDbLecture()
        student = syncView.getCurrentStudent()
        syncPloneQuestions(dbLec, testLec)
        allocByTitleTestLec = dict((getAllocation(portal, qn['uri'], USER_A_ID)['title'], qn) for qn in list(self.allocGetQuestionAllocation(
            dbLec,
            student,
            dict(question_cap=10),
        )))
        self.assertEqual(sorted(allocByTitleTestLec.keys()), [
            u'Einf\xf6ld Umr\xf6\xf0un',
            u'T\xe1knm\xe1l mengjafr\xe6\xf0innar - mengi',
            u'Unittest D1 T1 L1 Q1',
            u'Unittest tw_latexquestion 0',
            u'Unittest tw_latexquestion 1',
        ])

        # Allocate original lecture too, should have same questions, but different allocations
        allocByTitleOrigLec = dict((getAllocation(portal, qn['uri'], USER_A_ID)['title'], qn) for qn in list(self.allocGetQuestionAllocation(
            origLec.restrictedTraverse('@@quizdb-sync').getDbLecture(),
            student,
            dict(question_cap=10),
        )))
        self.assertEqual(sorted(allocByTitleOrigLec.keys()), [
            u'Einf\xf6ld Umr\xf6\xf0un',
            u'T\xe1knm\xe1l mengjafr\xe6\xf0innar - mengi',
            u'Unittest D1 T1 L1 Q1',
            u'Unittest D1 T1 L1 Q2',
        ])
        for k in allocByTitleOrigLec.keys():
            if k not in allocByTitleTestLec.keys():
                continue
            self.assertNotEqual(
                allocByTitleTestLec[k]['uri'],
                allocByTitleOrigLec[k]['uri'],
            )

        # Get question stats for lecture, should be 0
        self.assertEqual(origLec.unrestrictedTraverse('@@question-stats').getStats(), [
            {'id': 'qn1', 'timesAnswered': 0, 'timesCorrect': 0, 'title': 'Unittest D1 T1 L1 Q1', 'url': 'http://nohost/plone/dept1/tut1/lec1/qn1'},
            {'id': 'qn2', 'timesAnswered': 0, 'timesCorrect': 0, 'title': 'Unittest D1 T1 L1 Q2', 'url': 'http://nohost/plone/dept1/tut1/lec1/qn2'},
            {'id': 'qnpack01?question_id=Ag10q16', 'timesAnswered': 0, 'timesCorrect': 0, 'title': '', 'url': 'http://nohost/plone/dept1/tut1/lec1/qnpack01?question_id=Ag10q16'},
            {'id': 'qnpack01?question_id=umGen1-0', 'timesAnswered': 0, 'timesCorrect': 0, 'title': '', 'url': 'http://nohost/plone/dept1/tut1/lec1/qnpack01?question_id=umGen1-0'},
        ])
        self.assertEqual(testLec.unrestrictedTraverse('@@question-stats').getStats(), [
            {'id': 'qn-0', 'timesAnswered': 0, 'timesCorrect': 0, 'title': 'Unittest tw_latexquestion 0', 'url': testLec.absolute_url() + '/qn-0'},
            {'id': 'qn-1', 'timesAnswered': 0, 'timesCorrect': 0, 'title': 'Unittest tw_latexquestion 1', 'url': testLec.absolute_url() + '/qn-1'},
            {'id': 'qn1', 'timesAnswered': 0, 'timesCorrect': 0, 'title': 'Unittest D1 T1 L1 Q1', 'url': 'http://nohost/plone/dept1/tut1/lec1/qn1'},
            {'id': 'qnpack01?question_id=Ag10q16', 'timesAnswered': 0, 'timesCorrect': 0, 'title': '', 'url': 'http://nohost/plone/dept1/tut1/lec1/qnpack01?question_id=Ag10q16'},
            {'id': 'qnpack01?question_id=umGen1-0', 'timesAnswered': 0, 'timesCorrect': 0, 'title': '', 'url': 'http://nohost/plone/dept1/tut1/lec1/qnpack01?question_id=umGen1-0'},
        ])

        # Answer a symlinked question, should update both lectures
        self.allocParseAnswerQueue(dbLec, student, [
            dict(
                synced=False,
                uri=allocByTitleTestLec[u'Unittest D1 T1 L1 Q1']['uri'],
                student_answer=1,
                correct=True,
                quiz_time=  1000000000,
                answer_time=1000000001,
                grade_after=0.1,
            ),
        ], {})
        self.assertEqual(origLec.unrestrictedTraverse('@@question-stats').getStats(), [
            {'id': 'qn1', 'timesAnswered': 1, 'timesCorrect': 1, 'title': 'Unittest D1 T1 L1 Q1', 'url': 'http://nohost/plone/dept1/tut1/lec1/qn1'},
            {'id': 'qn2', 'timesAnswered': 0, 'timesCorrect': 0, 'title': 'Unittest D1 T1 L1 Q2', 'url': 'http://nohost/plone/dept1/tut1/lec1/qn2'},
            {'id': 'qnpack01?question_id=Ag10q16', 'timesAnswered': 0, 'timesCorrect': 0, 'title': '', 'url': 'http://nohost/plone/dept1/tut1/lec1/qnpack01?question_id=Ag10q16'},
            {'id': 'qnpack01?question_id=umGen1-0', 'timesAnswered': 0, 'timesCorrect': 0, 'title': '', 'url': 'http://nohost/plone/dept1/tut1/lec1/qnpack01?question_id=umGen1-0'},
        ])
        self.assertEqual(testLec.unrestrictedTraverse('@@question-stats').getStats(), [
            {'id': 'qn-0', 'timesAnswered': 0, 'timesCorrect': 0, 'title': 'Unittest tw_latexquestion 0', 'url': testLec.absolute_url() + '/qn-0'},
            {'id': 'qn-1', 'timesAnswered': 0, 'timesCorrect': 0, 'title': 'Unittest tw_latexquestion 1', 'url': testLec.absolute_url() + '/qn-1'},
            {'id': 'qn1', 'timesAnswered': 1, 'timesCorrect': 1, 'title': 'Unittest D1 T1 L1 Q1', 'url': 'http://nohost/plone/dept1/tut1/lec1/qn1'},
            {'id': 'qnpack01?question_id=Ag10q16', 'timesAnswered': 0, 'timesCorrect': 0, 'title': '', 'url': 'http://nohost/plone/dept1/tut1/lec1/qnpack01?question_id=Ag10q16'},
            {'id': 'qnpack01?question_id=umGen1-0', 'timesAnswered': 0, 'timesCorrect': 0, 'title': '', 'url': 'http://nohost/plone/dept1/tut1/lec1/qnpack01?question_id=umGen1-0'},
        ])

        # Remove symlinked question, should dissapear from both
        login(portal, MANAGER_ID)
        self.removeQn(origLec, qnPack.id)
        login(portal, USER_A_ID)
        self.assertEqual(origLec.unrestrictedTraverse('@@question-stats').getStats(), [
            {'id': 'qn1', 'timesAnswered': 1, 'timesCorrect': 1, 'title': 'Unittest D1 T1 L1 Q1', 'url': 'http://nohost/plone/dept1/tut1/lec1/qn1'},
            {'id': 'qn2', 'timesAnswered': 0, 'timesCorrect': 0, 'title': 'Unittest D1 T1 L1 Q2', 'url': 'http://nohost/plone/dept1/tut1/lec1/qn2'},
        ])
        self.assertEqual(testLec.unrestrictedTraverse('@@question-stats').getStats(), [
            {'id': 'qn-0', 'timesAnswered': 0, 'timesCorrect': 0, 'title': 'Unittest tw_latexquestion 0', 'url': testLec.absolute_url() + '/qn-0'},
            {'id': 'qn-1', 'timesAnswered': 0, 'timesCorrect': 0, 'title': 'Unittest tw_latexquestion 1', 'url': testLec.absolute_url() + '/qn-1'},
            {'id': 'qn1', 'timesAnswered': 1, 'timesCorrect': 1, 'title': 'Unittest D1 T1 L1 Q1', 'url': 'http://nohost/plone/dept1/tut1/lec1/qn1'},
        ])

        # Remove qn1 from our linked lecture, still in the original lecture
        login(portal, MANAGER_ID)
        self.removeQn(testLec, 'qn1')
        login(portal, USER_A_ID)
        self.assertEqual(origLec.unrestrictedTraverse('@@question-stats').getStats(), [
            {'id': 'qn1', 'timesAnswered': 1, 'timesCorrect': 1, 'title': 'Unittest D1 T1 L1 Q1', 'url': 'http://nohost/plone/dept1/tut1/lec1/qn1'},
            {'id': 'qn2', 'timesAnswered': 0, 'timesCorrect': 0, 'title': 'Unittest D1 T1 L1 Q2', 'url': 'http://nohost/plone/dept1/tut1/lec1/qn2'},
        ])
        self.assertEqual(testLec.unrestrictedTraverse('@@question-stats').getStats(), [
            {'id': 'qn-0', 'timesAnswered': 0, 'timesCorrect': 0, 'title': 'Unittest tw_latexquestion 0', 'url': testLec.absolute_url() + '/qn-0'},
            {'id': 'qn-1', 'timesAnswered': 0, 'timesCorrect': 0, 'title': 'Unittest tw_latexquestion 1', 'url': testLec.absolute_url() + '/qn-1'},
        ])

    def test_historicalSelection(self):
        def getAlloc(dbLec, settings):
            out = []
            for a in self.allocGetQuestionAllocation(
                    dbLec,
                    self.studentA,
                    settings):
                out.append([
                    a['_type'],
                    getAllocation(self.layer['portal'], a['uri'], USER_A_ID)['title'],
                ])
            return sorted(out, key=lambda(x): x[0] + x[1])

        portal = self.layer['portal']
        dbLec1 = portal['dept1']['tut1']['lec1'].restrictedTraverse('@@quizdb-sync').getDbLecture()
        dbLec2 = portal['dept1']['tut1']['lec2'].restrictedTraverse('@@quizdb-sync').getDbLecture()
        syncPloneQuestions(dbLec1, portal['dept1']['tut1']['lec1'])
        syncPloneQuestions(dbLec2, portal['dept1']['tut1']['lec2'])

        # By default, no historical questions
        self.assertEqual(getAlloc(dbLec1, dict()), [
            ['regular', u'Unittest D1 T1 L1 Q1'],
            ['regular', u'Unittest D1 T1 L1 Q2'],
        ])
        self.assertEqual(getAlloc(dbLec2, dict()), [
            ['regular', u'Unittest D1 T1 L2 Q1'],
            ['regular', u'Unittest D1 T1 L2 Q2'],
        ])

        # Historical allocations only work if there's a history
        self.assertEqual(getAlloc(dbLec1, dict(hist_sel='0.5')), [
            ['regular', u'Unittest D1 T1 L1 Q1'],
            ['regular', u'Unittest D1 T1 L1 Q2'],
        ])
        self.assertEqual(getAlloc(dbLec2, dict(hist_sel='0.5')), [
            ['historical', u'Unittest D1 T1 L1 Q1'],
            ['historical', u'Unittest D1 T1 L1 Q2'],
            ['regular', u'Unittest D1 T1 L2 Q1'],
            ['regular', u'Unittest D1 T1 L2 Q2'],
        ])

        # All historical means there's no need to return regular questions
        self.assertEqual(getAlloc(dbLec2, dict(hist_sel='1')), [
            ['historical', u'Unittest D1 T1 L1 Q1'],
            ['historical', u'Unittest D1 T1 L1 Q2'],
        ])

        # Create lecture before with loads of questions
        lec0 = self.createTestLecture(qnCount=120, lecOpts=lambda i: dict(id='lec0'), tutorialObj=portal['dept1']['tut1'])
        dbLec0 = lec0.restrictedTraverse('@@quizdb-sync').getDbLecture()
        syncPloneQuestions(dbLec0, lec0)
        self.assertEqual(len(getAlloc(dbLec2, dict(hist_sel='0.7'))), 102)
        self.assertEqual(len(getAlloc(dbLec2, dict(hist_sel='0.2'))), 52)
