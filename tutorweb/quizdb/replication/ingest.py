import collections
import datetime
import uuid
import logging
# logging.getLogger('sqlalchemy.engine').setLevel(logging.DEBUG)

from sqlalchemy.orm.exc import NoResultFound
from z3c.saconfig import Session

from tutorweb.quizdb import db


def updateHost(fqdn, hostKey):
    """Insert/update a host entry"""
    try:
        dbHost = (Session.query(db.Host)
            .filter(db.Host.fqdn == fqdn)
            .one())
        dbHost.hostKey = hostKey
    except NoResultFound:
        dbHost = db.Host(fqdn=fqdn, hostKey=hostKey)
        Session.add(dbHost)
    Session.flush()

    return dict(
        fqdn=dbHost.fqdn,
        hostKey=str(dbHost.hostKey),
    )


def findMissingEntries(dataRawEntries, dbQuery, sortCols=[], ignoreCols=[], idMap={}):
    """Hunt for entries in dataEntries that aren't in dbEntries"""
    def translateData(entries):
        """Translate dict to use local ids, datetime objects, resort"""
        def tlate(k, v):
            if k in idMap:
                return (k, idMap[k][v])
            elif k in ['timeStart', 'timeEnd', 'awardTime']:
                return (k, datetime.datetime.utcfromtimestamp(v))
            elif k in ['ugQuestionGuid'] and v:
                return (k, uuid.UUID(v))
            else:
                return (k, v)

        return sorted([
            dict(tlate(k, v) for (k, v) in d.items() if k not in ignoreCols)
            for d in entries
        ], key=lambda k: tuple(k.get(c) for c in sortCols))

    def getNext(iter):
        entry = iter.next()
        if hasattr(entry, 'get'):
            return (entry, tuple(entry[c] for c in sortCols))
        return (entry, tuple(getattr(entry, c) for c in sortCols))

    # Convert inputs into 2 iterators over our data
    if len(dataRawEntries) == 0:
        return # Nothing to do
    dataEntries = iter(translateData(dataRawEntries))
    dbEntries = iter(dbQuery)
    (dataTuple, dbTuple) = (None, None,)

    try:
        (dataEntry, dataTuple) = getNext(dataEntries)
        (dbEntry, dbTuple) = getNext(dbEntries)
        while True:
            if dataTuple > dbTuple:
                # Extra entries in DB, skip over them
                (dbEntry, dbTuple) = getNext(dbEntries)
                continue
            if dataTuple < dbTuple:
                # Extra entries in data, yield.
                yield dataEntry
            # Matching / extra entry, keep going.
            (dataEntry, dataTuple) = getNext(dataEntries)
    except StopIteration:
        pass

    try:
        # Clean up any extra entries at end
        while dbTuple is None or dataTuple > dbTuple:
            yield dataEntry
            (dataEntry, dataTuple) = getNext(dataEntries)
    except StopIteration:
        pass


