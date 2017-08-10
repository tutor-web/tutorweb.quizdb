import logging
import pytz

from tutorweb.quizdb.allocation.base import Allocation

# logging.getLogger('sqlalchemy.engine').setLevel(logging.DEBUG)
logger = logging.getLogger(__package__)


def getQuestionAllocation(dbLec, student, alloc, settings, targetDifficulty=None, reAllocQuestions=False):
    # Return all active questions
    for questionUri, allocType, dbQn in alloc.updateAllocation(settings, targetDifficulty=targetDifficulty, reAllocQuestions=reAllocQuestions):
        yield dict(
            _type=allocType,
            uri=questionUri,
            chosen=dbQn.timesAnswered,
            correct=dbQn.timesCorrect,
            online_only=dbQn.onlineOnly,
        )
