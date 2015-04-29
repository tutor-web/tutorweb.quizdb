import datetime

from sqlalchemy.orm.exc import NoResultFound

def ingestDateRange(data):
    # Fetch range
    dateFrom = datetime.datetime.utcfromtimestamp(data['date_from'])
    dateTo = datetime.datetime.utcfromtimestamp(data['date_to'])

    # Check all host keys match our stored versions, and map to our IDs
    for (hostId, host) in data['host'].items():
        dbHost = Session.query(db.Host).filter(db.Host.fqdn == host['fqdn']).one()
        if dbHost.hostKey != host['hostKey']:
            raise ValueError("Mismatching host key for %s: %s vs %s" % (
                db.Host.fqdn,
                dbHost.hostKey,
                host['hostKey'],
            ))
        host['targetId'] = hostId

    # Map students to our IDs
    allStudentIds = []
    for (studentId, student) in data['student'].items():
        targetHostId = data['host'][student.hostId]['targetId']
        try:
            dbStudent = (Session.query(db.Student)
                .filter(db.Student.hostId == targetHostId)
                .filter(db.Student.userName == student['userName'])
                .one())
            dbStudent.userName = student['userName']
            dbStudent.email = student['eMail']
        except NoResultFound:
            dbStudent = db.Student(
                hostId=targetHostId,
                userName=student['userName'],
                eMail=student['eMail'],
            )
            Session.add(dbStudent)
            Session.flush()
        allStudentIds.append(dbStudent.studentId)
        student['targetId'] = dbStudent.studentId
    Session.flush()

    # Map lectures to our IDs
    allLectureIds = []
    for (lectureId, lecture) in data['lecture'].items():
        targetHostId = data['host'][lecture.hostId]['targetId']
        try:
            dbLecture = (Session.query(db.Lecture)
                .filter(db.Lecture.hostId == targetHostId)
                .filter(db.Lecture.plonePath == lecture['plonePath'])
                .one())
            dbLecture.plonePath = lecture['plonePath']
        except NoResultFound:
            dbLecture = db.Lecture(
                hostId=targetHostId,
                plonePath=lecture['plonePath'],
            )
            Session.add(dbLecture)
            Session.flush()
        allLectureIds.append(dbLecture.lectureId)
        lecture['targetId'] = dbLecture.lectureId
    Session.flush()

    # Answer (student/question/timeEnd should be unique)
    # TODO: Or we can link to host twice (once via student, once via lecture) and filter by that
    for dbAns in (Session.query(db.Answer)
            .filter(db.Answer.studentId.in_(allStudentIds))
            .filter(db.Answer.lectureId.in_(allLectureIds))
            .filter(db.Answer.timeEnd.between(dateFrom, dateTo))):
        for a in data['answer']:
            if lecture[a['lectureId']]['targetId'] == dbAns.lectureId and
                    student[a['studentId']]['targetId'] == dbAns.studentId and
                    a['timeEnd'] == dbAns.timeEnd:
                a['inDb'] = True
    for a in data['answer']:
        if a.get('inDb', False):
            continue
        Session.add(db.Answer(
            lectureId=lecture[a['lectureId']]['targetId'],
            studentId=student[a['studentId']]['targetId'],
            questionId=-1, # TODO: need map, question paths
            coinsAwarded=a['coinsAwarded'],
            grade=a['grade'],
            practice=a['practice'],
            timeStart=datetime.datetime.utcfromtimestamp(a['timeStart']),
            timeEnd=datetime.datetime.utcfromtimestamp(a['timeEnd']),
            chosenAnswer=a['chosenAnswer'],
            correct=a['correct'],
        ))

    # LectureSetting (lecture/student/key should be unique)

    # For coinAward, fetch existing rows, remove from dataset
    # Insert remaining

    # TODO: Crowdsourced questions and answers
