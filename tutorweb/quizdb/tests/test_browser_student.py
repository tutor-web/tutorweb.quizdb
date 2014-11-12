from z3c.saconfig import Session
from zope.testing.loggingsupport import InstalledHandler

from plone.app.testing import login

from Products.CMFCore.utils import getToolByName

from tutorweb.quizdb import db
from .base import IntegrationTestCase, FunctionalTestCase
from .base import MANAGER_ID, USER_A_ID, USER_B_ID, USER_C_ID


class StudentUpdateViewTest(IntegrationTestCase):
    def setUp(self):
        """Set up a class ready for testing"""
        self.loghandlers = dict(
            sqlalchemy=InstalledHandler('sqlalchemy.engine'),
            sync=InstalledHandler('tutorweb.quizdb.browser.sync')
        )

    def logs(self, name='sqlalchemy'):
        return [x.getMessage() for x in self.loghandlers[name].records]

    def test_studentUpdate(self):
        """Should be able to update all student's email addresses in one go"""
        portal = self.layer['portal']

        # Login as user B and C, to get them in the DB
        login(portal, USER_A_ID)
        self.assertEqual(self.getCurrentStudent().userName, USER_A_ID)
        login(portal, USER_C_ID)
        self.assertEqual(self.getCurrentStudent().userName, USER_C_ID)

        # Change all email addresses, run update
        login(portal, MANAGER_ID)
        mtool = getToolByName(portal, 'portal_membership')
        mtool.getMemberById(USER_A_ID).setMemberProperties(dict(
            email='alfred@example.com',
        ))
        mtool.getMemberById(USER_B_ID).setMemberProperties(dict(
            email='bert@example.com',
        ))
        mtool.getMemberById(USER_C_ID).setMemberProperties(dict(
            email='catherine@example.com',
        ))
        update = portal.restrictedTraverse('quizdb-student-update').asDict(None)
        self.assertEqual(update['success'], True)

        # Email addresses have already changed, apart from B who wasn't there
        for dbStudent in Session.query(db.Student).all():
            self.assertEqual(
                'alfred@example.com' if dbStudent.userName == USER_A_ID
                else 'Betty@example.com' if dbStudent.userName == USER_B_ID
                else 'catherine@example.com',
                dbStudent.eMail,
            )
            pass

        # Set email addresses back again
        for id in [USER_A_ID, USER_B_ID, USER_C_ID]:
            mtool.getMemberById(id).setMemberProperties(dict(
                email=id + '@example.com',
            ))

    def getCurrentStudent(self):
        """Use getCurrentStudent() to create students"""
        lec = self.layer['portal']['dept1']['tut1']['lec1']
        return lec.restrictedTraverse('quizdb-sync').getCurrentStudent()


