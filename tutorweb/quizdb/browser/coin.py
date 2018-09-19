import calendar
import datetime
# import logging
# logging.getLogger('sqlalchemy.engine').setLevel(logging.DEBUG)

from sqlalchemy.sql import func
from z3c.saconfig import Session

try:
    from norecaptcha import captcha
except ImportError:
    captcha = None

from tutorweb.quizdb import db
from ..config import coin_config
from .base import JSONBrowserView, PlainTextBrowserView
from ...quizdb import coin

MAX_STUDENT_HOURLY_AWARD = 7 * 10**6 * 1000  # 7 million milliSMLY
MAX_DAILY_AWARD = 15 * 10**6 * 1000  # 15 million milliSMLY
EIAS_WALLET = 'BPj18BBacYdvEnqgJqKVRNFQrw5ka76gxy'

class TotalCoinView(PlainTextBrowserView):
    """Show approximate number of coins"""
    def asPlainText(self, data={}):
        yield str((coin.getBlockCount() - 1000) * 10000 + 24000000000)


def utcnow():
    return datetime.datetime.utcnow()


class StudentAwardView(JSONBrowserView):
    """Show coins awarded to student"""

    def asDict(self, data=None):
        """Show coins given to student"""
        student = self.getCurrentStudent()

        (lastAwardTime, walletId, coinClaimed) = (Session.query(
            func.max(db.CoinAward.awardTime),
            func.max(db.CoinAward.walletId), #TODO: Should be last, not max
            func.sum(db.CoinAward.amount),
        )
            .filter(db.CoinAward.studentId == student.studentId)
            .first())
        if coinClaimed is None:
            lastAwardTime = 0
            coinClaimed = 0
            walletId = ''

        history = []
        coinAwarded = 0
        for row in (Session.query(db.Answer.timeEnd, db.Answer.coinsAwarded, db.Lecture.plonePath)
                .join(db.Lecture)
                .filter(db.Lecture.hostId == self.getDbHost().hostId)
                .filter(db.Answer.studentId == student.studentId)
                .filter(db.Answer.practice == False)
                .filter(db.Answer.coinsAwarded > 0)
                .order_by(db.Answer.timeEnd, db.Lecture.plonePath)):

            coinAwarded += row[1]
            history.insert(0, dict(
                lecture=row[2],
                time=calendar.timegm(row[0].timetuple()) if row[1] else None,
                amount=row[1],
                claimed=(coinAwarded <= coinClaimed and row[0] <= lastAwardTime)
            ))

        # Check if wallet ID is provided, if so pay up.
        txId = None
        if data is not None and data.get('walletId', None):
            walletId = data['walletId']

            # Validate Captcha if not a unittest wallet
            if walletId.startswith('$$UNITTEST'):
                pass
            elif walletId =='$$DONATE:EIAS':
                walletId = EIAS_WALLET
            else:
                remote_addr = self.request.get('HTTP_X_FORWARDED_FOR', '').split(',')[0]
                if not remote_addr:
                    remote_addr = self.request.get('REMOTE_ADDR')

                if captcha:
                    res = captcha.submit(
                        data.get('captchaResponse', ''),
                        coin_config.CAPTCHA_KEY,
                        remote_addr
                    )
                    if res.error_code:
                        raise ValueError("Could not validate CAPTCHA")
                    elif not res.is_valid:
                        raise ValueError("Invalid CAPTCHA")

            # Have we already given out our maximum for today?
            dailyTotalAward = (Session.query(func.sum(db.CoinAward.amount))
                .filter(db.CoinAward.awardTime > (utcnow() - datetime.timedelta(days=1)))
                .one())[0] or 0
            if dailyTotalAward > MAX_DAILY_AWARD:
                raise ValueError("We have distributed all awards available for today")

            # Has this student already got their coins for the hour?
            hourlyStudentTotal = (Session.query(func.sum(db.CoinAward.amount))
                .filter(db.CoinAward.studentId == student.studentId)
                .filter(db.CoinAward.awardTime > (utcnow() - datetime.timedelta(hours=1)))
                .one())[0] or 0
            coinOwed = min(
                coinAwarded - coinClaimed,
                MAX_STUDENT_HOURLY_AWARD - hourlyStudentTotal,
            )
            if coinOwed == 0 and (coinAwarded - coinClaimed) > 0:
                raise ValueError("You cannot redeem any more awards just yet")

            # Perform transaction
            txId = coin.sendTransaction(walletId, coinOwed)

            # Worked, so update database
            Session.add(db.CoinAward(
                studentId=student.studentId,
                amount=int(coinOwed),
                walletId=walletId,
                txId=txId,
                awardTime=utcnow(),  # NB: So it gets mocked in the tests
            ))
            Session.flush()

            # Worked, so should be even now
            for h in history:
                h['claimed'] = True
            coinClaimed += coinOwed

        return dict(
            walletId=walletId,
            history=history,
            coin_available=int(coinAwarded - coinClaimed),
            tx_id=txId,
        )


class RedeemUnclaimedView(PlainTextBrowserView):
    def asPlainText(self, data={}):
        if 'dry-run' in data:
            yield "*** DRY RUN ***\n"

        total_reclaimed = 0
        for (studentId, unclaimed) in Session.execute("""
SELECT a.studentId,
    SUM(coinsAwarded) -
    COALESCE((SELECT SUM(amount) FROM coinAward ca WHERE ca.studentId = a.studentId), 0)
    AS unclaimed
FROM answer a, student s
WHERE coinsAwarded > 0
AND a.studentId = s.studentId AND s.hostId = 1
AND a.timeEnd < CURDATE() - INTERVAL 2 YEAR
AND a.studentId NOT IN (SELECT DISTINCT c.studentId FROM coinAward c WHERE c.awardTime >= CURDATE() - INTERVAL 2 YEAR)
GROUP BY a.studentId
HAVING unclaimed > 0
        """):

            total_reclaimed += int(unclaimed)
            if 'dry-run' in data:
                txId = 'DRY_RUN'
            else:
                txId = coin.sendTransaction(EIAS_WALLET, unclaimed, message="Auto-reclaim of awards")
                # Worked, so update database
                Session.add(db.CoinAward(
                    studentId=studentId,
                    amount=int(unclaimed),
                    walletId=EIAS_WALLET,
                    txId=txId,
                    awardTime=utcnow(),  # NB: So it gets mocked in the tests
                ))
                Session.flush()
            yield "StudentId: %d Unclaimed: %d Transaction: %s\n" % (
                studentId,
                unclaimed,
                txId,
            )
        yield "Total: %d\n" % total_reclaimed
