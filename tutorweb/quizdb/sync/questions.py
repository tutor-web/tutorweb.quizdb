import hashlib
import logging
import pytz

from tutorweb.quizdb.allocation.base import Allocation

# logging.getLogger('sqlalchemy.engine').setLevel(logging.DEBUG)
logger = logging.getLogger(__package__)


def getQuestionAllocation(alloc, settings):
    # Return all active questions
    for questionUri, allocType, dbQn in alloc.updateAllocation(settings):
        yield dict(
            _type=allocType,
            uri=questionUri,
            chosen=dbQn.timesAnswered,
            correct=dbQn.timesCorrect,
            online_only=dbQn.onlineOnly,
        )


def getAllQuestionPath(questions):
    """Return all-questions URI with hash of all current question URIs"""
    return 'quizdb-all-questions?%s' % (
        hashlib.sha1("".join(sorted(q['uri'] for q in questions)).encode("utf8")).hexdigest()
    )
