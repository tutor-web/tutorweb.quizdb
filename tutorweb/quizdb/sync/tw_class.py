from sqlalchemy.orm.exc import NoResultFound
from z3c.saconfig import Session

from tutorweb.quizdb import db
from tutorweb.quizdb.utils import getDbStudent

def syncClassSubscriptions(classObj):
    """
    Make sure all students in a class are subscribed
    """
    ploneClassPath = '/'.join(classObj.getPhysicalPath())

    for s in classObj.students:
        dbStudent = getDbStudent(s)

        try:
            dbSub = (Session.query(db.Subscription)
                .filter_by(student=dbStudent)
                .filter_by(plonePath=ploneClassPath)
                .one())
        except NoResultFound:
            Session.add(db.Subscription(
                student=dbStudent,
                plonePath=ploneClassPath,
            ))
        Session.flush()
