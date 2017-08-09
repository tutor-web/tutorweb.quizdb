import datetime
import calendar
import uuid

from plone.app.testing import login

from ..sync.questions import getQuestionAllocation
from ..sync.answers import parseAnswerQueue

from .base import IntegrationTestCase, FunctionalTestCase
from .base import MANAGER_ID


class ReplicationDumpIngestViewTest(FunctionalTestCase):
    maxDiff = None

    def submitAnswers(self, lecObj, student, rawAnswers):
        portal = self.layer['portal']
        login(portal, student.userName)

        allocs = lecObj.restrictedTraverse('@@quizdb-sync').asDict({})['questions']
        aq = []
        for a in rawAnswers:
            aq.append(dict(
                uri=allocs[a['alloc']]['uri'] + ('?question_id=%s' % a['ugquestion_guid'] if a.get('ugquestion_guid', None) else ''),
                student_answer=0,
                quiz_time=a['quiz_time'],
                answer_time=a['quiz_time'] + 1,
                correct=True,
                synced=False,
            ))
            aq[-1].update(a)

        lecObj.restrictedTraverse('@@quizdb-sync').asDict(dict(
            user=student.userName,
            answerQueue=aq,
        ))
        login(portal, MANAGER_ID)

    def fetchView(self, viewName, data, remoteAddr='127.0.0.1'):
        self.layer['request'].environ['REMOTE_ADDR'] = remoteAddr
        view = self.layer['portal'].unrestrictedTraverse('@@quizdb-replication-%s' % viewName)
        return view.asDict(data)

    def doDump(self, data={}, remoteAddr='127.0.0.1'):
        return self.fetchView('dump', data, remoteAddr)

    def doIngest(self, data, remoteAddr='127.0.0.1'):
        return self.fetchView('ingest', data, remoteAddr)

    def test_answers(self):
        portal = self.layer['portal']
        login(portal, MANAGER_ID)

        # Create test lectures and sync them
        lecObjs = [self.createTestLecture(qnCount=3, lecOpts=lambda i: dict(
            settings=[dict(key="hist_sel", value="0.%d" % i)],
        )) for _ in xrange(3)]
        ugLecObjs = [self.createTestLecture(qnCount=1, lecOpts=lambda i: dict(
            settings=[dict(key="cap_template_qn_reviews", value="3")],
        ), qnOpts=lambda i: dict(
            type_name="tw_questiontemplate",
        )) for _ in xrange(1)]

        # Create some students
        students = [self.createTestStudent('student%d' % i) for i in range(0,3)]

        # student 0 answers questions in lec 1 and 3
        self.submitAnswers(lecObjs[0], students[0], [
            dict(alloc=0, quiz_time=1271010000),
            dict(alloc=1, quiz_time=1271020000),
            dict(alloc=2, quiz_time=1272030000),
        ])
        self.submitAnswers(lecObjs[2], students[0], [
            dict(alloc=0, quiz_time=1271040000),
            dict(alloc=1, quiz_time=1271050000),
            dict(alloc=1, quiz_time=1272060000),
        ])
        self.submitAnswers(lecObjs[2], students[1], [
            dict(alloc=0, quiz_time=1271070000),
            dict(alloc=1, quiz_time=1271080000),
            dict(alloc=1, quiz_time=1272090000),
        ])

        # Fetch some of the data.
        dump = self.doDump(dict(answerId=5, maxVals=4))
        self.assertEqual(dump['state'], dict(answerId=9, coinAwardId=0))
        self.assertEqual(dump['student'], [
            dict(studentId=1, hostId=1, userName=students[0].userName, eMail=students[0].eMail),
            dict(studentId=2, hostId=1, userName=students[1].userName, eMail=students[1].eMail),
        ])
        self.assertEqual(dump['lecture'], [
            dict(hostId=1, currentVersion=1, lectureId=5, plonePath='/'.join(lecObjs[2].getPhysicalPath()), lastUpdate=dump['lecture'][0]['lastUpdate']),
        ])
        self.assertEqual([(a['studentId'], a['lectureId'], a['timeStart']) for a in dump['answer']], [
            (1, 5, 1271050000),
            (1, 5, 1272060000),
            (2, 5, 1271070000),
            (2, 5, 1271080000),
        ])

        # Fetch all of the data with an oversize range
        dump = self.doDump(dict(answerId=1))
        self.assertEqual(dump['state'], dict(answerId=10, coinAwardId=0))
        self.assertEqual(dump['host'], [
            dict(hostId=1, hostKey=dump['host'][0]['hostKey'], fqdn=dump['host'][0]['fqdn']),
        ])
        self.assertEqual(dump['student'], [
            dict(studentId=1, hostId=1, userName=students[0].userName, eMail=students[0].eMail),
            dict(studentId=2, hostId=1, userName=students[1].userName, eMail=students[1].eMail),
        ])
        # We only get the lecture that we just answered, none of the default ones
        self.assertEqual(dump['lecture'], [
            dict(hostId=1, lectureId=3, currentVersion=1, plonePath='/'.join(lecObjs[0].getPhysicalPath()), lastUpdate=dump['lecture'][0]['lastUpdate']),
            dict(hostId=1, lectureId=5, currentVersion=1, plonePath='/'.join(lecObjs[2].getPhysicalPath()), lastUpdate=dump['lecture'][1]['lastUpdate']),
        ])
        self.assertEqual([(a['studentId'], a['lectureId'], a['timeStart']) for a in dump['answer']], [
            (1, 3, 1271010000),
            (1, 3, 1271020000),
            (1, 3, 1272030000),
            (1, 5, 1271040000),
            (1, 5, 1271050000),
            (1, 5, 1272060000),
            (2, 5, 1271070000),
            (2, 5, 1271080000),
            (2, 5, 1272090000),
        ])
        self.assertEqual([x for x in dump['lecture_global_setting'] if x['key'] in [u'hist_sel']], [
            dict(lectureId=3, lectureVersion=1, key=u'hist_sel', value=unicode(lecObjs[0].id.replace('lec-', '0.')), min=None, max=None, shape=None, creationDate=dump['lecture_global_setting'][0]['creationDate']),
            dict(lectureId=5, lectureVersion=1, key=u'hist_sel', value=unicode(lecObjs[2].id.replace('lec-', '0.')), min=None, max=None, shape=None, creationDate=dump['lecture_global_setting'][-1]['creationDate']),
        ])
        # TODO: lecture_student_setting
        self.assertEqual(dump['ug_question'], [])
        self.assertEqual(dump['ug_answer'], [])
        self.assertEqual(dump['coin_award'], [])

        # student 2 writes a question in ugLec, appears in dump
        self.submitAnswers(ugLecObjs[0], students[2], [
            dict(alloc=0, quiz_time=1273010000, student_answer=dict(
                text=u"My question",
                explanation=u"I'm getting the hang of it",
                choices=[dict(answer="Good?", correct=True), dict(answer="Bad?", correct=False)],
            )),
        ])
        dump = self.doDump(dict())
        self.assertEqual(dump['state'], dict(answerId=11, coinAwardId=0))
        self.assertEqual(dump['student'], [
            dict(studentId=1, hostId=1, userName=students[0].userName, eMail=students[0].eMail),
            dict(studentId=2, hostId=1, userName=students[1].userName, eMail=students[1].eMail),
            dict(studentId=3, hostId=1, userName=students[2].userName, eMail=students[2].eMail),
        ])
        self.assertEqual([(a['studentId'], a['lectureId'], a['timeStart']) for a in dump['answer']], [
            (1, 3, 1271010000),
            (1, 3, 1271020000),
            (1, 3, 1272030000),
            (1, 5, 1271040000),
            (1, 5, 1271050000),
            (1, 5, 1272060000),
            (2, 5, 1271070000),
            (2, 5, 1271080000),
            (2, 5, 1272090000),
            (3, 6, 1273010000),
        ])
        self.assertEqual(dump['lecture'], [
            dict(hostId=1, lectureId=3, currentVersion=1, plonePath='/'.join(lecObjs[0].getPhysicalPath()), lastUpdate=dump['lecture'][0]['lastUpdate']),
            dict(hostId=1, lectureId=5, currentVersion=1, plonePath='/'.join(lecObjs[2].getPhysicalPath()), lastUpdate=dump['lecture'][1]['lastUpdate']),
            dict(hostId=1, lectureId=6, currentVersion=1, plonePath='/'.join(ugLecObjs[0].getPhysicalPath()), lastUpdate=dump['lecture'][2]['lastUpdate']),
        ])
        creationDates = {}
        for x in dump['lecture_global_setting']:
            creationDates[x['lectureId']] = x['creationDate']
        self.assertEqual([x for x in dump['lecture_global_setting'] if x['key'] in [u'hist_sel',u'cap_template_qn_reviews']], [
            dict(lectureId=3, lectureVersion=1, key=u'cap_template_qn_reviews', value=u'10', min=None, max=None, shape=None, creationDate=creationDates[3]),
            dict(lectureId=3, lectureVersion=1, key=u'hist_sel', value=unicode(lecObjs[0].id.replace('lec-', '0.')), min=None, max=None, shape=None, creationDate=creationDates[3]),
            dict(lectureId=5, lectureVersion=1, key=u'cap_template_qn_reviews', value=u'10', min=None, max=None, shape=None, creationDate=creationDates[5]),
            dict(lectureId=5, lectureVersion=1, key=u'hist_sel', value=unicode(lecObjs[2].id.replace('lec-', '0.')), min=None, max=None, shape=None, creationDate=creationDates[5]),
            dict(lectureId=6, lectureVersion=1, key=u'cap_template_qn_reviews', value=u'3', min=None, max=None, shape=None, creationDate=creationDates[6]),
            dict(lectureId=6, lectureVersion=1, key=u'hist_sel', value=u'0', min=None, max=None, shape=None, creationDate=creationDates[6]),
        ])
        # TODO: lecture_student_setting
        self.assertEqual([(q['ugQuestionId'], q['text']) for q in dump['ug_question']], [
            (1, "My question"),
        ])
        self.assertEqual(dump['ug_answer'], [])
        self.assertEqual(dump['coin_award'], [])

        # Student 0 reviews this question
        self.submitAnswers(ugLecObjs[0], students[0], [
            dict(
                alloc=0,
                ugquestion_guid=dump['ug_question'][0]['ugQuestionGuid'],
                question_type='usergenerated',
                quiz_time=1273020000,
                student_answer=dict(choice=0, rating=75, comments="Question, I'll say")
            ),
        ])
        dump = self.doDump()
        self.assertEqual(dump['state'], dict(answerId=12, coinAwardId=0))
        self.assertEqual(dump['student'], [
            dict(studentId=1, hostId=1, userName=students[0].userName, eMail=students[0].eMail),
            dict(studentId=2, hostId=1, userName=students[1].userName, eMail=students[1].eMail),
            dict(studentId=3, hostId=1, userName=students[2].userName, eMail=students[2].eMail),
        ])
        self.assertEqual([(a['studentId'], a['lectureId'], a['timeStart'], a['coinsAwarded']) for a in dump['answer']], [
            (1, 3, 1271010000, 0),
            (1, 3, 1271020000, 0),
            (1, 3, 1272030000, 0),
            (1, 5, 1271040000, 0),
            (1, 5, 1271050000, 0),
            (1, 5, 1272060000, 0),
            (2, 5, 1271070000, 0),
            (2, 5, 1271080000, 0),
            (2, 5, 1272090000, 0),
            (1, 6, 1273020000, 0),
            (3, 6, 1273010000, 0),
        ])
        self.assertEqual([(q['ugQuestionId'], q['text']) for q in dump['ug_question']], [
            (1, "My question"),
        ])
        self.assertEqual(dump['ug_answer'], [
            dict(ugAnswerId=1, studentId=1, ugQuestionGuid=dump['ug_question'][0]['ugQuestionGuid'], chosenAnswer=0, questionRating=75, comments=u"Question, I'll say", studentGrade=0),
        ])
        self.assertEqual(dump['coin_award'], [])

        # Rework dump, pretend it was from a different host
        dump['host'][0]['fqdn'] = u'beef.tutor-web.net'
        dump['host'][0]['hostKey'] = u'0123456789012345678900000000beef'
        ugQnMap = dict((id['ugQuestionGuid'], str(uuid.uuid4())) for id in dump['ug_question'])
        for a in dump['answer']:
            a['ugQuestionGuid'] = ugQnMap[a['ugQuestionGuid']] if a['ugQuestionGuid'] else None 
        for q in dump['ug_question']:
            q['ugQuestionGuid'] = ugQnMap[q['ugQuestionGuid']]
        for q in dump['ug_answer']:
            q['ugQuestionGuid'] = ugQnMap[q['ugQuestionGuid']]

        # First attempt, don't know what beef is
        with self.assertRaisesRegexp(ValueError, "beef.tutor-web.net"):
            ingest = self.doIngest(dump)

        # Add beef, get the key wrong, also noticed
        self.fetchView('updatehost', dict(
            fqdn=u'beef.tutor-web.net',
            hostKey=u'01234567890123456789000000000000',
        ))
        with self.assertRaisesRegexp(ValueError, u'0123456789012345678900000000beef'):
            ingest = self.doIngest(dump)

        # Finally, get it right.
        self.fetchView('updatehost', dict(
            fqdn=u'beef.tutor-web.net',
            hostKey=u'0123456789012345678900000000beef',
        ))
        self.assertEqual(self.doIngest(dump), dict(
            student=3,
            lecture=3,
            answer=11,
            lecture_global_setting=51,
            lecture_student_setting=0,  # TODO: Surely a few here?
            coin_award=0,
            ug_question=1,
            ug_answer=1,
        ))

        # All the data should be doubled-up now
        dumpPostIngest = self.doDump()
        self.assertEqual(dumpPostIngest['state'], dict(answerId=23, coinAwardId=0))
        self.assertEqual(dumpPostIngest['host'], [
            dict(hostId=1, hostKey=dumpPostIngest['host'][0]['hostKey'], fqdn=dumpPostIngest['host'][0]['fqdn']),
            dict(hostId=2, hostKey=u'0123456789012345678900000000beef', fqdn='beef.tutor-web.net'),
        ])
        self.assertEqual(dumpPostIngest['student'], [
            dict(studentId=1, hostId=1, userName=students[0].userName, eMail=students[0].eMail),
            dict(studentId=2, hostId=1, userName=students[1].userName, eMail=students[1].eMail),
            dict(studentId=3, hostId=1, userName=students[2].userName, eMail=students[2].eMail),
            dict(studentId=4, hostId=2, userName=students[0].userName, eMail=students[0].eMail),
            dict(studentId=5, hostId=2, userName=students[1].userName, eMail=students[1].eMail),
            dict(studentId=6, hostId=2, userName=students[2].userName, eMail=students[2].eMail),
        ])
        # There's no gap between new lectures, since we don't know about them
        self.assertEqual(dumpPostIngest['lecture'], [
            dict(hostId=1, lectureId=3, currentVersion=1, plonePath='/'.join(lecObjs[0].getPhysicalPath()), lastUpdate=dumpPostIngest['lecture'][0]['lastUpdate']),
            dict(hostId=1, lectureId=5, currentVersion=1, plonePath='/'.join(lecObjs[2].getPhysicalPath()), lastUpdate=dumpPostIngest['lecture'][1]['lastUpdate']),
            dict(hostId=1, lectureId=6, currentVersion=1, plonePath='/'.join(ugLecObjs[0].getPhysicalPath()), lastUpdate=dumpPostIngest['lecture'][2]['lastUpdate']),
            dict(hostId=2, lectureId=7, currentVersion=0, plonePath='/'.join(lecObjs[0].getPhysicalPath()), lastUpdate=dumpPostIngest['lecture'][3]['lastUpdate']),
            dict(hostId=2, lectureId=8, currentVersion=0, plonePath='/'.join(lecObjs[2].getPhysicalPath()), lastUpdate=dumpPostIngest['lecture'][4]['lastUpdate']),
            dict(hostId=2, lectureId=9, currentVersion=0, plonePath='/'.join(ugLecObjs[0].getPhysicalPath()), lastUpdate=dumpPostIngest['lecture'][5]['lastUpdate']),
        ])
        self.assertEqual([(a['studentId'], a['lectureId'], a['timeStart']) for a in dumpPostIngest['answer']], [
            (1, 3, 1271010000),
            (1, 3, 1271020000),
            (1, 3, 1272030000),
            (1, 5, 1271040000),
            (1, 5, 1271050000),
            (1, 5, 1272060000),
            (2, 5, 1271070000),
            (2, 5, 1271080000),
            (2, 5, 1272090000),
            (1, 6, 1273020000),
            (3, 6, 1273010000),
            (4, 7, 1271010000),
            (4, 7, 1271020000),
            (4, 7, 1272030000),
            (4, 8, 1271040000),
            (4, 8, 1271050000),
            (4, 8, 1272060000),
            (5, 8, 1271070000),
            (5, 8, 1271080000),
            (5, 8, 1272090000),
            (4, 9, 1273020000),
            (6, 9, 1273010000),
        ])

        creationDates = {}
        for x in dumpPostIngest['lecture_global_setting']:
            creationDates[x['lectureId']] = x['creationDate']
        self.assertEqual([x for x in dumpPostIngest['lecture_global_setting'] if x['key'] in [u'hist_sel',u'cap_template_qn_reviews']], [
            dict(lectureId=3, lectureVersion=1, key=u'cap_template_qn_reviews', value=u'10', min=None, max=None, shape=None, creationDate=creationDates[3]),
            dict(lectureId=3, lectureVersion=1, key=u'hist_sel', value=unicode(lecObjs[0].id.replace('lec-', '0.')), min=None, max=None, shape=None, creationDate=creationDates[3]),
            dict(lectureId=5, lectureVersion=1, key=u'cap_template_qn_reviews', value=u'10', min=None, max=None, shape=None, creationDate=creationDates[5]),
            dict(lectureId=5, lectureVersion=1, key=u'hist_sel', value=unicode(lecObjs[2].id.replace('lec-', '0.')), min=None, max=None, shape=None, creationDate=creationDates[5]),
            dict(lectureId=6, lectureVersion=1, key=u'cap_template_qn_reviews', value=u'3', min=None, max=None, shape=None, creationDate=creationDates[6]),
            dict(lectureId=6, lectureVersion=1, key=u'hist_sel', value=u'0', min=None, max=None, shape=None, creationDate=creationDates[6]),

            dict(lectureId=7, lectureVersion=1, key=u'cap_template_qn_reviews', value=u'10', min=None, max=None, shape=None, creationDate=creationDates[7]),
            dict(lectureId=7, lectureVersion=1, key=u'hist_sel', value=unicode(lecObjs[0].id.replace('lec-', '0.')), min=None, max=None, shape=None, creationDate=creationDates[7]),
            dict(lectureId=8, lectureVersion=1, key=u'cap_template_qn_reviews', value=u'10', min=None, max=None, shape=None, creationDate=creationDates[8]),
            dict(lectureId=8, lectureVersion=1, key=u'hist_sel', value=unicode(lecObjs[2].id.replace('lec-', '0.')), min=None, max=None, shape=None, creationDate=creationDates[8]),
            dict(lectureId=9, lectureVersion=1, key=u'cap_template_qn_reviews', value=u'3', min=None, max=None, shape=None, creationDate=creationDates[9]),
            dict(lectureId=9, lectureVersion=1, key=u'hist_sel', value=u'0', min=None, max=None, shape=None, creationDate=creationDates[9]),
        ])
        # TODO: lecture_student_setting
        self.assertEqual([(q['ugQuestionId'], q['text']) for q in dumpPostIngest['ug_question']], [
            (1, "My question"),
            (2, "My question"),
        ])
        self.assertEqual(dumpPostIngest['ug_answer'], [
            dict(ugAnswerId=1, studentId=1, ugQuestionGuid=ugQnMap.keys()[0], chosenAnswer=0, questionRating=75, comments=u"Question, I'll say", studentGrade=0),
            dict(ugAnswerId=2, studentId=4, ugQuestionGuid=ugQnMap.values()[0], chosenAnswer=0, questionRating=75, comments=u"Question, I'll say", studentGrade=0),
        ])
        self.assertEqual([(x['coinAwardId'], x['studentId'], x['amount']) for x in dumpPostIngest['coin_award']], [
        ])

        # Do it again, dump results are the same
        ingest = self.doIngest(dump)
        self.assertEqual(ingest, dict(
            student=0,
            lecture=0,
            answer=0,
            lecture_global_setting=0,
            lecture_student_setting=0,
            coin_award=0,
            ug_question=0,
            ug_answer=0,
        ))
        self.assertEqual(
            self.doDump(),
            dumpPostIngest,
        )

        # Student 1 reviews question, should give award
        self.submitAnswers(ugLecObjs[0], students[1], [
            dict(
                alloc=0,
                ugquestion_guid=dumpPostIngest['ug_question'][0]['ugQuestionGuid'],
                question_type='usergenerated',
                quiz_time=1273030000,
                student_answer=dict(choice=0, rating=75, comments="What can I say it's a question")
            ),
        ])
        dumpPostIngest = self.doDump()
        self.assertEqual(dumpPostIngest['state'], dict(answerId=24, coinAwardId=0))
        self.assertEqual([(a['studentId'], a['lectureId'], a['timeStart'], a['coinsAwarded']) for a in dumpPostIngest['answer']], [
            (1, 3, 1271010000, 0),
            (1, 3, 1271020000, 0),
            (1, 3, 1272030000, 0),
            (1, 5, 1271040000, 0),
            (1, 5, 1271050000, 0),
            (1, 5, 1272060000, 0),
            (2, 5, 1271070000, 0),
            (2, 5, 1271080000, 0),
            (2, 5, 1272090000, 0),
            (1, 6, 1273020000, 0),
            (2, 6, 1273030000, 0), # NB: We gave an answer here
            (3, 6, 1273010000, 10000),
            (4, 7, 1271010000, 0),
            (4, 7, 1271020000, 0),
            (4, 7, 1272030000, 0),
            (4, 8, 1271040000, 0),
            (4, 8, 1271050000, 0),
            (4, 8, 1272060000, 0),
            (5, 8, 1271070000, 0),
            (5, 8, 1271080000, 0),
            (5, 8, 1272090000, 0),
            (4, 9, 1273020000, 0),
            (6, 9, 1273010000, 0),
        ])
        self.assertEqual([(q['ugQuestionId'], q['text']) for q in dumpPostIngest['ug_question']], [
            (1, "My question"),
            (2, "My question"),
        ])
        self.assertEqual(dumpPostIngest['ug_answer'], [
            dict(ugAnswerId=1, studentId=1, ugQuestionGuid=dumpPostIngest['ug_question'][0]['ugQuestionGuid'], chosenAnswer=0, questionRating=75, comments=u"Question, I'll say", studentGrade=0),
            dict(ugAnswerId=3, studentId=2, ugQuestionGuid=dumpPostIngest['ug_question'][0]['ugQuestionGuid'], chosenAnswer=0, questionRating=75, comments=u"What can I say it's a question", studentGrade=0),
            dict(ugAnswerId=2, studentId=4, ugQuestionGuid=ugQnMap.values()[0], chosenAnswer=0, questionRating=75, comments=u"Question, I'll say", studentGrade=0),
        ])
        self.assertEqual(dumpPostIngest['coin_award'], [])

        # Award coins to student 2
        login(portal, students[2].userName)
        portal.unrestrictedTraverse('@@quizdb-student-award').asDict(dict(walletId='$$UNITTEST001'))
        login(portal, MANAGER_ID)
        dumpPostIngest = self.doDump()
        self.assertEqual(dumpPostIngest['state'], dict(answerId=24, coinAwardId=2))
        self.assertEqual([(x['coinAwardId'], x['studentId'], x['amount']) for x in dumpPostIngest['coin_award']], [
            (1, 3, 10000),
        ])

        # Add coins to other question by altering dump.
        dump['answer'][-1]['coinsAwarded'] = 99999
        self.assertEqual(self.doIngest(dump), dict(
            student=0,
            lecture=0,
            answer=0,
            lecture_global_setting=0,
            lecture_student_setting=0,
            coin_award=0,
            ug_question=0,
            ug_answer=0,
        ))
        dumpPostIngest = self.doDump()
        self.assertEqual(dumpPostIngest['state'], dict(answerId=24, coinAwardId=2))
        self.assertEqual([(a['studentId'], a['lectureId'], a['timeStart'], a['coinsAwarded']) for a in dumpPostIngest['answer']], [
            (1, 3, 1271010000, 0),
            (1, 3, 1271020000, 0),
            (1, 3, 1272030000, 0),
            (1, 5, 1271040000, 0),
            (1, 5, 1271050000, 0),
            (1, 5, 1272060000, 0),
            (2, 5, 1271070000, 0),
            (2, 5, 1271080000, 0),
            (2, 5, 1272090000, 0),
            (1, 6, 1273020000, 0),
            (2, 6, 1273030000, 0),
            (3, 6, 1273010000, 10000),
            (4, 7, 1271010000, 0),
            (4, 7, 1271020000, 0),
            (4, 7, 1272030000, 0),
            (4, 8, 1271040000, 0),
            (4, 8, 1271050000, 0),
            (4, 8, 1272060000, 0),
            (5, 8, 1271070000, 0),
            (5, 8, 1271080000, 0),
            (5, 8, 1272090000, 0),
            (4, 9, 1273020000, 0),
            (6, 9, 1273010000, 99999),
        ])

