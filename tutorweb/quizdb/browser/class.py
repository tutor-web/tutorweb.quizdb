import csv
from StringIO import StringIO

from collections import defaultdict
# import logging
# logging.getLogger('sqlalchemy.engine').setLevel(logging.DEBUG)

from z3c.saconfig import Session

from Products.Five.browser import BrowserView

from tutorweb.quizdb import db


class StudentResultsView(BrowserView):
    """Show a table of student results for the class"""

    def lecturesInClass(self):
        """URL & title of each each of classes lectures"""
        lectures = [r.to_object for r in self.context.lectures]
        return [dict(
            url=lec.absolute_url(),
            id=lec.id,
        ) for lec in lectures]

    def allStudentGrades(self):
        """
        Get entries from AnswerSummary for the classes lectures / students
        """
        lecturePaths = [r.to_path for r in self.context.lectures]
        dbTotals = (
            Session.query(db.AnswerSummary)
            .add_columns(db.Student.userName, db.Lecture.plonePath)
            .join(db.Student)
            .filter(db.Student.userName.in_(self.context.students))
            .join(db.Lecture)
            .filter(db.Lecture.plonePath.in_(lecturePaths))
            .all())

        # First convert to deep dict: user -> lecture -> results
        asDict = defaultdict(lambda: defaultdict(lambda: '-'))
        for t in dbTotals:
            asDict[t[1]][t[2]] = t[0].grade

        # Next, rearrange into a convenient table
        return [dict(
            username=student,
            grades=[asDict[student][l] for l in lecturePaths],
        ) for student in self.context.students]


class StudentTableView(BrowserView):
    """Download a CSV file of all students' answers"""
    def allStudentAnswers(self):
        """
        Get entries from Answer for the classes lectures / students
        """
        lecturePaths = [r.to_path for r in self.context.lectures]
        return (
            Session.query(db.Answer)
            .add_columns(db.Student.userName, db.Lecture.plonePath, db.Question.plonePath)
            .join(db.Student)
            .filter(db.Student.userName.in_(self.context.students))
            .join(db.Lecture)
            .filter(db.Lecture.plonePath.in_(lecturePaths))
            .join(db.Question, db.Question.questionId == db.Answer.questionId)
            .order_by(db.Student.userName, db.Lecture.plonePath, db.Answer.timeEnd)
            .all())

    def __call__(self):
        """Turn student answers into a CSV"""
        out = StringIO()
        writer = csv.writer(out)
        writer.writerow(['Student', 'Lecture', 'Question', 'Chosen answer', 'Correct', 'Time answered', 'Grade', 'Practice'])
        for row in self.allStudentAnswers():
            writer.writerow([
                row[1],
                row[2],
                row[3],
                row[0].chosenAnswer,
                row[0].correct,
                row[0].timeEnd,
                row[0].grade,
                row[0].practice,
            ])

        filename = "%s-results.csv" % self.context.id
        self.request.response.setHeader('Content-Type', 'text/csv')
        self.request.response.setHeader('Content-Disposition', 'attachment; filename="%s"' % filename)
        #TODO: Streaming?
        return out.getvalue()
