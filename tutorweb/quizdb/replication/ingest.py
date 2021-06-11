import collections
import datetime
import uuid
import logging

from sqlalchemy.orm.exc import NoResultFound
from z3c.saconfig import Session

from tutorweb.quizdb import db

from App.config import getConfiguration
if getConfiguration().debug_mode:
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
                # NB: We don't worry about missing values for ug_question cases,
                # when students are reviewing the questions the source student
                # won't be in the map. However, the question will be already inserted
                # so won't cause a problem.
                return (k, idMap[k].get(v, None))
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
            dbHost = Session.query(db.Host).filter_by(
                hostKey=host['hostKey'],
                fqdn=host['fqdn'],
            ).one()
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

    if 'lecture_global_setting' in data:
        inserts['lecture_global_setting'] = 0
        for (dataEntry, dbEntry) in findMissingEntries(
                data['lecture_global_setting'],
                Session.query(db.LectureGlobalSetting)
                    .filter(db.LectureGlobalSetting.lectureId.in_(idMap['lectureId'].values()))
                    .order_by(
                        db.LectureGlobalSetting.lectureId,
                        db.LectureGlobalSetting.lectureVersion,
                        db.LectureGlobalSetting.key,
                    ),
                sortCols=['lectureId', 'lectureVersion', 'key'],
                idMap=idMap):
            dataEntry['creationDate'] = datetime.datetime.utcfromtimestamp(dataEntry['creationDate'])
            Session.add(db.LectureGlobalSetting(**dataEntry))
            inserts['lecture_global_setting'] += 1
        Session.flush()

    if 'lecture_student_setting' in data:
        inserts['lecture_student_setting'] = 0
        for (dataEntry, dbEntry) in findMissingEntries(
                data['lecture_student_setting'],
                Session.query(db.LectureStudentSetting)
                    .filter(db.LectureStudentSetting.lectureId.in_(idMap['lectureId'].values()))
                    .filter(db.LectureStudentSetting.studentId.in_(idMap['studentId'].values()))
                    .order_by(
                        db.LectureStudentSetting.lectureId,
                        db.LectureStudentSetting.lectureVersion,
                        db.LectureStudentSetting.studentId,
                        db.LectureStudentSetting.key,
                    ),
                sortCols=['lectureId', 'lectureVersion', 'studentId', 'key'],
                idMap=idMap):
            dataEntry['creationDate'] = datetime.datetime.utcfromtimestamp(dataEntry['creationDate'])
            Session.add(db.LectureStudentSetting(**dataEntry))
            inserts['lecture_student_setting'] += 1
        Session.flush()

    inserts['ug_question'] = 0
    for (dataEntry, dbEntry) in findMissingEntries(
            data['ug_question'],
            Session.query(db.UserGeneratedQuestion)
                .order_by(db.UserGeneratedQuestion.ugQuestionGuid),
            sortCols=['ugQuestionGuid'],
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
        if dataEntry['studentId'] is not None:
            Session.add(db.UserGeneratedAnswer(**dataEntry))
            inserts['ug_answer'] += 1
        else:
            # If studentId is None, we've selected it but not relevant to current data
            # (the dump isn't selective enough). Ignore it, will import eventually
            continue
    Session.flush()

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

    if 'lecture_setting' in data:
        inserts['lecture_setting'] = 0
        for (dataEntry, dbEntry) in findMissingEntries(
                data['lecture_setting'],
                Session.query(db.DeprecatedLectureSetting)
                    .filter(db.DeprecatedLectureSetting.lectureId.in_(idMap['lectureId'].values()))
                    .filter(db.DeprecatedLectureSetting.studentId.in_(idMap['studentId'].values()))
                    .order_by(db.DeprecatedLectureSetting.lectureId, db.DeprecatedLectureSetting.studentId, db.DeprecatedLectureSetting.key),
                sortCols=['lectureId', 'studentId', 'key'],
                idMap=idMap):
            Session.add(db.DeprecatedLectureSetting(**dataEntry))
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

    Session.flush()
    return inserts
