import calendar
import uuid

from plone.app.testing import login

from ..sync.questions import syncPloneQuestions, getQuestionAllocation
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

    def doDump(self, data, remoteAddr='127.0.0.1'):
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
        for l in lecObjs + ugLecObjs:
            syncPloneQuestions(l.restrictedTraverse('@@quizdb-sync').getDbLecture(), l)

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

        # Fetch some of the data. NB: We round up to the nearest day
        dump = self.doDump({'from':'2010-04-11', 'to':'2010-04-11'})
        self.assertEqual(dump['date_from'], calendar.timegm((2010, 4, 11, 0, 0, 0)))
        self.assertEqual(dump['date_to'],  calendar.timegm((2010, 4, 12, 0, 0, 0)))
        self.assertEqual(dump['student'], [
            dict(studentId=1, hostId=1, userName=students[0].userName, eMail=students[0].eMail),
        ])
        self.assertEqual(dump['lecture'], [
            dict(hostId=1, lectureId=1, plonePath='/'.join(lecObjs[0].getPhysicalPath())),
        ])
        self.assertEqual([(a['studentId'], a['lectureId'], a['timeStart']) for a in dump['answer']], [
            (1, 1, 1271010000),
            (1, 1, 1271020000),
        ])

        dump = self.doDump({'from':'2010-04-12', 'to':'2010-04-12'})
        self.assertEqual(dump['date_from'], calendar.timegm((2010, 4, 12, 0, 0, 0)))
        self.assertEqual(dump['date_to'],  calendar.timegm((2010, 4, 13, 0, 0, 0)))
        self.assertEqual(dump['student'], [
            dict(studentId=1, hostId=1, userName=students[0].userName, eMail=students[0].eMail),
            dict(studentId=2, hostId=1, userName=students[1].userName, eMail=students[1].eMail),
        ])
        self.assertEqual(dump['lecture'], [
            dict(hostId=1, lectureId=3, plonePath='/'.join(lecObjs[2].getPhysicalPath())),
        ])
        self.assertEqual([(a['studentId'], a['lectureId'], a['timeStart']) for a in dump['answer']], [
            (1, 3, 1271040000),
            (1, 3, 1271050000),
            (2, 3, 1271070000),
            (2, 3, 1271080000),
        ])

        # Fetch all of the data with an oversize date range
        dump = self.doDump({'from':'2000-05-01', 'to':'2099-05-08'})
        self.assertEqual(dump['date_from'], calendar.timegm((2000, 5, 1, 0, 0, 0)))
        self.assertEqual(dump['date_to'],  calendar.timegm((2099, 5, 9, 0, 0, 0)))
        self.assertEqual(dump['host'], [
            dict(hostId=1, hostKey=dump['host'][0]['hostKey'], fqdn=dump['host'][0]['fqdn']),
        ])
        self.assertEqual(dump['student'], [
            dict(studentId=1, hostId=1, userName=students[0].userName, eMail=students[0].eMail),
            dict(studentId=2, hostId=1, userName=students[1].userName, eMail=students[1].eMail),
        ])
        # We only get the lecture that we just answered, none of the default ones
        self.assertEqual(dump['lecture'], [
            dict(hostId=1, lectureId=1, plonePath='/'.join(lecObjs[0].getPhysicalPath())),
            dict(hostId=1, lectureId=3, plonePath='/'.join(lecObjs[2].getPhysicalPath())),
        ])
        self.assertEqual([(a['studentId'], a['lectureId'], a['timeStart']) for a in dump['answer']], [
            (1, 1, 1271010000),
            (1, 1, 1271020000),
            (1, 1, 1272030000),
            (1, 3, 1271040000),
            (1, 3, 1271050000),
            (1, 3, 1272060000),
            (2, 3, 1271070000),
            (2, 3, 1271080000),
            (2, 3, 1272090000),
        ])
        self.assertEqual([x for x in dump['lecture_setting'] if x['key'] in [u'hist_sel']], [
            dict(studentId=1, lectureId=1, key=u'hist_sel', value=lecObjs[0].id.replace('lec-', '0.')),
            dict(studentId=1, lectureId=3, key=u'hist_sel', value=lecObjs[2].id.replace('lec-', '0.')),
            dict(studentId=2, lectureId=3, key=u'hist_sel', value=lecObjs[2].id.replace('lec-', '0.')),
        ])
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
        dump = self.doDump({'from':'2000-05-01', 'to':'2099-05-08'})
        self.assertEqual(dump['student'], [
            dict(studentId=1, hostId=1, userName=students[0].userName, eMail=students[0].eMail),
            dict(studentId=2, hostId=1, userName=students[1].userName, eMail=students[1].eMail),
            dict(studentId=3, hostId=1, userName=students[2].userName, eMail=students[2].eMail),
        ])
        self.assertEqual([(a['studentId'], a['lectureId'], a['timeStart']) for a in dump['answer']], [
            (1, 1, 1271010000),
            (1, 1, 1271020000),
            (1, 1, 1272030000),
            (1, 3, 1271040000),
            (1, 3, 1271050000),
            (1, 3, 1272060000),
            (2, 3, 1271070000),
            (2, 3, 1271080000),
            (2, 3, 1272090000),
            (3, 4, 1273010000),
        ])
        self.assertEqual(dump['lecture'], [
            dict(hostId=1, lectureId=1, plonePath='/'.join(lecObjs[0].getPhysicalPath())),
            dict(hostId=1, lectureId=3, plonePath='/'.join(lecObjs[2].getPhysicalPath())),
            dict(hostId=1, lectureId=4, plonePath='/'.join(ugLecObjs[0].getPhysicalPath())),
        ])
        self.assertEqual([x for x in dump['lecture_setting'] if x['key'] in [u'hist_sel',u'cap_template_qn_reviews']], [
            dict(studentId=1, lectureId=1, key=u'cap_template_qn_reviews', value=u'10'),
            dict(studentId=1, lectureId=1, key=u'hist_sel', value=lecObjs[0].id.replace('lec-', '0.')),
            dict(studentId=1, lectureId=3, key=u'cap_template_qn_reviews', value=u'10'),
            dict(studentId=1, lectureId=3, key=u'hist_sel', value=lecObjs[2].id.replace('lec-', '0.')),
            dict(studentId=2, lectureId=3, key=u'cap_template_qn_reviews', value=u'10'),
            dict(studentId=2, lectureId=3, key=u'hist_sel', value=lecObjs[2].id.replace('lec-', '0.')),
            dict(studentId=3, lectureId=4, key=u'cap_template_qn_reviews', value=u'3'),
            dict(studentId=3, lectureId=4, key=u'hist_sel', value=u'0'),
        ])
        self.assertEqual([(q['ugQuestionId'], q['text']) for q in dump['ug_question']], [
            (1, "My question"),
        ])
        self.assertEqual(dump['ug_answer'], [])
        self.assertEqual(dump['coin_award'], [])

        # Student 0 & 1 review this question, gets an award
        self.submitAnswers(ugLecObjs[0], students[0], [
            dict(
                alloc=0,
                ugquestion_guid=dump['ug_question'][0]['ugQuestionGuid'],
                question_type='usergenerated',
                quiz_time=1273020000,
                student_answer=dict(choice=0, rating=75, comments="Question, I'll say")
            ),
        ])
        self.submitAnswers(ugLecObjs[0], students[1], [
            dict(
                alloc=0,
                ugquestion_guid=dump['ug_question'][0]['ugQuestionGuid'],
                question_type='usergenerated',
                quiz_time=1273030000,
                student_answer=dict(choice=0, rating=75, comments="What can I say it's a question")
            ),
        ])
        dump = self.doDump({'from':'2000-05-01', 'to':'2099-05-08'})
        self.assertEqual(dump['student'], [
            dict(studentId=1, hostId=1, userName=students[0].userName, eMail=students[0].eMail),
            dict(studentId=2, hostId=1, userName=students[1].userName, eMail=students[1].eMail),
            dict(studentId=3, hostId=1, userName=students[2].userName, eMail=students[2].eMail),
        ])
        self.assertEqual([(a['studentId'], a['lectureId'], a['timeStart'], a['coinsAwarded']) for a in dump['answer']], [
            (1, 1, 1271010000, 0),
            (1, 1, 1271020000, 0),
            (1, 1, 1272030000, 0),
            (1, 3, 1271040000, 0),
            (1, 3, 1271050000, 0),
            (1, 3, 1272060000, 0),
            (2, 3, 1271070000, 0),
            (2, 3, 1271080000, 0),
            (2, 3, 1272090000, 0),
            (1, 4, 1273020000, 0),
            (2, 4, 1273030000, 0),
            (3, 4, 1273010000, 10000),
        ])
        self.assertEqual([(q['ugQuestionId'], q['text']) for q in dump['ug_question']], [
            (1, "My question"),
        ])
        self.assertEqual(dump['ug_answer'], [
            dict(ugAnswerId=1, studentId=1, ugQuestionGuid=dump['ug_question'][0]['ugQuestionGuid'], chosenAnswer=0, questionRating=75, comments=u"Question, I'll say", studentGrade=0),
            dict(ugAnswerId=2, studentId=2, ugQuestionGuid=dump['ug_question'][0]['ugQuestionGuid'], chosenAnswer=0, questionRating=75, comments=u"What can I say it's a question", studentGrade=0),
        ])
        self.assertEqual(dump['coin_award'], [])

        # Award coins to student 2
        login(portal, students[2].userName)
        portal.unrestrictedTraverse('@@quizdb-student-award').asDict(dict(walletId='$$UNITTEST001'))
        login(portal, MANAGER_ID)
        dump = self.doDump({'from':'2000-05-01', 'to':'2099-05-08'})
        self.assertEqual([(x['coinAwardId'], x['studentId'], x['amount']) for x in dump['coin_award']], [
            (1, 3, 10000),
        ])

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
        with self.assertRaisesRegexp(ValueError, "Unknown host beef.tutor-web.net"):
            ingest = self.doIngest(dump)

        # Add beef, get the key wrong, also noticed
        self.fetchView('updatehost', dict(
            fqdn=u'beef.tutor-web.net',
            hostKey=u'01234567890123456789000000000000',
        ))
        with self.assertRaisesRegexp(ValueError, u'01234567890123456789000000000000'):
            ingest = self.doIngest(dump)

        # Finally, get it right.
        self.fetchView('updatehost', dict(
            fqdn=u'beef.tutor-web.net',
            hostKey=u'0123456789012345678900000000beef',
        ))
        self.assertEqual(self.doIngest(dump), dict(
            student=3,
            lecture=3,
            answer=12,
            lecture_setting=102,
            coin_award=1,
            ug_question=1,
            ug_answer=2,
        ))

        # All the data should be doubled-up now
        dumpPostIngest = self.doDump({'from':'2000-05-01', 'to':'2099-05-08'})
        self.assertEqual(dumpPostIngest['date_from'], calendar.timegm((2000, 5, 1, 0, 0, 0)))
        self.assertEqual(dumpPostIngest['date_to'],  calendar.timegm((2099, 5, 9, 0, 0, 0)))
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
            dict(hostId=1, lectureId=1, plonePath='/'.join(lecObjs[0].getPhysicalPath())),
            dict(hostId=1, lectureId=3, plonePath='/'.join(lecObjs[2].getPhysicalPath())),
            dict(hostId=1, lectureId=4, plonePath='/'.join(ugLecObjs[0].getPhysicalPath())),
            dict(hostId=2, lectureId=5, plonePath='/'.join(lecObjs[0].getPhysicalPath())),
            dict(hostId=2, lectureId=6, plonePath='/'.join(lecObjs[2].getPhysicalPath())),
            dict(hostId=2, lectureId=7, plonePath='/'.join(ugLecObjs[0].getPhysicalPath())),
        ])
        self.assertEqual([(a['studentId'], a['lectureId'], a['timeStart']) for a in dumpPostIngest['answer']], [
            (1, 1, 1271010000),
            (1, 1, 1271020000),
            (1, 1, 1272030000),
            (1, 3, 1271040000),
            (1, 3, 1271050000),
            (1, 3, 1272060000),
            (2, 3, 1271070000),
            (2, 3, 1271080000),
            (2, 3, 1272090000),
            (1, 4, 1273020000),
            (2, 4, 1273030000),
            (3, 4, 1273010000),
            (4, 5, 1271010000),
            (4, 5, 1271020000),
            (4, 5, 1272030000),
            (4, 6, 1271040000),
            (4, 6, 1271050000),
            (4, 6, 1272060000),
            (5, 6, 1271070000),
            (5, 6, 1271080000),
            (5, 6, 1272090000),
            (4, 7, 1273020000),
            (5, 7, 1273030000),
            (6, 7, 1273010000),
        ])
        self.assertEqual([x for x in dumpPostIngest['lecture_setting'] if x['key'] in [u'hist_sel',u'cap_template_qn_reviews']], [
            dict(studentId=1, lectureId=1, key=u'cap_template_qn_reviews', value=u'10'),
            dict(studentId=1, lectureId=1, key=u'hist_sel', value=lecObjs[0].id.replace('lec-', '0.')),
            dict(studentId=1, lectureId=3, key=u'cap_template_qn_reviews', value=u'10'),
            dict(studentId=1, lectureId=3, key=u'hist_sel', value=lecObjs[2].id.replace('lec-', '0.')),
            dict(studentId=2, lectureId=3, key=u'cap_template_qn_reviews', value=u'10'),
            dict(studentId=2, lectureId=3, key=u'hist_sel', value=lecObjs[2].id.replace('lec-', '0.')),
            dict(studentId=1, lectureId=4, key=u'cap_template_qn_reviews', value=u'3'),
            dict(studentId=1, lectureId=4, key=u'hist_sel', value=u'0'),
            dict(studentId=2, lectureId=4, key=u'cap_template_qn_reviews', value=u'3'),
            dict(studentId=2, lectureId=4, key=u'hist_sel', value=u'0'),
            dict(studentId=3, lectureId=4, key=u'cap_template_qn_reviews', value=u'3'),
            dict(studentId=3, lectureId=4, key=u'hist_sel', value=u'0'),

            dict(studentId=4, lectureId=5, key=u'cap_template_qn_reviews', value=u'10'),
            dict(studentId=4, lectureId=5, key=u'hist_sel', value=lecObjs[0].id.replace('lec-', '0.')),
            dict(studentId=4, lectureId=6, key=u'cap_template_qn_reviews', value=u'10'),
            dict(studentId=4, lectureId=6, key=u'hist_sel', value=lecObjs[2].id.replace('lec-', '0.')),
            dict(studentId=5, lectureId=6, key=u'cap_template_qn_reviews', value=u'10'),
            dict(studentId=5, lectureId=6, key=u'hist_sel', value=lecObjs[2].id.replace('lec-', '0.')),
            dict(studentId=4, lectureId=7, key=u'cap_template_qn_reviews', value=u'3'),
            dict(studentId=4, lectureId=7, key=u'hist_sel', value=u'0'),
            dict(studentId=5, lectureId=7, key=u'cap_template_qn_reviews', value=u'3'),
            dict(studentId=5, lectureId=7, key=u'hist_sel', value=u'0'),
            dict(studentId=6, lectureId=7, key=u'cap_template_qn_reviews', value=u'3'),
            dict(studentId=6, lectureId=7, key=u'hist_sel', value=u'0'),
        ])
        self.assertEqual([(q['ugQuestionId'], q['text']) for q in dumpPostIngest['ug_question']], [
            (1, "My question"),
            (2, "My question"),
        ])
        self.assertEqual(dumpPostIngest['ug_answer'], [
            dict(ugAnswerId=1, studentId=1, ugQuestionGuid=ugQnMap.keys()[0], chosenAnswer=0, questionRating=75, comments=u"Question, I'll say", studentGrade=0),
            dict(ugAnswerId=2, studentId=2, ugQuestionGuid=ugQnMap.keys()[0], chosenAnswer=0, questionRating=75, comments=u"What can I say it's a question", studentGrade=0),
            dict(ugAnswerId=3, studentId=4, ugQuestionGuid=ugQnMap.values()[0], chosenAnswer=0, questionRating=75, comments=u"Question, I'll say", studentGrade=0),
            dict(ugAnswerId=4, studentId=5, ugQuestionGuid=ugQnMap.values()[0], chosenAnswer=0, questionRating=75, comments=u"What can I say it's a question", studentGrade=0),
        ])
        self.assertEqual([(x['coinAwardId'], x['studentId'], x['amount']) for x in dumpPostIngest['coin_award']], [
            (1, 3, 10000),
            (2, 6, 10000),
        ])

        # Do it again, dump results are the same
        ingest = self.doIngest(dump)
        self.assertEqual(ingest, dict(
            student=0,
            lecture=0,
            answer=0,
            lecture_setting=0,
            coin_award=0,
            ug_question=0,
            ug_answer=0,
        ))
        self.assertEqual(
            self.doDump({'from':'2000-05-01', 'to':'2099-05-08'}),
            dumpPostIngest,
        )
