import random

from AccessControl import Unauthorized
from z3c.saconfig import Session

from tutorweb.quizdb import db
from .base import JSONBrowserView

from ..sync.questions import syncPloneQuestions, getQuestionAllocation
from ..sync.answers import parseAnswerQueue

# logging.getLogger('sqlalchemy.engine').setLevel(logging.DEBUG)

SERVERSIDE_SETTINGS = [
    'prob_template_eval',
    'cap_template_qns',
    'cap_template_qn_reviews',
    'question_cap',
    'award_lecture_answered',
]
INTEGER_SETTINGS = ['grade_s', 'grade_nmin', 'grade_nmax']  # Randomly-chosen questions that should result in an integer value
STRING_SETTINGS = ['iaa_mode', 'grade_algorithm']


class SyncTutorialView(JSONBrowserView):
    def asDict(self, data):
        # If there's a incoming tutorial, break up lectures so each can be updated
        tutorial = data or dict()
        lectureDict = dict(
            (l['uri'].replace(self.context.absolute_url() + '/', ''), l)
            for l
            in tutorial.get('lectures', [])
        )

        # Fetch a list of all lectures
        lectureUrls = (
            l.id + '/quizdb-sync'
            for l
            in self.context.restrictedTraverse('@@folderListing')(
                portal_type='tw_lecture',
                sort_on='id',
            )
        )

        return dict(
            uri=self.context.absolute_url() + '/quizdb-sync',
            title=self.context.title,
            lectures=[
                self.context.restrictedTraverse(url).asDict(lectureDict.get(url, None))
                for url
                in lectureUrls
            ],
        )


class SyncLectureView(JSONBrowserView):
    def updateStudentSettings(self, dbLec, settings, student):
        """Return a dict of lecture / tutorial settings, choosing a random value if required"""

        # Get all current settings as a dict, removing old ones
        allSettings = {}
        for dbS in (Session.query(db.LectureSetting)
                .filter(db.LectureSetting.lectureId == dbLec.lectureId)
                .filter(db.LectureSetting.studentId == student.studentId)
                .all()):
            if dbS.key not in settings.keys() and dbS.key + ':max' not in settings.keys():
                # No longer in Plone, remove it here too
                Session.delete(dbS)
            else:
                allSettings[dbS.key] = dbS.value

        ignoreKey = {}
        for k in settings.keys():
            # Only update settings that have changed
            if k in allSettings and allSettings[k] == settings[k]:
                continue

            # If a variable setting has changed, assign a value and write this also
            if not(ignoreKey.get(k, False)) and (k.endswith(':max') or k.endswith(':min')):
                base_key = k.replace(":max", "").replace(":min", "")
                if base_key + ":max" not in settings:
                    raise ValueError(base_key + ":max not set in lecture")

                # Don't assign another value if/when other half shows up
                ignoreKey[base_key + ":min"] = True
                ignoreKey[base_key + ":max"] = True

                # Assign new value, rounding if appropriate
                new_value = random.uniform(
                    float(settings.get(base_key + ":min", 0)),
                    float(settings.get(base_key + ":max", None)),
                )
                if base_key in INTEGER_SETTINGS:
                    new_value = str(int(round(new_value)))
                else:
                    new_value = str(round(new_value, 3))

                Session.merge(db.LectureSetting(
                    lectureId=dbLec.lectureId,
                    studentId=student.studentId,
                    key=base_key,
                    value=new_value,
                ))
                allSettings[base_key] = new_value

            # Add / update DB
            Session.merge(db.LectureSetting(
                lectureId=dbLec.lectureId,
                studentId=student.studentId,
                key=k,
                value=settings[k],
            ))
            allSettings[k] = settings[k]

        Session.flush()

        # Remove :min and :max, not useful downstream
        return dict((k, allSettings[k]) for k in allSettings.keys() if ':' not in k)

    def asDict(self, data):
        student = self.getCurrentStudent()
        portalObj = self.portalObject()
        dbLec = self.getDbLecture()

        # Check we're the right user, given the data
        lecture = data or dict()
        if lecture.get('user', None) and lecture['user'] != student.userName:
            raise Unauthorized('This drill is for user ' + lecture['user'] + ', not ' + student.userName)

        # Fetch lecture settings for current student
        settings = self.updateStudentSettings(
            dbLec,
            self.context.unrestrictedTraverse('@@drill-settings').asDict(),
            student,
        )

        # Make sure DB is in sync with Plone
        syncPloneQuestions(
            dbLec,
            self.context,
        )

        # Parse answer queue first to update question counts
        answerQueue = parseAnswerQueue(
            dbLec,
            self.context,
            student,
            lecture.get('answerQueue', []),
            settings,
        )

        # ... then fetch question lists
        questions = getQuestionAllocation(
            dbLec,
            student,
            portalObj.absolute_url(),
            settings,
            targetDifficulty=(answerQueue[-1].get('grade_after', None) if len(answerQueue) > 8 else None),
            reAllocQuestions=(len(answerQueue) > 10 and len(answerQueue) % 10 == 0),
        )

        # Build lecture dict
        return dict(
            uri=self.context.absolute_url() + '/quizdb-sync',
            user=student.userName,
            question_uri=self.context.absolute_url() + '/quizdb-all-questions',
            slide_uri=self.context.absolute_url() + '/slide-html',
            review_uri=self.context.absolute_url() + '/quizdb-review-ugqn',
            title=self.context.title,
            settings=dict((k, v) for k, v in settings.items() if k not in SERVERSIDE_SETTINGS),
            answerQueue=answerQueue,
            questions=questions,
        )
