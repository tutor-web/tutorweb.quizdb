import logging

from z3c.saconfig import Session

from tutorweb.quizdb import db
from .base import JSONBrowserView

# logging.getLogger('sqlalchemy.engine').setLevel(logging.DEBUG)


class ReviewUgQnView(JSONBrowserView):
    """Look back on your questions"""

    def asDict(self, data):
        student = self.getCurrentStudent()

        # Get all answers for our questions, index by ID.
        ugAnswers = (Session.query(db.UserGeneratedAnswer)
            .join(db.UserGeneratedQuestion).join(db.Question)
            .filter(db.UserGeneratedQuestion.studentId == student.studentId)
            .filter(db.Question.lectureId == self.getLectureId())
            .order_by(db.UserGeneratedQuestion.ugQuestionId)
            .all())

        # Get all our questions, interleave questions with answers
        out = []
        answerIndex = 0
        for ugQn in (Session.query(db.UserGeneratedQuestion)
                .join(db.Question)
                .filter(db.UserGeneratedQuestion.studentId == student.studentId)
                .filter(db.Question.lectureId == self.getLectureId())
                .order_by(db.UserGeneratedQuestion.ugQuestionId)
                .all()):

            out.append(dict(
                id=ugQn.ugQuestionId,
                text=self.texToHTML(ugQn.text),
                choices=[x for x in [
                    dict(answer=self.texToHTML(ugQn.choice_0_answer), correct=ugQn.choice_0_correct),
                    dict(answer=self.texToHTML(ugQn.choice_1_answer), correct=ugQn.choice_1_correct),
                    dict(answer=self.texToHTML(ugQn.choice_2_answer), correct=ugQn.choice_2_correct),
                    dict(answer=self.texToHTML(ugQn.choice_3_answer), correct=ugQn.choice_3_correct),
                    dict(answer=self.texToHTML(ugQn.choice_4_answer), correct=ugQn.choice_4_correct),
                    dict(answer=self.texToHTML(ugQn.choice_5_answer), correct=ugQn.choice_5_correct),
                    dict(answer=self.texToHTML(ugQn.choice_6_answer), correct=ugQn.choice_6_correct),
                    dict(answer=self.texToHTML(ugQn.choice_7_answer), correct=ugQn.choice_7_correct),
                    dict(answer=self.texToHTML(ugQn.choice_8_answer), correct=ugQn.choice_8_correct),
                    dict(answer=self.texToHTML(ugQn.choice_9_answer), correct=ugQn.choice_9_correct),
                ] if x['correct'] is not None],
                answers=[],
            ))

            # NB: Both arrays are ordered by ugQuestionId, so can iterate through at same pace
            while answerIndex < len(ugAnswers) and ugAnswers[answerIndex].ugQuestionId == ugQn.ugQuestionId:
                out[-1]['answers'].append(dict(
                    id=ugAnswers[answerIndex].ugAnswerId,
                    rating=ugAnswers[answerIndex].questionRating,
                    comments=ugAnswers[answerIndex].comments,
                ))
                answerIndex += 1
        return out
