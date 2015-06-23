import collections
import datetime
import uuid
import logging

from sqlalchemy.orm.exc import NoResultFound
from z3c.saconfig import Session

from tutorweb.quizdb import db

from Globals import DevelopmentMode
if DevelopmentMode:
    logging.getLogger('sqlalchemy.engine').setLevel(logging.INFO)


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


def findMissingEntries(dataRawEntries, dbQuery, sortCols=[], ignoreCols=[], idMap={}, returnUpdates=False):
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
                # New entry to return
                yield (dataEntry, None)
            elif returnUpdates:
                yield (dataEntry, dbEntry)
            (dataEntry, dataTuple) = getNext(dataEntries)
    except StopIteration:
        pass

    try:
        # Clean up any extra entries at end
        while dbTuple is None or dataTuple > dbTuple:
            yield (dataEntry, None)
            (dataEntry, dataTuple) = getNext(dataEntries)
    except StopIteration:
        pass


def ingestData(data):
    idMap = collections.defaultdict(dict)
    inserts = {}

    # Check all host keys match our stored versions, and map to our IDs
    for host in data['host']:
        try:
            dbHost = Session.query(db.Host).filter(db.Host.hostKey == host['hostKey']).one()
        except NoResultFound:
            raise ValueError("Unknown host %s:%s, cannot import results" % (host['hostKey'], host['fqdn']))
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

    # Any answer entries we fetch should be at least as new as the oldest incoming entry
    minVal = None
    for a in data['answer']:
        if minVal is None or a['timeEnd'] < minVal:
            minVal = a['timeEnd']
    answerFilter = db.Answer.timeEnd.__ge__(datetime.datetime.utcfromtimestamp(minVal or 0))
    minVal = None
    for a in data['coin_award']:
        if minVal is None or a['awardTime'] < minVal:
            minVal = a['awardTime']
    coinAwardFilter = db.CoinAward.awardTime.__ge__(datetime.datetime.utcfromtimestamp(minVal or 0))

    # Filter out answer student/question/timeEnd combinations already stored in DB
    inserts['answer'] = 0
    for (dataEntry, dbEntry) in findMissingEntries(
            data['answer'],
            Session.query(db.Answer)
                .filter(db.Answer.lectureId.in_(idMap['lectureId'].values()))
                .filter(db.Answer.studentId.in_(idMap['studentId'].values()))
                .filter(answerFilter)
                .order_by(db.Answer.lectureId, db.Answer.studentId, db.Answer.timeEnd),
            sortCols=['lectureId', 'studentId', 'timeEnd'],
            ignoreCols=['answerId'],
            idMap=idMap,
            returnUpdates=True):
        if dbEntry:
            # Coins awarded might have been updated afer the fact
            dbEntry.coinsAwarded = dataEntry['coinsAwarded']
        else:
            Session.add(db.Answer(**dataEntry))
            inserts['answer'] += 1
    Session.flush()

    inserts['lecture_setting'] = 0
    for (dataEntry, dbEntry) in findMissingEntries(
            data['lecture_setting'],
            Session.query(db.LectureSetting)
                .filter(db.LectureSetting.lectureId.in_(idMap['lectureId'].values()))
                .filter(db.LectureSetting.studentId.in_(idMap['studentId'].values()))
                .order_by(db.LectureSetting.lectureId, db.LectureSetting.studentId, db.LectureSetting.key),
            sortCols=['lectureId', 'studentId', 'key'],
            idMap=idMap):
        Session.add(db.LectureSetting(**dataEntry))
        inserts['lecture_setting'] += 1
    Session.flush()

    inserts['coin_award'] = 0
    for (dataEntry, dbEntry) in findMissingEntries(
            data['coin_award'],
            Session.query(db.CoinAward)
                .filter(db.CoinAward.studentId.in_(idMap['studentId'].values()))
                .filter(coinAwardFilter)
                .order_by(db.CoinAward.studentId, db.CoinAward.awardTime),
            sortCols=['studentId', 'awardTime'],
            ignoreCols=['coinAwardId'],
            idMap=idMap):
        Session.add(db.CoinAward(**dataEntry))
        inserts['coin_award'] += 1
    Session.flush()

    inserts['ug_question'] = 0
    for (dataEntry, dbEntry) in findMissingEntries(
            data['ug_question'],
            Session.query(db.UserGeneratedQuestion)
                .filter(db.UserGeneratedQuestion.studentId.in_(idMap['studentId'].values()))
                .order_by(db.UserGeneratedQuestion.studentId, db.UserGeneratedQuestion.ugQuestionGuid),
            sortCols=['studentId', 'ugQuestionGuid'],
            ignoreCols=['ugQuestionId'],
            idMap=idMap):
        Session.add(db.UserGeneratedQuestion(**dataEntry))
        inserts['ug_question'] += 1
    Session.flush()

    inserts['ug_answer'] = 0
    for (dataEntry, dbEntry) in findMissingEntries(
            data['ug_answer'],
            Session.query(db.UserGeneratedAnswer)
                .filter(db.UserGeneratedAnswer.studentId.in_(idMap['studentId'].values()))
                .order_by(db.UserGeneratedAnswer.studentId, db.UserGeneratedAnswer.ugQuestionGuid),
            sortCols=['studentId', 'ugQuestionGuid'],
            ignoreCols=['ugAnswerId'],
            idMap=idMap):
        Session.add(db.UserGeneratedAnswer(**dataEntry))
        inserts['ug_answer'] += 1
    Session.flush()

    Session.flush()
    return inserts
