from AccessControl import Unauthorized

from .base import JSONBrowserView

from ..allocation.base import Allocation
from ..sync.questions import getQuestionAllocation
from ..sync.answers import parseAnswerQueue
from ..sync.student import getStudentSettings, SERVERSIDE_SETTINGS

# logging.getLogger('sqlalchemy.engine').setLevel(logging.DEBUG)

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
            allocObj,
            lecture.get('answerQueue', []),
            settings,
            studentSettings=lecture.get('settings', []),
        )

        # ... then fetch question lists
        questions = getQuestionAllocation(
            allocObj,
            settings,
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
