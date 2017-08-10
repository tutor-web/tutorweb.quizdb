import socket
import uuid
import re

from sqlalchemy.orm.exc import NoResultFound

from z3c.saconfig import Session

from tutorweb.quizdb import db

def getDbHost():
    """
    Find / create the object for the current host
    """
    try:
        dbHost = (Session.query(db.Host)
            .filter(db.Host.hostId == 1)
            .one())
    except NoResultFound:
        dbHost = db.Host(fqdn=socket.getfqdn())
        Session.add(dbHost)

    # Make sure we have a key associated with this host
    if not dbHost.hostKey:
        dbHost.hostKey = str(uuid.uuid4().get_hex())

    Session.flush()
    return dbHost


def getDbStudent(username, email=None):
    """
    Find / create a student object with (username), updating (email)
    if supplied. Return object
    """
    dbHost = getDbHost()
    try:
        dbStudent = Session.query(db.Student) \
            .filter_by(hostId=dbHost.hostId) \
            .filter_by(userName=username) \
            .one()
    except NoResultFound:
        dbStudent = db.Student(
            userName=username,
            hostId=dbHost.hostId,
            eMail=username,  # NB: email can't be NULL, so assume username is an email address
        )
        Session.add(dbStudent)
    if email:
        dbStudent.eMail = email
    Session.flush()
    return dbStudent


def getDbLecture(plonePath):
    """
    Find a lecture object corresponding to plonePath
    (should have been created via. sync)
    """
    # Hack around an upgrade bug
    plonePath = re.sub('/tutor-web/tutor-web/', '/tutor-web/', plonePath)

    try:
        dbLec = Session.query(db.Lecture) \
            .filter(db.Lecture.hostId == getDbHost().hostId) \
            .filter(db.Lecture.plonePath == plonePath).one()
        return dbLec
    except NoResultFound:
        raise ValueError("lecture %s does not exist" % plonePath)
