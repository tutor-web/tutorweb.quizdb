from plone.app.testing import login

from ..sync.questions import syncPloneQuestions, getQuestionAllocation
from ..sync.answers import parseAnswerQueue

from .base import IntegrationTestCase, FunctionalTestCase
from .base import MANAGER_ID


class ReplicationDumpIngestViewTest(FunctionalTestCase):
    def submitAnswers(self, lecDb, lecObj, student, rawAnswers):
        portal = self.layer['portal']
        answers = dict()
        allocs = getQuestionAllocation(lecDb, student, portal.absolute_url(), {})
        parseAnswerQueue(lecDb.lectureId, lecObj, student, [
            dict(
                uri=allocs[a['alloc']]['uri'],
                student_answer=0,
                quiz_time=a['quiz_time'],
                answer_time=a['quiz_time'] + 1,
                correct=True,
                synced=False,
            ) for a in rawAnswers
        ], {})

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
        lecObjs = [self.createTestLecture(qnCount=3) for _ in xrange(3)]
        lecDbs = [l.restrictedTraverse('@@quizdb-sync').getDbLecture() for l in lecObjs]
        for (i, l) in enumerate(lecObjs):
            syncPloneQuestions(lecDbs[i], l)

        # Create some students
        students = [self.createTestStudent('student%d' % i) for i in range(0,3)]

        # student 0 answers questions in lec 1 and 3
        self.submitAnswers(lecDbs[0], lecObjs[0], students[0], [
            dict(alloc=0, quiz_time=1271001000),
            dict(alloc=1, quiz_time=1271002000),
            dict(alloc=2, quiz_time=1272003000),
        ])
        self.submitAnswers(lecDbs[2], lecObjs[2], students[0], [
            dict(alloc=0, quiz_time=1271004000),
            dict(alloc=1, quiz_time=1271005000),
            dict(alloc=1, quiz_time=1272006000),
        ])
        self.submitAnswers(lecDbs[2], lecObjs[2], students[1], [
            dict(alloc=0, quiz_time=1271007000),
            dict(alloc=1, quiz_time=1271008000),
            dict(alloc=1, quiz_time=1272009000),
        ])

        dump = self.doDump({'from':'2000-05-01', 'to':'2099-05-08'})
        self.assertEqual(dump['date_from'], 957139200)
        self.assertEqual(dump['date_to'],  4081881600)
        self.assertEqual(dump['host'], [
            dict(hostId=1, hostKey=dump['host'][0]['hostKey'], fqdn=dump['host'][0]['fqdn']),
        ])
        self.assertEqual(dump['student'], [
            dict(studentId=1, hostId=1, userName=students[0].userName, eMail=students[0].eMail),
            dict(studentId=2, hostId=1, userName=students[1].userName, eMail=students[1].eMail),
        ])
        # We only get the lecture that we just answered, none of the default ones
        self.assertEqual(dump['lecture'], [
            dict(hostId=1, lectureId=1, plonePath=lecDbs[0].plonePath),
            dict(hostId=1, lectureId=3, plonePath=lecDbs[2].plonePath),
        ])
        self.assertEqual([(a['studentId'], a['lectureId'], a['timeStart']) for a in dump['answer']], [
            (1, 1, 1271001000),
            (1, 1, 1271002000),
            (1, 1, 1272003000),
            (1, 3, 1271004000),
            (1, 3, 1271005000),
            (1, 3, 1272006000),
            (2, 3, 1271007000),
            (2, 3, 1271008000),
            (2, 3, 1272009000),
        ])
