import calendar
import datetime
import dateutil.parser

from testfixtures import Replacer, test_time
import transaction

from .base import IntegrationTestCase, FunctionalTestCase
from .base import MANAGER_ID, USER_A_ID, USER_B_ID, USER_C_ID

import tutorweb.quizdb.tests.test_coin
from .test_coin import chooseOpener, MockHTTPHandler, nextResponse

from .. import coin

from tutorweb.quizdb.browser.coin import MAX_STUDENT_HOURLY_AWARD, MAX_DAILY_AWARD


def uDict(**kwargs):
    def unicodify(o):
        if isinstance(o, str):
            return unicode(o)
        return o

    return dict(
        (unicodify(k), unicodify(v))
        for k, v in kwargs.items()
    )

def toTimestamp(iso):
    """Convert ISO string into timestamp"""
    return calendar.timegm(dateutil.parser.parse(iso).timetuple())

def fromTimestamp(stamp):
    """Convert timestamp into readable string"""
    return datetime.datetime.fromtimestamp(stamp).strftime('%Y-%m-%d %H:%M:%S')

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
    def setUp(self):
        super(StudentUpdateViewFunctional, self).setUp()
        if not hasattr(self, 'replace'):
            self.replace = Replacer()

    def tearDown(self):
        self.replace.restore()
        super(StudentUpdateViewFunctional, self).tearDown()

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

        self.objectPublish(self.layer['portal']['dept1']['tut1']['lec1'])
        transaction.commit()

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
                aqEntry(aAlloc, 0, True, 9.25),
                aqEntry(aAlloc, 0, True, 9.75),
            ],
        ))
        self.assertEqual(
            self.getJson('http://nohost/plone/@@quizdb-student-award', user=USER_A_ID),
            uDict(coin_available=11000, walletId='', tx_id=None, history=[
                uDict(amount=10000, claimed=False, lecture='/plone/dept1/tut1/lec1', time=toTimestamp('2013-08-20T12:21:40')),
                uDict(amount=1000,  claimed=False, lecture='/plone/dept1/tut1/lec1', time=toTimestamp('2013-08-20T12:15:40')),
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
                dict(amount=11000, claimed=False, lecture='/plone/dept1/tut1/lec1', time=toTimestamp('2013-08-20T12:23:40')),
            ])
        )

        # Claim some coin
        self.assertEqual(
            self.getJson('http://nohost/plone/@@quizdb-student-award', user=USER_A_ID, body=dict(
                walletId='$$UNITTEST:01',
            )),
            dict(coin_available=0, walletId='$$UNITTEST:01', tx_id='UNITTESTTX:$$UNITTEST:01:11000', history=[
                dict(amount=10000, claimed=True, lecture='/plone/dept1/tut1/lec1', time=toTimestamp('2013-08-20T12:21:40')),
                dict(amount=1000,  claimed=True, lecture='/plone/dept1/tut1/lec1', time=toTimestamp('2013-08-20T12:15:40')),
            ])
        )

        # B's coin isn't claimed
        self.assertEqual(
            self.getJson('http://nohost/plone/@@quizdb-student-award', user=USER_B_ID),
            dict(coin_available=11000, walletId='', tx_id=None, history=[
                dict(amount=11000, claimed=False, lecture='/plone/dept1/tut1/lec1', time=toTimestamp('2013-08-20T12:23:40')),
            ])
        )

        # It's still gone, and we remember our wallet ID
        self.assertEqual(
            self.getJson('http://nohost/plone/@@quizdb-student-award', user=USER_A_ID),
            dict(coin_available=0, walletId='$$UNITTEST:01', tx_id=None, history=[
                dict(amount=10000, claimed=True, lecture='/plone/dept1/tut1/lec1', time=toTimestamp('2013-08-20T12:21:40')),
                dict(amount=1000,  claimed=True, lecture='/plone/dept1/tut1/lec1', time=toTimestamp('2013-08-20T12:15:40')),
            ])
        )

        # B's coin still isn't claimed
        self.assertEqual(
            self.getJson('http://nohost/plone/@@quizdb-student-award', user=USER_B_ID),
            dict(coin_available=11000, walletId='', tx_id=None, history=[
                dict(amount=11000, claimed=False, lecture='/plone/dept1/tut1/lec1', time=toTimestamp('2013-08-20T12:23:40')),
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
                dict(amount=111000, claimed=False, lecture='/plone/dept1/tut1/lec2', time=toTimestamp('2013-08-20T12:25:40')),
                dict(amount=10000, claimed=True, lecture='/plone/dept1/tut1/lec1', time=toTimestamp('2013-08-20T12:21:40')),
                dict(amount=1000,  claimed=True, lecture='/plone/dept1/tut1/lec1', time=toTimestamp('2013-08-20T12:15:40')),
            ])
        )

        # B's situation is still the same
        self.assertEqual(
            self.getJson('http://nohost/plone/@@quizdb-student-award', user=USER_B_ID),
            dict(coin_available=11000, walletId='', tx_id=None, history=[
                dict(amount=11000, claimed=False, lecture='/plone/dept1/tut1/lec1', time=toTimestamp('2013-08-20T12:23:40')),
            ])
        )

    def test_studentAward_overflow(self):
        """Make sure we take into account DB overflow"""
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

        # i.e. a bit more than the MySQL limit
        BIG_AWARD = 2**31 * 10
        self.replace('tutorweb.quizdb.browser.coin.MAX_STUDENT_HOURLY_AWARD', BIG_AWARD * 2)
        self.replace('tutorweb.quizdb.browser.coin.MAX_DAILY_AWARD', BIG_AWARD * 2)

        # Create lecture with a stonking award
        lec = self.createTestLecture(qnCount=2, lecOpts=lambda i: dict(settings=[
            dict(key='award_lecture_answered', value=str(BIG_AWARD)),
        ]))
        lecPath = '/'.join(lec.getPhysicalPath())
        lecSyncUri = 'http://nohost%s/@@quizdb-sync' % lecPath

        # Get an allocation to start things off
        aAlloc = self.getJson(lecSyncUri, user=USER_A_ID)

        # Get the award
        aAlloc = self.getJson(lecSyncUri, user=USER_A_ID, body=dict(
            user='Arnold',
            answerQueue=[
                aqEntry(aAlloc, 0, True, 1.0),
                aqEntry(aAlloc, 0, True, 2.0),
                aqEntry(aAlloc, 0, True, 5.0),
            ],
        ))
        self.assertEqual(
            self.getJson('http://nohost/plone/@@quizdb-student-award', user=USER_A_ID),
            uDict(coin_available=BIG_AWARD, walletId='', tx_id=None, history=[
                uDict(amount=BIG_AWARD,  claimed=False, lecture=lecPath, time=toTimestamp('2013-08-20T12:05:40')),
            ])
        )

        # Claim the award
        self.assertEqual(
            self.getJson('http://nohost/plone/@@quizdb-student-award', user=USER_A_ID, body=dict(
                walletId='$$UNITTEST:01',
            )),
            uDict(coin_available=0, walletId='$$UNITTEST:01', tx_id=u'UNITTESTTX:$$UNITTEST:01:21474836480', history=[
                uDict(amount=BIG_AWARD,  claimed=True, lecture=lecPath, time=toTimestamp('2013-08-20T12:05:40')),
            ])
        )

    def test_studentAward_hourlylimit(self):
        """There's an hourly limit on a user's withdrawals"""
        from tutorweb.quizdb.browser.coin import MAX_STUDENT_HOURLY_AWARD
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

        # Create lectures, with a total award bigger than the max
        HALF_AWARD = (MAX_STUDENT_HOURLY_AWARD / 2) + 2000
        lec = self.createTestLecture(qnCount=2, lecOpts=lambda i: dict(settings=[
            dict(key='award_lecture_answered', value=str(HALF_AWARD)),
            dict(key='award_lecture_aced', value=str(HALF_AWARD)),
        ]), tutOpts=lambda i: dict(settings=[
            dict(key='award_tutorial_aced', value="0"),
        ]))
        lecPath = '/'.join(lec.getPhysicalPath())
        lecSyncUri = 'http://nohost%s/@@quizdb-sync' % lecPath

        # Get an allocation to start things off
        aAlloc = self.getJson(lecSyncUri, user=USER_A_ID)

        self.replace('tutorweb.quizdb.browser.coin.utcnow', lambda: datetime.datetime(2017, 01, 01, 10, 1, 1))

        # Get answered award
        aAlloc = self.getJson(lecSyncUri, user=USER_A_ID, body=dict(
            user='Arnold',
            answerQueue=[
                aqEntry(aAlloc, 0, True, 1.0),
                aqEntry(aAlloc, 0, True, 2.0),
                aqEntry(aAlloc, 0, True, 5.0),
            ],
        ))
        self.assertEqual(
            self.getJson('http://nohost/plone/@@quizdb-student-award', user=USER_A_ID),
            uDict(coin_available=HALF_AWARD, walletId='', tx_id=None, history=[
                uDict(amount=HALF_AWARD,  claimed=False, lecture=lecPath, time=toTimestamp('2013-08-20T12:05:40')),
            ])
        )
        # Claim the award, get all of it
        self.assertEqual(
            self.getJson('http://nohost/plone/@@quizdb-student-award', user=USER_A_ID, body=dict(
                walletId='$$UNITTEST:01',
            )),
            uDict(coin_available=0, walletId='$$UNITTEST:01', tx_id=u'UNITTESTTX:$$UNITTEST:01:%d' % HALF_AWARD, history=[
                uDict(amount=HALF_AWARD,  claimed=True, lecture=lecPath, time=toTimestamp('2013-08-20T12:05:40')),
            ])
        )

        # Get aced award, but we don't get all of it yet.
        aAlloc = self.getJson(lecSyncUri, user=USER_A_ID, body=dict(
            user='Arnold',
            answerQueue=[
                aqEntry(aAlloc, 0, True, 8.0),
                aqEntry(aAlloc, 0, True, 9.999),
            ],
        ))
        self.assertEqual(
            self.getJson('http://nohost/plone/@@quizdb-student-award', user=USER_A_ID, body=dict(
                walletId='$$UNITTEST:01',
            )),
            uDict(coin_available=4000, walletId='$$UNITTEST:01', tx_id=u'UNITTESTTX:$$UNITTEST:01:%d' % (MAX_STUDENT_HOURLY_AWARD - HALF_AWARD), history=[
                uDict(amount=HALF_AWARD,  claimed=True, lecture=lecPath, time=toTimestamp('2013-08-20T12:09:40')), # NB: I've only half-claimed this
                uDict(amount=HALF_AWARD,  claimed=True, lecture=lecPath, time=toTimestamp('2013-08-20T12:05:40')),
            ])
        )

        # Try again, get an error that we can't claim the rest
        self.assertEqual(
            self.getJson('http://nohost/plone/@@quizdb-student-award', user=USER_A_ID, body=dict(
                walletId='$$UNITTEST:01',
            ), expectedStatus=500)['message'],
            u'You cannot redeem any more awards just yet'
        )

        # Wait an hour, we can.
        self.replace('tutorweb.quizdb.browser.coin.utcnow', lambda: datetime.datetime(2017, 01, 01, 11, 2, 1))
        self.assertEqual(
            self.getJson('http://nohost/plone/@@quizdb-student-award', user=USER_A_ID, body=dict(
                walletId='$$UNITTEST:01',
            )),
            uDict(coin_available=0, walletId='$$UNITTEST:01', tx_id=u'UNITTESTTX:$$UNITTEST:01:%d' % 4000, history=[
                uDict(amount=HALF_AWARD,  claimed=True, lecture=lecPath, time=toTimestamp('2013-08-20T12:09:40')),
                uDict(amount=HALF_AWARD,  claimed=True, lecture=lecPath, time=toTimestamp('2013-08-20T12:05:40')),
            ])
        )

    def test_studentAward_dailylimit(self):
        """There's a daily limit limit on all user's withdrawals"""
        from tutorweb.quizdb.browser.coin import MAX_DAILY_AWARD
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

        # Create lectures, with a total award slightly smaller than max
        BIG_AWARD = MAX_DAILY_AWARD + 1000
        lec = self.createTestLecture(qnCount=2, lecOpts=lambda i: dict(settings=[
            dict(key='award_lecture_answered', value=str(BIG_AWARD)),
            dict(key='award_lecture_aced', value=str(BIG_AWARD)),
        ]), tutOpts=lambda i: dict(settings=[
            dict(key='award_tutorial_aced', value="0"),
        ]))
        lecPath = '/'.join(lec.getPhysicalPath())
        lecSyncUri = 'http://nohost%s/@@quizdb-sync' % lecPath

        # Get an allocation to start things off
        aAlloc = self.getJson(lecSyncUri, user=USER_A_ID)
        bAlloc = self.getJson(lecSyncUri, user=USER_B_ID)

        self.replace('tutorweb.quizdb.browser.coin.utcnow', lambda: datetime.datetime(2017, 01, 01, 10, 1, 1))
        self.replace('tutorweb.quizdb.browser.coin.MAX_STUDENT_HOURLY_AWARD', BIG_AWARD * 2)

        # Get the answered award for both A & B
        aAlloc = self.getJson(lecSyncUri, user=USER_A_ID, body=dict(
            user='Arnold',
            answerQueue=[
                aqEntry(aAlloc, 0, True, 1.0),
                aqEntry(aAlloc, 0, True, 2.0),
                aqEntry(aAlloc, 0, True, 5.0),
            ],
        ))
        bAlloc = self.getJson(lecSyncUri, user=USER_B_ID, body=dict(
            user='Betty',
            answerQueue=[
                aqEntry(bAlloc, 0, True, 1.0, user=USER_B_ID),
                aqEntry(bAlloc, 0, True, 2.0, user=USER_B_ID),
                aqEntry(bAlloc, 0, True, 5.0, user=USER_B_ID),
            ],
        ))

        # A can claim - even though the big award is bigger than the limit
        self.assertEqual(
            self.getJson('http://nohost/plone/@@quizdb-student-award', user=USER_A_ID, body=dict(
                walletId='$$UNITTEST:01',
            )),
            uDict(coin_available=0, walletId='$$UNITTEST:01', tx_id=u'UNITTESTTX:$$UNITTEST:01:%d' % BIG_AWARD, history=[
                uDict(amount=BIG_AWARD, claimed=True, lecture=lecPath, time=toTimestamp('2013-08-20T12:05:40')),
            ])
        )

        # B also has award, but isn't allowed
        self.assertEqual(
            self.getJson('http://nohost/plone/@@quizdb-student-award', user=USER_B_ID, body=dict(
            )),
            uDict(coin_available=BIG_AWARD, walletId='', tx_id=None, history=[
                uDict(amount=BIG_AWARD, claimed=False, lecture=lecPath, time=toTimestamp('2013-08-20T12:11:40')),
            ])
        )
        self.assertEqual(
            self.getJson('http://nohost/plone/@@quizdb-student-award', user=USER_B_ID, body=dict(
                walletId='$$UNITTEST:02',
            ), expectedStatus=500)['message'],
            u'We have distributed all awards available for today',
        )

        # Wait a day, and B is allowed
        self.replace('tutorweb.quizdb.browser.coin.utcnow', lambda: datetime.datetime(2017, 01, 02, 11, 2, 1))
        self.assertEqual(
            self.getJson('http://nohost/plone/@@quizdb-student-award', user=USER_B_ID, body=dict(
                walletId='$$UNITTEST:02',
            )),
            uDict(coin_available=0, walletId='$$UNITTEST:02', tx_id=u'UNITTESTTX:$$UNITTEST:02:%d' % BIG_AWARD, history=[
                uDict(amount=BIG_AWARD, claimed=True, lecture=lecPath, time=toTimestamp('2013-08-20T12:11:40')),
            ])
        )

    def test_studentAward_captchafail(self):
        """Make sure captchas can fail"""
        coin.coin_config.CAPTCHA_KEY = 'keykeykey'

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

        # Create lecture with award
        lec = self.createTestLecture(qnCount=2, lecOpts=lambda i: dict(settings=[
            dict(key='award_lecture_answered', value="1000"),
        ]))
        lecPath = '/'.join(lec.getPhysicalPath())
        lecSyncUri = 'http://nohost%s/@@quizdb-sync' % lecPath

        # Get an allocation to start things off
        aAlloc = self.getJson(lecSyncUri, user=USER_A_ID)

        # Get the award
        aAlloc = self.getJson(lecSyncUri, user=USER_A_ID, body=dict(
            user='Arnold',
            answerQueue=[
                aqEntry(aAlloc, 0, True, 1.0),
                aqEntry(aAlloc, 0, True, 2.0),
                aqEntry(aAlloc, 0, True, 5.0),
            ],
        ))

        def fakeCaptcha(resp, key, remote_addr):
            class FakeResponse:
                pass

            self.assertEqual(resp, 'resprespresp')
            self.assertEqual(key, 'keykeykey')
            self.assertEqual(remote_addr, '')

            out = FakeResponse()
            out.error_code = 0
            out.is_valid = False
            return out

        self.replace('norecaptcha.captcha.submit', fakeCaptcha)

        # Try to claim the award, can't without a captcha value
        self.assertEqual(
            self.getJson('http://nohost/plone/@@quizdb-student-award', user=USER_A_ID, body=dict(
                walletId='123456789101112',
                captchaResponse="resprespresp",
            ), expectedStatus=500)['message'],
            u'Invalid CAPTCHA',
        )
