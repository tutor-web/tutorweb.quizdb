import hmac
import logging
import re

from AccessControl import Unauthorized
from z3c.saconfig import Session
from zope.publisher.interfaces import NotFound

from tutorweb.quizdb import db

from .base import StreamingJSONBrowserView
from .question import QuestionView

from ..config import dump_config
from ..utils import getDbLecture

logger = logging.getLogger(__package__)


def _asBytes(s):
    """
    s as bytes, for hmac.compare_digest, which won't mix the two.

    zope.conf and request headers both give us str, but encode anything that
    did arrive as unicode rather than letting str.encode() try to decode
    non-ASCII bytes as ASCII first and raise.
    """
    if isinstance(s, unicode):
        return s.encode('utf-8')
    return s


class TutorialDumpView(StreamingJSONBrowserView, QuestionView):
    """
    Dump a tutorial and all its questions, for bundling into an app as seed
    content.

    Output is a flat {filename: content} manifest, for ./bin/build.sh to
    write out verbatim:

      tutorials/dept1/tut1.json    the tutorial: title and its lecture URIs
      tutorials/dept1/tut1/12.json a lecture, in @@quizdb-sync's shape
      questions/12/1234.json       a question, as @@quizdb-all-questions
                                   renders it

    Lectures are keyed by db.Lecture.lectureId beneath their tutorial,
    questions by db.Question.questionId beneath their *home* lecture - the
    one their plonePath lives in, as opposed to any they are aliased into
    (see sync.plone.syncPloneQuestions). An aliased question is listed by
    every lecture holding it, but stored once. Ids are in the keys so a
    server-side component can recover them from an incoming URI's last
    segment. The tutorial is keyed by path, having no table to take an id
    from.

    Every URI in the content is 'base' + that entry's own key, 'base' being
    the root the app serves the bundle from, taken from the querystring or
    JSON body and defaulting to this portal's URL.

    Takes no student and writes nothing, and the output says nothing about
    one either: no 'settings' (there's nobody to choose the randomised ones
    for, and one draw baked in would be the same "random" choice on every
    device), no 'answerQueue', and no 'user' - the last being what stops
    syncLecture() rejecting a seeded lecture as somebody else's. The client
    supplies all three for whoever is using it.

    NB: Authenticated by the KEY_HEADER shared secret rather than by a
    Plone login - see requireDumpKey().

    NB: 'slide_uri'/'review_uri' are the only URIs naming something that
    isn't an entry here - server-rendered HTML that isn't bundled, so they
    stay pointed at this server. Everything else resolves within the dump.

    NB: Output is streamed a member at a time, question bodies being large
    (images and attachments are inlined as base64 data URIs). It is one
    request per tutorial so a dump can't straddle an edit. A failure mid-dump
    cannot change the status code, so it appears as an 'error.json' entry
    under a 200 - build.sh must check for it.
    """

    # Every key is under one of these, so none can collide with the bare
    # 'error.json' StreamingJSONBrowserView reports failures under.
    TUTORIAL_DIR = 'tutorials'
    QUESTION_DIR = 'questions'

    def requireDumpKey(self):
        """
        Require 'X-Tutorweb-Dump-Key' to match zope.conf's dump-key, or refuse.

        Not Plone's authentication: there is no student involved here, this
        endpoint needs to be accesible from a CI job, see
        https://github.com/tutor-web/tutorweb.app
        """
        expected = _asBytes(dump_config.KEY or '')
        got = _asBytes(self.request.getHeader('X-Tutorweb-Dump-Key') or '')

        # Constant-time, so a wrong key can't be narrowed down a character at
        # a time by watching how long the comparison takes
        if not expected or not hmac.compare_digest(expected, got):
            raise Unauthorized('Missing or invalid X-Tutorweb-Dump-Key header')

    def _normaliseBase(self, base):
        """A base we can concatenate a key onto"""
        return base.rstrip('/') + '/'

    def _relativePath(self, plonePath):
        """Portal-relative path"""
        # As utils.getDbLecture(): some stored paths have a doubled portal id
        # from an old upgrade bug, which would otherwise strip to a
        # plausible-looking but wrong relative path
        plonePath = re.sub('/tutor-web/tutor-web/', '/tutor-web/', plonePath)

        portalPath = '/'.join(self.portalObject().getPhysicalPath())
        if not plonePath.startswith(portalPath + '/'):
            # Better than a key that looks right and isn't
            raise ValueError("%s is not within %s" % (plonePath, portalPath))
        return plonePath[len(portalPath) + 1:]

    def _fileName(self, plonePath):
        """The tutorial's key: its relative path"""
        return '%s/%s.json' % (self.TUTORIAL_DIR, self._relativePath(plonePath))

    def _lectureFileName(self, dbLec):
        """
        A lecture's key: its database id, under the tutorial being dumped.

        NB: self.context, not the lecture's own path, so an alias lecture
        living elsewhere still files under this tutorial.
        """
        return '%s/%s/%d.json' % (
            self.TUTORIAL_DIR,
            self._relativePath('/'.join(self.context.getPhysicalPath())),
            dbLec.lectureId,
        )

    def _homeLecture(self, dbQn):
        """
        The lecture holding a question's editable entry: the one its
        plonePath lives in, which is how syncPloneQuestions tells a real
        entry from an alias.

        Raises ValueError (as getDbLecture does) when that lecture has no
        row, e.g. a question still aliased into a live lecture after its home
        was removed.
        """
        plonePath = dbQn.plonePath.rsplit('/', 1)[0]
        if plonePath not in self._homeLectures:
            # Cached: a lecture's worth of questions share a home
            self._homeLectures[plonePath] = getDbLecture(plonePath)
        return self._homeLectures[plonePath]

    def _questionFileName(self, dbQn):
        """
        A question's key: its database id, under its home lecture.

        NB: These are question ids, not the allocation publicIds
        @@quizdb-sync uses, so they don't identify an allocation. A student
        who answers seeded questions and then syncs gets each answer logged
        and skipped by parseAnswerQueue(), which finds no allocation for
        them---so seeded answers won't count towards a grade until something
        server-side maps questionId back to that student's allocation.
        """
        return '%s/%d/%d.json' % (
            self.QUESTION_DIR,
            self._homeLecture(dbQn).lectureId,
            dbQn.questionId,
        )

    def _objFileName(self, obj):
        return self._fileName('/'.join(obj.getPhysicalPath()))

    def _lectureUri(self, dbLec):
        """Lecture identity URI: base + the lecture's own key"""
        return self.base + self._lectureFileName(dbLec)

    def lectureQuestions(self, dbLec):
        """
        Every question in the lecture that can work offline without a student.

        onlineOnly currently means "is a template", which is also what can't
        be dumped: templates are generated per request out of other students'
        work, so there's nothing fixed to bundle. Filtering on onlineOnly
        rather than qnType stays correct if that changes.
        """
        return (Session.query(db.Question)
            .filter(db.Question.lectures.contains(dbLec))
            .filter(db.Question.active == True)
            .filter(db.Question.onlineOnly == False)
            .order_by(db.Question.plonePath)
            .all())

    def dumpLecture(self, lectureObj, dbLec, nextDbLec, emitted):
        """
        Yield (filename, content) for each of the lecture's questions, then
        for the lecture itself---last, since its 'questions' isn't final
        until we know which questions render.

        'emitted' is the question keys written by earlier lectures, so an
        alias question listed by several is only written once.
        """
        questions = []
        for dbQn in self.lectureQuestions(dbLec):
            try:
                fileName = self._questionFileName(dbQn)
            except ValueError:
                # No home lecture row, so nowhere to store it. Leave it out
                # of the listing too, rather than naming a file we won't
                # write.
                logger.warn("Skipping %s: home lecture missing", dbQn.plonePath)
                continue
            if fileName not in emitted:
                try:
                    qnData = self.getQuestionData(dbQn, dbLec)
                except NotFound:
                    # No @@data to render, so likewise leave it out
                    logger.warn("Skipping %s: no question data", dbQn.plonePath)
                    continue
                emitted.add(fileName)
                yield fileName, qnData
            questions.append(dict(
                # The key we just emitted it under, so the two can't drift
                uri=self.base + fileName,
                _type='regular',
                chosen=dbQn.timesAnswered,
                correct=dbQn.timesCorrect,
                online_only=False,
            ))

        yield self._lectureFileName(dbLec), dict(
            uri=self._lectureUri(dbLec),
            # The next lecture in this dump, so it resolves here
            next_uri=self._lectureUri(nextDbLec) if nextDbLec else None,
            slide_uri=self.lectureObjToUrl(lectureObj, 'slide-html'),
            review_uri=self.lectureObjToUrl(lectureObj, 'quizdb-review-ugqn'),
            title=lectureObj.title,
            questions=questions,
        )

    def asJsonItems(self, data):
        # NB: Before we start streaming, so returning 403 is possible
        self.requireDumpKey()

        data = data or {}
        self._homeLectures = {}
        self.base = self._normaliseBase(
            data.get('base', self.portalObject().absolute_url())
        )

        lectureObjs = [
            l.getObject()
            for l
            in self.context.restrictedTraverse('@@folderListing')(
                portal_type='tw_lecture',
                sort_on='id',
            )
        ]

        # Resolve every lecture up front, so next_uri can name the lecture
        # we are really going to include
        dumpable = []
        for lectureObj in lectureObjs:
            try:
                dbLec = getDbLecture('/'.join(lectureObj.getPhysicalPath()))
            except ValueError:
                # Never synced, so there's nothing to dump. Skip rather than
                # failing the whole tutorial over one lecture.
                logger.warn("Skipping %s: not in the database", lectureObj.absolute_url())
                continue
            dumpable.append((lectureObj, dbLec))

        # First, needing nothing rendered, so a consumer sees the manifest's
        # head before the bulk arrives. 'lectures' is URIs, the lectures
        # being entries of their own, and a list because their order matters
        # and a JSON object's doesn't.
        yield self._objFileName(self.context), dict(
            uri=self.base + self._objFileName(self.context),
            title=self.context.title,
            lectures=[self._lectureUri(dbLec) for _obj, dbLec in dumpable],
        )

        emitted = set()
        for i, (lectureObj, dbLec) in enumerate(dumpable):
            for item in self.dumpLecture(
                lectureObj,
                dbLec,
                dumpable[i + 1][1] if i + 1 < len(dumpable) else None,
                emitted,
            ):
                yield item
