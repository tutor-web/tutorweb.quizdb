import calendar

from plone.app.testing import login

from ..sync.questions import syncPloneQuestions, getQuestionAllocation
from ..sync.answers import parseAnswerQueue

from .base import IntegrationTestCase, FunctionalTestCase
from .base import MANAGER_ID


class ReplicationDumpIngestViewTest(FunctionalTestCase):
    def submitAnswers(self, lecObj, student, rawAnswers):
        portal = self.layer['portal']
        login(portal, student.userName)

        allocs = lecObj.restrictedTraverse('@@quizdb-sync').asDict({})['questions']
        aq = []
        for a in rawAnswers:
            aq.append(dict(
                uri=allocs[a['alloc']]['uri'],
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
        ugLecObjs = [self.createTestLecture(qnCount=1, qnOpts=lambda i: dict(
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
        # student 0 writes a question in ugLec
        self.submitAnswers(ugLecObjs[0], students[0], [
            dict(alloc=0, quiz_time=1273010000, student_answer=dict(
                text=u"My question",
                explanation=u"I'm getting the hang of it",
                choices=[dict(answer="Good?", correct=True), dict(answer="Bad?", correct=False)],
            )),
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
            dict(hostId=1, lectureId=4, plonePath='/'.join(ugLecObjs[0].getPhysicalPath())),
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
            (1, 4, 1273010000),
        ])
        self.assertEqual(dump['lecture_setting'], [
            dict(studentId=1, lectureId=1, key=u'hist_sel', value=lecObjs[0].id.replace('lec-', '0.')),
            dict(studentId=1, lectureId=3, key=u'hist_sel', value=lecObjs[2].id.replace('lec-', '0.')),
            dict(studentId=2, lectureId=3, key=u'hist_sel', value=lecObjs[2].id.replace('lec-', '0.')),
        ])
        self.assertEqual(dump['ug_question'], [
        ])
