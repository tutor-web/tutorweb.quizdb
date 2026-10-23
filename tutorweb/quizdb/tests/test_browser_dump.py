import base64
import json
import transaction
from urllib import urlencode

from z3c.saconfig import Session

from plone.app.testing import login

from tutorweb.quizdb import db

from .base import FunctionalTestCase
from .base import PRODUCT_CONFIG, USER_A_ID, MANAGER_ID

PORTAL = u'http://nohost/plone/'
# The shared secret the instance is configured with, and the header it travels
# in. Spelled out rather than taken from TutorialDumpView.KEY_HEADER, being
# the wire contract build.sh has to match.
DUMP_KEY = PRODUCT_CONFIG['dump-key']
KEY_HEADER = 'X-Tutorweb-Dump-Key'


class TutorialDumpViewFunctional(FunctionalTestCase):
    maxDiff = None

    def setUp(self):
        super(TutorialDumpViewFunctional, self).setUp()
        # The inherited setUp publishes lec1/lec2, creating their lecture and
        # question rows, but doesn't commit. The first dump request would end
        # its transaction and take them with it, leaving a tutorial with no
        # lectures - so commit before dumping anything.
        transaction.commit()

    def dump(self, path='http://nohost/plone/dept1/tut1/@@quizdb-tutorial-dump', key=DUMP_KEY, **kwargs):
        kwargs.setdefault('user', MANAGER_ID)
        # The view streams its output, so the test browser needs to read it
        # out of stdout rather than the response body
        kwargs.setdefault('streaming', True)
        # key=None to send no shared secret at all, as opposed to a wrong one
        if key is not None:
            kwargs.setdefault('headers', {KEY_HEADER: key})
        return self.getJson(path, **kwargs)

    def lecKey(self, plonePath):
        """The dump key for a lecture: its database id, under the tutorial"""
        dbLec = (Session.query(db.Lecture)
            .filter(db.Lecture.plonePath == plonePath)
            .one())
        return u'tutorials/dept1/tut1/%d.json' % dbLec.lectureId

    def lecId(self, plonePath):
        return (Session.query(db.Lecture)
            .filter(db.Lecture.plonePath == plonePath)
            .one()).lectureId

    def qnKey(self, plonePath):
        """
        The dump key for a question: its database id, under the id of its
        home lecture (the one its plonePath lives in).
        """
        dbQn = (Session.query(db.Question)
            .filter(db.Question.plonePath == plonePath)
            .one())
        return u'questions/%d/%d.json' % (
            self.lecId(plonePath.rsplit('/', 1)[0]),
            dbQn.questionId,
        )

    def dumpWithBase(self, base):
        return self.dump(
            'http://nohost/plone/dept1/tut1/@@quizdb-tutorial-dump?' + urlencode(dict(
                base=base,
            )),
        )

    def test_anonymous(self):
        """
        The shared secret is the credential, not a Plone login: with the key
        and no login at all, build.sh gets its dump.
        """
        out = self.dump(user=None)
        self.assertTrue(u'tutorials/dept1/tut1.json' in out)

    def test_student(self):
        """...and a login makes no difference either way, given the key"""
        out = self.dump(user=USER_A_ID)
        self.assertTrue(u'tutorials/dept1/tut1.json' in out)

    def test_noKey(self):
        """Without the key nobody gets a dump, however they are logged in"""
        for user in (None, USER_A_ID, MANAGER_ID):
            out = self.dump(user=user, key=None, expectedStatus=403)
            self.assertEqual(out[u'error.json']['error'], u'Unauthorized')
            # Refused before any of it was written, so it's a 403 with
            # nothing else in it rather than an error.json under a 200
            self.assertEqual(list(out.keys()), [u'error.json'])

    def test_wrongKey(self):
        """A key that isn't the configured one is no better than none"""
        for key in ('', 'ut-dumpke', DUMP_KEY + 'x', DUMP_KEY.upper(), 'ut-rpcpass'):
            out = self.dump(key=key, expectedStatus=403)
            self.assertEqual(out[u'error.json']['error'], u'Unauthorized')
            self.assertEqual(list(out.keys()), [u'error.json'])

    def test_keyNotConfigured(self):
        """
        An instance that hasn't been given a dump-key refuses everybody,
        rather than letting everybody in - a request offering no key, or an
        empty one, included.
        """
        from ..config import dump_config

        original = dump_config.KEY
        try:
            for notConfigured in (None, ''):
                dump_config.KEY = notConfigured
                for key in (None, '', DUMP_KEY):
                    out = self.dump(key=key, expectedStatus=403)
                    self.assertEqual(out[u'error.json']['error'], u'Unauthorized')
        finally:
            dump_config.KEY = original

        # ...and the key still works once it's configured again
        self.assertTrue(u'tutorials/dept1/tut1.json' in self.dump())

    def test_flatFileNames(self):
        """
        One flat dict of {relative filename: content}: the tutorial, each
        lecture, and each question, keyed by portal-relative path + .json
        """
        out = self.dump()

        self.assertEqual(sorted(out.keys()), sorted([
            # Tutorial by path, lectures by id beneath it...
            u'tutorials/dept1/tut1.json',
            self.lecKey('/plone/dept1/tut1/lec1'),
            self.lecKey('/plone/dept1/tut1/lec2'),
        ] + [
            # ...questions by database id, under their home lecture's
            self.qnKey('/plone/dept1/tut1/lec1/qn1'),
            self.qnKey('/plone/dept1/tut1/lec1/qn2'),
            self.qnKey('/plone/dept1/tut1/lec2/qn1'),
            self.qnKey('/plone/dept1/tut1/lec2/qn2'),
        ]))

    def test_questionsStoredUnderHomeLecture(self):
        """
        A question's directory is its home lecture's id - the lecture holding
        the editable entry, i.e. the one its plonePath lives in.
        """
        out = self.dump()
        checked = 0

        for key in out.keys():
            parts = key.split('/')
            if len(parts) != 3 or parts[0] != u'questions':
                continue  # tutorial or lecture entry, not a question
            dbLec = Session.query(db.Lecture).get(int(parts[1]))
            dbQn = Session.query(db.Question).get(int(parts[2][:-len('.json')]))
            self.assertEqual(dbQn.plonePath.rsplit('/', 1)[0], dbLec.plonePath)
            checked += 1

        self.assertEqual(checked, 4)  # 2 questions in each of 2 lectures

    def test_questionIdRecoverableFromUri(self):
        """
        A server-side component has to get the questionId back out of an
        incoming URI, so the last segment is exactly that id.
        """
        out = self.dump()
        lec = out[self.lecKey('/plone/dept1/tut1/lec1')]
        self.assertTrue(len(lec['questions']) > 0)

        for qn in lec['questions']:
            segment = qn['uri'].rsplit('/', 1)[-1]
            self.assertTrue(segment.endswith(u'.json'), msg=qn['uri'])
            dbQn = Session.query(db.Question).get(int(segment[:-len('.json')]))
            self.assertTrue(dbQn is not None, msg=qn['uri'])
            self.assertEqual(
                dbQn.plonePath.rsplit('/', 2)[-2],
                'lec1',
                msg=dbQn.plonePath,
            )

    def test_tutorialEntry(self):
        """The tutorial names its lectures by URI, in order"""
        out = self.dump()
        tut = out[u'tutorials/dept1/tut1.json']

        self.assertEqual(tut['uri'], PORTAL + u'tutorials/dept1/tut1.json')
        self.assertEqual(tut['title'], u'Unittest D1 T1')
        self.assertEqual(tut['lectures'], [
            PORTAL + self.lecKey('/plone/dept1/tut1/lec1'),
            PORTAL + self.lecKey('/plone/dept1/tut1/lec2'),
        ])

    def test_lectureEntry(self):
        """Lectures carry quizdb-sync's student-independent fields"""
        out = self.dump()
        lec = out[self.lecKey('/plone/dept1/tut1/lec1')]

        self.assertEqual(sorted(lec.keys()), [
            u'next_uri',
            u'questions',
            u'review_uri',
            u'slide_uri',
            u'title',
            u'uri',
        ])
        self.assertEqual(lec['uri'], PORTAL + self.lecKey('/plone/dept1/tut1/lec1'))
        self.assertEqual(lec['title'], u'Unittest D1 T1 L1')
        self.assertEqual(lec['slide_uri'], PORTAL + u'dept1/tut1/lec1/slide-html')
        self.assertEqual(lec['review_uri'], PORTAL + u'dept1/tut1/lec1/quizdb-review-ugqn')

    def test_nothingPerStudent(self):
        """
        Nothing in the dump is specific to a student: the client supplies the
        settings, answer queue and user for whoever is using it.
        """
        out = self.dump()

        for content in out.values():
            for key in ('settings', 'answerQueue', 'user'):
                self.assertFalse(key in content, msg=key)

    def test_everyReferenceResolvesWithinTheDump(self):
        """
        The point of the exercise: every URI in the dump names an entry of the
        dump, so the bundle is self-contained.
        """
        out = self.dump()

        def key(uri):
            self.assertTrue(uri.startswith(PORTAL), msg=uri)
            return uri[len(PORTAL):]

        for filename, content in out.items():
            # Question bodies have no 'uri' of their own, matching
            # GetLectureQuestionsView - the client takes it from the key
            if 'uri' in content:
                self.assertEqual(key(content['uri']), filename)

            for uri in content.get('lectures', []):
                self.assertTrue(key(uri) in out, msg=uri)

            for qn in content.get('questions', []):
                self.assertTrue(key(qn['uri']) in out, msg=qn['uri'])

            if content.get('next_uri', None) is not None:
                self.assertTrue(key(content['next_uri']) in out, msg=content['next_uri'])

    def test_nextUriChainsWithinDump(self):
        """next_uri points at the next lecture in the dump, then None"""
        out = self.dump()
        uris = out[u'tutorials/dept1/tut1.json']['lectures']

        for i, uri in enumerate(uris):
            lec = out[uri[len(PORTAL):]]
            self.assertEqual(lec['next_uri'], uris[i + 1] if i + 1 < len(uris) else None)

    def test_noQuestionUri(self):
        """
        Lectures list their questions individually; there's no aggregate to
        point at, so no question_uri.
        """
        out = self.dump()

        for content in out.values():
            self.assertFalse('question_uri' in content)
        for key in out.keys():
            self.assertFalse('all-questions' in key)

    def test_questionEntries(self):
        """Bodies match GetLectureQuestionsView's output, answers obfuscated"""
        out = self.dump()
        lec = out[self.lecKey('/plone/dept1/tut1/lec1')]
        self.assertTrue(len(lec['questions']) > 0)

        for qn in lec['questions']:
            # The listed entry carries the allocation type and stats...
            self.assertEqual(qn['_type'], u'regular')
            self.assertEqual(qn['online_only'], False)
            self.assertTrue('chosen' in qn)
            self.assertTrue('correct' in qn)
            # ...the question's own entry carries the body, with the question
            # type in its own _type. Flattening is what keeps them apart.
            body = out[qn['uri'][len(PORTAL):]]
            self.assertEqual(body['_type'], u'multichoice')
            self.assertTrue('text' in body)
            self.assertTrue(len(body['choices']) > 0)
            answer = json.loads(base64.b64decode(body['answer']))
            self.assertTrue('correct' in answer)
            self.assertTrue('explanation' in answer)

    def test_base(self):
        """
        Every URI is base + the entry's own key, so the tutorials/ and
        questions/ segments appear exactly once.
        """
        APP = u'https://tutorweb-quiz-app/'
        out = self.dumpWithBase(APP)

        # Keys are unchanged by rebasing - they're filenames, not URIs
        self.assertTrue(self.lecKey('/plone/dept1/tut1/lec1') in out)
        self.assertTrue(self.qnKey('/plone/dept1/tut1/lec1/qn1') in out)

        self.assertEqual(
            out[u'tutorials/dept1/tut1.json']['uri'],
            APP + u'tutorials/dept1/tut1.json',
        )

        lec = out[self.lecKey('/plone/dept1/tut1/lec1')]
        self.assertEqual(lec['uri'], APP + self.lecKey('/plone/dept1/tut1/lec1'))
        self.assertEqual(lec['next_uri'], APP + self.lecKey('/plone/dept1/tut1/lec2'))
        self.assertEqual(
            lec['questions'][0]['uri'],
            APP + self.qnKey('/plone/dept1/tut1/lec1/qn1'),
        )

        # Slides/review are server-rendered, so they stay on this server
        self.assertEqual(lec['slide_uri'], PORTAL + u'dept1/tut1/lec1/slide-html')

    def test_baseSegmentsNotDoubled(self):
        """
        The key carries tutorials/ and questions/, so a base that happens to
        end in one of them doesn't repeat it.
        """
        out = self.dumpWithBase('https://app/')

        for key, content in out.items():
            if 'uri' not in content:
                continue
            self.assertEqual(content['uri'], u'https://app/' + key)
            self.assertEqual(content['uri'].count(u'/questions/questions/'), 0)
            self.assertEqual(content['uri'].count(u'/tutorials/tutorials/'), 0)

    def test_baseTrailingSlashOptional(self):
        """A base with or without a trailing slash gives the same output"""
        self.assertEqual(
            self.dumpWithBase('https://app/'),
            self.dumpWithBase('https://app'),
        )

    def test_noTemplateQuestions(self):
        """
        Template questions can't be dumped---they're generated per request out
        of other students' work---so they're left out entirely.
        """
        portal = self.layer['portal']
        login(portal, MANAGER_ID)
        lec1 = portal['dept1']['tut1']['lec1']
        lec1.invokeFactory(
            type_name="tw_questiontemplate",
            id="tmplqn0",
            title=u"Unittest lec1 tmplQ0",
        )
        # NB: tearDown only removes what's registered here; without this the
        # template leaks into every test that runs after this one
        self.tempObjects = getattr(self, 'tempObjects', [])
        self.tempObjects.append(lec1['tmplqn0'])
        self.objectPublish(lec1)
        transaction.commit()

        out = self.dump()
        # Keys are ids now, so look the template's own id up rather than
        # checking for its name in a filename (which would never match)
        tmplKey = self.qnKey('/plone/dept1/tut1/lec1/tmplqn0')
        self.assertFalse(tmplKey in out)
        for qn in out[self.lecKey('/plone/dept1/tut1/lec1')]['questions']:
            self.assertFalse(qn['uri'].endswith(tmplKey), msg=qn['uri'])

    def test_errorMidDumpReportedAsErrorJson(self):
        """
        A failure part way through can't change the status code, so it comes
        back as an 'error.json' entry for build.sh to look for - with the
        response still parseable, and what got dumped first still present.
        """
        from ..browser.dump import TutorialDumpView

        # Inherited from QuestionView, so shadow it and remove the shadow
        self.assertFalse('getQuestionData' in TutorialDumpView.__dict__)
        original = TutorialDumpView.getQuestionData
        seen = []

        def failAfterFirst(view, dbQn, dbLec):
            seen.append(dbQn)
            if len(seen) > 1:
                raise ValueError("ut-deliberate-failure")
            return original(view, dbQn, dbLec)

        TutorialDumpView.getQuestionData = failAfterFirst
        try:
            out = self.dump()
        finally:
            del TutorialDumpView.getQuestionData

        self.assertTrue(u'error.json' in out)
        self.assertEqual(out[u'error.json']['error'], u'ValueError')
        self.assertTrue('ut-deliberate-failure' in out[u'error.json']['message'])

        # The tutorial and the one question that worked are still there...
        self.assertTrue(u'tutorials/dept1/tut1.json' in out)
        self.assertTrue(self.qnKey('/plone/dept1/tut1/lec1/qn1') in out)
        # ...and the lecture that was interrupted is not, so build.sh can't
        # mistake this for a usable bundle even if it ignored error.json
        self.assertFalse(self.lecKey('/plone/dept1/tut1/lec1') in out)

    def test_noErrorJsonOnSuccess(self):
        """Nothing error-shaped in a clean dump"""
        out = self.dump()
        self.assertFalse(u'error.json' in out)

    def test_writesNothing(self):
        """
        Dumping allocates nothing and writes no settings rows, so it can be
        called repeatedly and by anyone without side effects.
        """
        def counts():
            return (
                Session.query(db.Allocation).count(),
                Session.query(db.LectureStudentSetting).count(),
                Session.query(db.Student).count(),
            )

        before = counts()
        first = self.dump()
        self.assertEqual(counts(), before)

        # ...and it's deterministic, unlike quizdb-sync
        second = self.dump()
        self.assertEqual(first, second)
        self.assertEqual(counts(), before)

    def test_skipsLectureWithNoDbRow(self):
        """A lecture with no DB row is skipped, not a 500 for the tutorial"""
        # NB: Provoked by moving the row out of the way rather than by leaving
        # a lecture unpublished - removePloneLecture() is disabled, so a row
        # outlives its lecture's publication state. This is what that function
        # used to do.
        lec1Key = self.lecKey('/plone/dept1/tut1/lec1')
        dbLec = (Session.query(db.Lecture)
            .filter(db.Lecture.plonePath == '/plone/dept1/tut1/lec2')
            .one())
        dbLec.plonePath = '/plone/dept1/tut1/lec2-moved-away'
        transaction.commit()

        out = self.dump()
        self.assertEqual(
            out[u'tutorials/dept1/tut1.json']['lectures'],
            [PORTAL + lec1Key],
        )
        self.assertEqual(
            [k for k in out.keys() if k.startswith(u'tutorials/dept1/tut1/')],
            [lec1Key],
        )
