DEFAULT_QUESTION_CAP = 100  # Maximum number of questions to assign to user

class Allocation(object):
    @classmethod
    def allocFor(cls, student, dbLec, urlBase="/"):
        from .original import OriginalAllocation

        klass = OriginalAllocation  # There is only one
        return klass(
            student=student,
            dbLec=dbLec,
            urlBase=urlBase,
        )

    @classmethod
    def allocFromUri(cls, student, uri, urlBase="/"):
        from .original import OriginalAllocation

        # TODO: If URIs look like (lecture-id):(whatever), can choose on that.
        # NB: URIs Need to be unique for localStorage's sake

        # Fall back to OriginalAllocation
        return OriginalAllocation.allocFromUri(student, uri, urlBase)

    def __init__(self, student, dbLec, urlBase="/"):
        self.student = student
        self.dbLec = dbLec
        self.urlBase = urlBase

    def getQuestion(self, uri, **kwargs):
        qns = list(self.getQuestions(uris=[uri], **kwargs))
        if len(qns) != 1:
            return None
        return qns[0][1]

    def getAllQuestions(self, **kwargs):
        return self.getQuestions(uris=None, **kwargs)
