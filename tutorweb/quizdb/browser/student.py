# import logging
# logging.getLogger('sqlalchemy.engine').setLevel(logging.DEBUG)

from sqlalchemy.sql import func
from z3c.saconfig import Session

from Products.CMFCore.utils import getToolByName

from tutorweb.quizdb import db
from .base import JSONBrowserView
from ...quizdb import coin

class StudentUpdateView(JSONBrowserView):
    """Update all student email addresses"""

    def asDict(self, data):
        """For all students already in DB, update details"""
        mtool = getToolByName(self.context, 'portal_membership')
        for dbStudent in Session.query(db.Student).all():
            mb = mtool.getMemberById(dbStudent.userName)
            dbStudent.eMail = mb.getProperty('email')
        Session.flush()
        return dict(success=True)


class StudentAwardView(JSONBrowserView):
    """Show coins awarded to student"""

    def asDict(self, data):
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
                .filter(db.Answer.studentId == student.studentId)
                .filter(db.Answer.practice == False)
                .filter(db.Answer.coinsAwarded > 0)
                .order_by(db.Answer.timeEnd, db.Lecture.plonePath)):

            coinAwarded += row[1]
            history.insert(0, dict(
                lecture=row[2],
                time=row[0].isoformat() if row[1] else None,
                amount=row[1],
                claimed=(coinAwarded <= coinClaimed and row[0] <= lastAwardTime)
            ))

        # Check if wallet ID is provided, if so pay up.
        txId = None
        if data is not None and data.get('walletId', None):
            walletId = data['walletId']
            coinOwed = (coinAwarded - coinClaimed)

            # Perform transaction
            txId = coin.sendTransaction(walletId, coinOwed)

            # Worked, so update database
            Session.add(db.CoinAward(
                studentId=student.studentId,
                amount=int(coinOwed),
                walletId=walletId,
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
