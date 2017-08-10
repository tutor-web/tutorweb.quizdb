from AccessControl import Unauthorized

from .base import JSONBrowserView

from ..allocation.base import Allocation
from ..sync.questions import getQuestionAllocation
from ..sync.answers import parseAnswerQueue
from ..sync.student import getStudentSettings

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
            uri=self.lectureObjToUrl(self.context),
            title=self.context.title,
            lectures=[
                self.context.restrictedTraverse(url).asDict(lectureDict.get(url, None))
                for url
                in lectureUrls
            ],
        )


class SyncLectureView(JSONBrowserView):
    def asDict(self, data):
        student = self.getCurrentStudent()
        portalObj = self.portalObject()
        dbLec = self.getDbLecture()

        # Check we're the right user, given the data
        lecture = data or dict()
        if lecture.get('user', None) and lecture['user'] != student.userName:
            raise Unauthorized('This drill is for user ' + lecture['user'] + ', not ' + student.userName)

        # Get settings for student
        settings = getStudentSettings(dbLec, student)

        allocObj = Allocation.allocFor(
            student=student,
            dbLec=dbLec,
            urlBase=self.context.portal_url.getPortalObject().absolute_url(),
        )

        # Parse answer queue first to update question counts
        answerQueue = parseAnswerQueue(
            dbLec,
            student,
            allocObj,
            lecture.get('answerQueue', []),
            settings,
            studentSettings=lecture.get('settings', []),
        )

        # ... then fetch question lists
        questions = getQuestionAllocation(
            dbLec,
            student,
            portalObj.absolute_url(),
            settings,
            targetDifficulty=(answerQueue[-1].get('grade_after', None) if len(answerQueue) > 8 else None),
            # TODO: If just syncing then this will cause lots of churn
            # TODO: This also will only reallocate at precisely a 10 boundary, unlikely.
            reAllocQuestions=(len(answerQueue) > 10 and len(answerQueue) % 10 == 0),
        )

        # Build lecture dict
        return dict(
            uri=self.lectureObjToUrl(self.context),
            user=student.userName,
            question_uri=self.lectureObjToUrl(self.context, 'quizdb-all-questions'),
            slide_uri=self.lectureObjToUrl(self.context, 'slide-html'),
            review_uri=self.lectureObjToUrl(self.context, 'quizdb-review-ugqn'),
            title=self.context.title,
            settings=dict((k, v) for k, v in settings.items() if k not in SERVERSIDE_SETTINGS),
            answerQueue=answerQueue,
            questions=list(questions),
        )
