from .base import IntegrationTestCase, FunctionalTestCase
from .base import MANAGER_ID, USER_A_ID, USER_B_ID, USER_C_ID

import tutorweb.quizdb.tests.test_coin
from .test_coin import chooseOpener, MockHTTPHandler, nextResponse

class TotalCoinViewTest(IntegrationTestCase):
    def tearDown(self):
        tutorweb.quizdb.tests.test_coin.chooseOpener()

    def test_totalCoinView(self):
        chooseOpener(MockHTTPHandler)

        view = self.layer['portal'].unrestrictedTraverse('@@quizdb-coin-totalcoins')

        blockCount = 0323523
        tutorweb.quizdb.tests.test_coin.nextResponse = dict(
            result=blockCount,
        )
        self.assertEqual(
            int(view()),
            (blockCount - 1000) * 10000 + 24000000000,
        )

        blockCount = 50291283
        tutorweb.quizdb.tests.test_coin.nextResponse = dict(
            result=blockCount,
        )
        self.assertEqual(
            int(view()),
            (blockCount - 1000) * 10000 + 24000000000,
        )


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
                aqEntry(aAlloc, 0, True, 1.0),
                aqEntry(aAlloc, 0, True, 2.0),
                aqEntry(aAlloc, 0, True, 3.0),
                aqEntry(aAlloc, 0, True, 3.5),
                aqEntry(aAlloc, 0, True, 4.0),
                aqEntry(aAlloc, 0, True, 4.9),
                aqEntry(aAlloc, 0, True, 4.99),
                aqEntry(aAlloc, 0, True, 5.0),
                aqEntry(aAlloc, 0, True, 9.0),
                aqEntry(aAlloc, 0, True, 9.99),
                aqEntry(aAlloc, 0, True, 9.999),
            ],
        ))
        self.assertEqual(
            self.getJson('http://nohost/plone/@@quizdb-student-award', user=USER_A_ID),
            dict(coin_available=11000, walletId='', tx_id=None, history=[
                dict(amount=10000, claimed=False, lecture='/plone/dept1/tut1/lec1', time='2013-08-20T13:21:40'),
                dict(amount=1000,  claimed=False, lecture='/plone/dept1/tut1/lec1', time='2013-08-20T13:15:40'),
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
            dict(coin_available=11000, walletId='', tx_id=None, history=[
                dict(amount=11000, claimed=False, lecture='/plone/dept1/tut1/lec1', time='2013-08-20T13:23:40'),
            ])
        )

        # Claim some coin
        self.assertEqual(
            self.getJson('http://nohost/plone/@@quizdb-student-award', user=USER_A_ID, body=dict(
                walletId='$$UNITTEST:01',
            )),
            dict(coin_available=0, walletId='$$UNITTEST:01', tx_id='UNITTESTTX:$$UNITTEST:01:11000', history=[
                dict(amount=10000, claimed=True, lecture='/plone/dept1/tut1/lec1', time='2013-08-20T13:21:40'),
                dict(amount=1000,  claimed=True, lecture='/plone/dept1/tut1/lec1', time='2013-08-20T13:15:40'),
            ])
        )

        # B's coin isn't claimed
        self.assertEqual(
            self.getJson('http://nohost/plone/@@quizdb-student-award', user=USER_B_ID),
            dict(coin_available=11000, walletId='', tx_id=None, history=[
                dict(amount=11000, claimed=False, lecture='/plone/dept1/tut1/lec1', time='2013-08-20T13:23:40'),
            ])
        )

        # It's still gone, and we remember our wallet ID
        self.assertEqual(
            self.getJson('http://nohost/plone/@@quizdb-student-award', user=USER_A_ID),
            dict(coin_available=0, walletId='$$UNITTEST:01', tx_id=None, history=[
                dict(amount=10000, claimed=True, lecture='/plone/dept1/tut1/lec1', time='2013-08-20T13:21:40'),
                dict(amount=1000,  claimed=True, lecture='/plone/dept1/tut1/lec1', time='2013-08-20T13:15:40'),
            ])
        )

        # B's coin still isn't claimed
        self.assertEqual(
            self.getJson('http://nohost/plone/@@quizdb-student-award', user=USER_B_ID),
            dict(coin_available=11000, walletId='', tx_id=None, history=[
                dict(amount=11000, claimed=False, lecture='/plone/dept1/tut1/lec1', time='2013-08-20T13:23:40'),
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
            dict(coin_available=111000, walletId='$$UNITTEST:01', tx_id=None, history=[
                dict(amount=111000, claimed=False, lecture='/plone/dept1/tut1/lec2', time='2013-08-20T13:25:40'),
                dict(amount=10000, claimed=True, lecture='/plone/dept1/tut1/lec1', time='2013-08-20T13:21:40'),
                dict(amount=1000,  claimed=True, lecture='/plone/dept1/tut1/lec1', time='2013-08-20T13:15:40'),
            ])
        )

        # B's situation is still the same
        self.assertEqual(
            self.getJson('http://nohost/plone/@@quizdb-student-award', user=USER_B_ID),
            dict(coin_available=11000, walletId='', tx_id=None, history=[
                dict(amount=11000, claimed=False, lecture='/plone/dept1/tut1/lec1', time='2013-08-20T13:23:40'),
            ])
        )