class StudentUpdateViewFunctional(FunctionalTestCase):
    def test_answerQueue_StudentAward(self):
        """Should be able to claim awards into wallets"""
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

        # Get an allocation to start things off
        aAlloc = self.getJson('http://nohost/plone/dept1/tut1/lec1/@@quizdb-sync', user=USER_A_ID)
        bAlloc = self.getJson('http://nohost/plone/dept1/tut1/lec1/@@quizdb-sync', user=USER_B_ID)

        # Get 10 right, ace the lecture
        aAlloc = self.getJson('http://nohost/plone/dept1/tut1/lec1/@@quizdb-sync', user=USER_A_ID, body=dict(
            user='Arnold',
            answerQueue=[
                aqEntry(aAlloc, 0, True, 0.1),
                aqEntry(aAlloc, 0, True, 0.2),
                aqEntry(aAlloc, 0, True, 0.3),
                aqEntry(aAlloc, 0, True, 0.4),
                aqEntry(aAlloc, 0, True, 0.5),
                aqEntry(aAlloc, 0, True, 0.6),
                aqEntry(aAlloc, 0, True, 0.7),
                aqEntry(aAlloc, 0, True, 0.8),
                aqEntry(aAlloc, 0, True, 0.9),
                aqEntry(aAlloc, 0, True, 1.0),
                aqEntry(aAlloc, 0, True, 10.0),
            ],
        ))
        self.assertEqual(
            self.getJson('http://nohost/plone/@@quizdb-student-award', user=USER_A_ID),
            dict(coin_available=11, walletId='', tx_id=None, history=[
                dict(amount=10, claimed=False, lecture='/plone/dept1/tut1/lec1', time='2013-08-20T13:21:40'),
                dict(amount=1,  claimed=False, lecture='/plone/dept1/tut1/lec1', time='2013-08-20T13:15:40'),
            ])
        )

        # B aces the lecture straight off
        bAlloc = self.getJson('http://nohost/plone/dept1/tut1/lec1/@@quizdb-sync', user=USER_B_ID, body=dict(
            user='Betty',
            answerQueue=[
                aqEntry(bAlloc, 0, True, 10.0, user=USER_B_ID),
            ],
        ))
        self.assertEqual(
            self.getJson('http://nohost/plone/@@quizdb-student-award', user=USER_B_ID),
            dict(coin_available=10, walletId='', tx_id=None, history=[
                dict(amount=10, claimed=False, lecture='/plone/dept1/tut1/lec1', time='2013-08-20T13:23:40'),
            ])
        )

        # Claim some coin
        self.assertEqual(
            self.getJson('http://nohost/plone/@@quizdb-student-award', user=USER_A_ID, body=dict(
                walletId='$$UNITTEST:01',
            )),
            dict(coin_available=0, walletId='$$UNITTEST:01', tx_id='UNITTESTTX:$$UNITTEST:01:11', history=[
                dict(amount=10, claimed=True, lecture='/plone/dept1/tut1/lec1', time='2013-08-20T13:21:40'),
                dict(amount=1,  claimed=True, lecture='/plone/dept1/tut1/lec1', time='2013-08-20T13:15:40'),
            ])
        )

        # B's coin isn't claimed
        self.assertEqual(
            self.getJson('http://nohost/plone/@@quizdb-student-award', user=USER_B_ID),
            dict(coin_available=10, walletId='', tx_id=None, history=[
                dict(amount=10, claimed=False, lecture='/plone/dept1/tut1/lec1', time='2013-08-20T13:23:40'),
            ])
        )

        # It's still gone, and we remember our wallet ID
        self.assertEqual(
            self.getJson('http://nohost/plone/@@quizdb-student-award', user=USER_A_ID),
            dict(coin_available=0, walletId='$$UNITTEST:01', tx_id=None, history=[
                dict(amount=10, claimed=True, lecture='/plone/dept1/tut1/lec1', time='2013-08-20T13:21:40'),
                dict(amount=1,  claimed=True, lecture='/plone/dept1/tut1/lec1', time='2013-08-20T13:15:40'),
            ])
        )

        # B's coin still isn't claimed
        self.assertEqual(
            self.getJson('http://nohost/plone/@@quizdb-student-award', user=USER_B_ID),
            dict(coin_available=10, walletId='', tx_id=None, history=[
                dict(amount=10, claimed=False, lecture='/plone/dept1/tut1/lec1', time='2013-08-20T13:23:40'),
            ])
        )

        # Earn some more coins, these haven't been claimed
        aAlloc = self.getJson('http://nohost/plone/dept1/tut1/lec2/@@quizdb-sync', user=USER_A_ID, body=dict(
            user='Arnold',
            answerQueue=[
                aqEntry(aAlloc, 0, True, 10.0),
            ],
        ))
        self.assertEqual(
            self.getJson('http://nohost/plone/@@quizdb-student-award', user=USER_A_ID),
            dict(coin_available=110, walletId='$$UNITTEST:01', tx_id=None, history=[
                dict(amount=110, claimed=False, lecture='/plone/dept1/tut1/lec2', time='2013-08-20T13:25:40'),
                dict(amount=10, claimed=True, lecture='/plone/dept1/tut1/lec1', time='2013-08-20T13:21:40'),
                dict(amount=1,  claimed=True, lecture='/plone/dept1/tut1/lec1', time='2013-08-20T13:15:40'),
            ])
        )

        # B's situation is still the same
        self.assertEqual(
            self.getJson('http://nohost/plone/@@quizdb-student-award', user=USER_B_ID),
            dict(coin_available=10, walletId='', tx_id=None, history=[
                dict(amount=10, claimed=False, lecture='/plone/dept1/tut1/lec1', time='2013-08-20T13:23:40'),
            ])
        )
