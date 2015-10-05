import csv
from StringIO import StringIO

from collections import defaultdict
# import logging
# logging.getLogger('sqlalchemy.engine').setLevel(logging.DEBUG)

from z3c.saconfig import Session

from Products.Five.browser import BrowserView

from tutorweb.quizdb import db
from .base import BrowserViewHelpers


class CSVView(BrowserView):
    fileId = "results"

    def generateRows(self):
        """Generate array-of-arrays"""
        raise NotImplementedError

    def __call__(self):
        """Turn student answers into a CSV"""
        out = StringIO()
        writer = csv.writer(out) # TODO: UTF-8 if you please
        for row in self.generateRows():
            writer.writerow(row)

        filename = "%s-%s.csv" % (self.context.id, self.fileId)
        self.request.response.setHeader('Content-Type', 'text/csv')
        self.request.response.setHeader('Content-Disposition', 'attachment; filename="%s"' % filename)
        #TODO: Streaming?
        return out.getvalue()


class StudentResultsView(BrowserView, BrowserViewHelpers):
    """Show a table of student results for the class"""

    def lecturesInClass(self):
        """URL & title of each each of classes lectures"""
        lectures = [r.to_object for r in self.context.lectures]
        return [dict(
            url=lec.absolute_url(),
            id='/'.join(lec.getPhysicalPath()[2:]),
        ) for lec in lectures]

    def allStudentGrades(self, summaryValue = None):
        """
        Get entries from AnswerSummary for the classes lectures / students
        """
        if not summaryValue:
            summaryValue = 'grade'
        classStudents = self.context.students or []
        aliasStudents = {}

        # Query for non-email form too
        for s in classStudents:
            if '@' in s and s.split('@', 1)[0] not in classStudents:
                aliasStudents[s.split('@', 1)[0]] = s

        lecturePaths = [r.to_path for r in self.context.lectures]
        dbTotals = (
            Session.query(getattr(db.AnswerSummary, summaryValue))
            .add_columns(db.Student.userName, db.Lecture.plonePath)
            .join(db.Student)
            .filter(db.Student.hostId == self.getDbHost().hostId)
            .filter(db.Student.userName.in_(classStudents + aliasStudents.keys()))
            .join(db.Lecture)
            .filter(db.Lecture.hostId == self.getDbHost().hostId)
            .filter(db.Lecture.plonePath.in_(lecturePaths))
            .all())

        # First convert to deep dict: user -> lecture -> results
        toDict = defaultdict(lambda: defaultdict(lambda: '-'))
        for (val, userName, plonePath) in dbTotals:
            d = toDict[aliasStudents.get(userName, userName)]
            # If both userName and the alias exist, choose the higest value
            d[plonePath] = max(0 if d[plonePath] == '-' else d[plonePath], val)

        # Next, rearrange into a convenient table
        return [{
            'username': student,
            summaryValue: [toDict[student][l] for l in lecturePaths],
        } for student in classStudents]


class StudentSummaryTableView(CSVView, StudentResultsView):
    fileId = "summary"

    def generateRows(self):
        summaryValue = self.request.get('value', 'grade')
        lecs = self.lecturesInClass()

        # Headers
        yield ['Student ' + summaryValue] + [l['id'] for l in lecs]

        # Data
        for row in self.allStudentGrades(summaryValue):
            yield [row['username']] + row[summaryValue]


class StudentTableView(CSVView, BrowserViewHelpers):
    """Download a CSV file of all students' answers"""
    fileId = "results"

    def generateRows(self):
        """
        Get entries from Answer for the classes lectures / students
        """
        yield [
            'Student',
            'Lecture',
            'Question',
            'Chosen answer',
            'Correct',
            'Time answered',
            'Grade',
            'Practice',
        ]

        allStudents = self.context.students or []
        lecturePaths = [r.to_path for r in self.context.lectures]
        for row in (
            Session.query(db.Answer)
                .add_columns(db.Student.userName, db.Lecture.plonePath, db.Question.plonePath)
                .join(db.Student)
                .filter(db.Student.hostId == self.getDbHost().hostId)
                .filter(db.Student.userName.in_(allStudents))
                .join(db.Lecture)
                .filter(db.Lecture.hostId == self.getDbHost().hostId)
                .filter(db.Lecture.plonePath.in_(lecturePaths))
                .join(db.Question, db.Question.questionId == db.Answer.questionId)
                .order_by(db.Student.userName, db.Lecture.plonePath, db.Answer.timeEnd)):
            yield [
                row[1],
                row[2],
                row[3],
                row[0].chosenAnswer,
                row[0].correct,
                row[0].timeEnd,
                row[0].grade,
                row[0].practice,
            ]
