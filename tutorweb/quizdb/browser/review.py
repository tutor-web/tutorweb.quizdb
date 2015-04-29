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
            .filter(db.Question.lectures.contains(self.getDbLecture()))
            .order_by(db.UserGeneratedQuestion.ugQuestionId)
            .all())

        # Get all our questions, interleave questions with answers
        out = []
        answerIndex = 0
        for (ugQn, alloc) in (Session.query(db.UserGeneratedQuestion, db.Allocation)
                .join(db.Question).join(db.Allocation)
                # NB: question/student/revision would be unique, this *should* be.
                .filter(db.Allocation.studentId == student.studentId)
                .filter(db.Allocation.active == True)
                .filter(db.Allocation.lectureId == self.getDbLecture().lectureId)
                .filter(db.UserGeneratedQuestion.studentId == student.studentId)
                .filter(db.UserGeneratedQuestion.superseded == None)
                .order_by(db.UserGeneratedQuestion.ugQuestionId)
                .all()):

            out.append(dict(
                uri='%s/quizdb-get-question/%s?author_qn=yes&question_id=%d' % (
                    self.portalObject().absolute_url(),
                    alloc.publicId,
                    ugQn.ugQuestionId,
                ),
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
                explanation=self.texToHTML(ugQn.explanation),
                answers=[],
                verdict=(-2 if ugQn.superseded else None),
            ))

            # NB: Both arrays are ordered by ugQuestionId, so can iterate through at same pace
            while answerIndex < len(ugAnswers) and ugAnswers[answerIndex].ugQuestionId == ugQn.ugQuestionId:
                out[-1]['answers'].append(dict(
                    id=ugAnswers[answerIndex].ugAnswerId,
                    rating=ugAnswers[answerIndex].questionRating,
                    comments=ugAnswers[answerIndex].comments,
                ))
                answerIndex += 1

        for qn in out:
            if qn['verdict'] is not None:
                continue

            # Work out modal rating for each question
            ratings = [a['rating'] for a in qn['answers'] if a['rating'] is not None]
            qn['verdict'] = max(set(ratings), key=ratings.count) if len(ratings) > 0 else None

        return sorted(out, key=lambda k: (k['verdict'], k['text']), reverse = True)