def ingestDateRange(data):
    idMap = collections.defaultdict(dict)
    inserts = {}

    # Fetch range
    dateFrom = datetime.datetime.utcfromtimestamp(data['date_from'])
    dateTo = datetime.datetime.utcfromtimestamp(data['date_to'])

    # Check all host keys match our stored versions, and map to our IDs
    for host in data['host']:
        try:
            dbHost = Session.query(db.Host).filter(db.Host.fqdn == host['fqdn']).one()
        except NoResultFound:
            raise ValueError("Unknown host %s, cannot import results" % host['fqdn'])
        if dbHost.hostKey != host['hostKey']:
            raise ValueError("Mismatching host key for %s: %s vs %s" % (
                db.Host.fqdn,
                dbHost.hostKey,
                host['hostKey'],
            ))
        idMap['hostId'][host['hostId']] = dbHost.hostId

    # Map students to our IDs
    inserts['student'] = 0
    for student in data['student']:
        try:
            dbStudent = (Session.query(db.Student)
                .filter(db.Student.hostId == idMap['hostId'][student['hostId']])
                .filter(db.Student.userName == student['userName'])
                .one())
            dbStudent.userName = student['userName']
            dbStudent.email = student['eMail']
        except NoResultFound:
            dbStudent = db.Student(
                hostId=idMap['hostId'][student['hostId']],
                userName=student['userName'],
                eMail=student['eMail'],
            )
            Session.add(dbStudent)
            Session.flush()
            inserts['student'] += 1
        idMap['studentId'][student['studentId']] = dbStudent.studentId
    Session.flush()

    # Map questions to our IDs
    for question in data['question']:
        try:
            dbQuestionId = (Session.query(db.Question.questionId)
                .filter(db.Question.plonePath == question['plonePath'])
                .one())
        except NoResultFound:
            raise ValueError("Missing question at %s" % question['plonePath'])
        idMap['questionId'][question['questionId']] = dbQuestionId[0]
    Session.flush()

    # Map lectures to our IDs
    inserts['lecture'] = 0
    for lecture in data['lecture']:
        try:
            dbLecture = (Session.query(db.Lecture)
                .filter(db.Lecture.hostId == idMap['hostId'][lecture['hostId']])
                .filter(db.Lecture.plonePath == lecture['plonePath'])
                .one())
            dbLecture.plonePath = lecture['plonePath']
        except NoResultFound:
            dbLecture = db.Lecture(
                hostId=idMap['hostId'][lecture['hostId']],
                plonePath=lecture['plonePath'],
            )
            Session.add(dbLecture)
            Session.flush()
            inserts['lecture'] += 1
        idMap['lectureId'][lecture['lectureId']] = dbLecture.lectureId
    Session.flush()

    # Filter out answer student/question/timeEnd combinations already stored in DB
    inserts['answer'] = 0
    for missingEntry in findMissingEntries(
            data['answer'],
            Session.query(db.Answer)
                # NB: In theory we should filter by student too, but shouldn't make much difference to result
                .filter(db.Answer.lectureId.in_(idMap['lectureId'].values()))
                .filter(db.Answer.timeEnd.between(dateFrom, dateTo))
                .order_by(db.Answer.lectureId, db.Answer.studentId, db.Answer.timeEnd),
            sortCols=['lectureId', 'studentId', 'timeEnd'],
            ignoreCols=['answerId'],
            idMap=idMap):
        Session.add(db.Answer(**missingEntry))
        inserts['answer'] += 1

    inserts['lecture_setting'] = 0
    answerDateFilter = db.Answer.timeEnd.between(dateFrom, dateTo)
    for missingEntry in findMissingEntries(
            data['lecture_setting'],
            Session.query(db.LectureSetting)
                .join(db.Answer, db.Answer.lectureId == db.LectureSetting.lectureId)
                .filter(answerDateFilter)
                .order_by(db.LectureSetting.lectureId, db.LectureSetting.studentId, db.LectureSetting.key),
            sortCols=['lectureId', 'studentId', 'key'],
            idMap=idMap):
        Session.add(db.LectureSetting(**missingEntry))
        inserts['lecture_setting'] += 1

    inserts['coin_award'] = 0
    for missingEntry in findMissingEntries(
            data['coin_award'],
            Session.query(db.CoinAward)
                .filter(db.CoinAward.studentId.in_(idMap['studentId'].values()))
                .filter(db.CoinAward.awardTime.between(dateFrom, dateTo))
                .order_by(db.CoinAward.studentId, db.CoinAward.awardTime),
            sortCols=['studentId', 'awardTime'],
            ignoreCols=['coinAwardId'],
            idMap=idMap):
        Session.add(db.CoinAward(**missingEntry))
        inserts['coin_award'] += 1

    inserts['ug_question'] = 0
    for missingEntry in findMissingEntries(
            data['ug_question'],
            Session.query(db.UserGeneratedQuestion)
                .filter(db.UserGeneratedQuestion.studentId.in_(idMap['studentId'].values()))
                .order_by(db.UserGeneratedQuestion.studentId, db.UserGeneratedQuestion.ugQuestionGuid),
            sortCols=['studentId', 'ugQuestionGuid'],
            ignoreCols=['ugQuestionId'],
            idMap=idMap):
        Session.add(db.UserGeneratedQuestion(**missingEntry))
        inserts['ug_question'] += 1

    inserts['ug_answer'] = 0
    for missingEntry in findMissingEntries(
            data['ug_answer'],
            Session.query(db.UserGeneratedAnswer)
                .filter(db.UserGeneratedAnswer.studentId.in_(idMap['studentId'].values()))
                .order_by(db.UserGeneratedAnswer.studentId, db.UserGeneratedAnswer.ugQuestionGuid),
            sortCols=['studentId', 'ugQuestionGuid'],
            ignoreCols=['ugAnswerId'],
            idMap=idMap):
        Session.add(db.UserGeneratedAnswer(**missingEntry))
        inserts['ug_answer'] += 1

    Session.flush()
    return inserts