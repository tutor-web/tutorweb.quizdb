from uuid import uuid4
from hashlib import md5
from datetime import datetime
from random import random

from sqlalchemy import Table, UniqueConstraint
from sqlalchemy.orm import relationship
import sqlalchemy.event
import sqlalchemy.schema
import sqlalchemy.types
from sqlalchemy.sql import func

from tutorweb.quizdb import ORMBase, customtypes

class Allocation(ORMBase):
    """Allocation table: Which students are working on which questions"""
    __tablename__ = 'allocation'
    __table_args__ = (
        dict(
            mysql_engine='InnoDB',
            mysql_charset='utf8',
        )
    )

    allocationId = sqlalchemy.schema.Column(
        sqlalchemy.types.Integer(),
        primary_key=True,
        autoincrement=True,
    )
    publicId = sqlalchemy.schema.Column(
        sqlalchemy.types.String(32),
        nullable=False,
        unique=True,
        index=True,
    )
    studentId = sqlalchemy.schema.Column(
        sqlalchemy.types.Integer(),
        sqlalchemy.schema.ForeignKey('student.studentId'),
        nullable=False,
        index=True,
    )
    lectureId = sqlalchemy.schema.Column(
        sqlalchemy.types.Integer(),
        sqlalchemy.schema.ForeignKey('lecture.lectureId'),
        nullable=False,
    )
    questionId = sqlalchemy.schema.Column(
        sqlalchemy.types.Integer(),
        sqlalchemy.schema.ForeignKey('question.questionId'),
        nullable=False,
    )
    allocationTime = sqlalchemy.schema.Column(
        sqlalchemy.types.DateTime(),
        nullable=False,
        default=datetime.utcnow,
    )
    active = sqlalchemy.schema.Column(
        sqlalchemy.types.Boolean(),
        nullable=False,
        default=True,
    )


@sqlalchemy.event.listens_for(Allocation, "before_insert")
def generatePublicId(mapper, connection, instance):
    """Generate a sparse ID for this row"""
    instance.publicId = md5('%s:%s:%s:%s' % (
        instance.studentId,
        instance.questionId,
        datetime.utcnow(),
        random(),
    )).hexdigest()


class Host(ORMBase):
    """Host table: Hosts that run tutorweb"""
    __tablename__ = 'host'
    __table_args__ = dict(
        mysql_engine='InnoDB',
        mysql_charset='utf8',
    )

    hostId = sqlalchemy.schema.Column(
        sqlalchemy.types.Integer(),
        primary_key=True,
        autoincrement=True,
    )
    fqdn = sqlalchemy.schema.Column(
        sqlalchemy.types.String(64),
        nullable=False,
        unique=True,
        index=True,
    )
    hostKey = sqlalchemy.schema.Column(
        sqlalchemy.types.String(32),
        nullable=False,
    )


lectureQuestionTable = Table('lectureQuestions', ORMBase.metadata,
    sqlalchemy.schema.Column(
        'lectureId',
        sqlalchemy.types.Integer(),
        sqlalchemy.schema.ForeignKey('lecture.lectureId'),
        nullable=False,
    ),
    sqlalchemy.schema.Column(
        'questionId',
        sqlalchemy.types.Integer(),
        sqlalchemy.schema.ForeignKey('question.questionId'),
        nullable=False,
    ),

    mysql_engine='InnoDB',
    mysql_charset='utf8',
)

class Lecture(ORMBase):
    """DB -> Plone question lookup table"""
    __tablename__ = 'lecture'
    __table_args__ = (
        UniqueConstraint('hostId', 'plonePath'),
        dict(
            mysql_engine='InnoDB',
            mysql_charset='utf8',
        )
    )

    lectureId = sqlalchemy.schema.Column(
        sqlalchemy.types.Integer(),
        autoincrement=True,
        primary_key=True,
    )
    hostId = sqlalchemy.schema.Column(
        sqlalchemy.types.Integer(),
        sqlalchemy.schema.ForeignKey('host.hostId'),
        nullable=False,
    )
    plonePath = sqlalchemy.schema.Column(
        sqlalchemy.types.String(128),
        nullable=False,
        index=True,
    )
    questions = relationship("Question",
        secondary=lectureQuestionTable,
        backref="lectures")


class Question(ORMBase):
    """Question table: Per-question stats"""
    __tablename__ = 'question'
    __table_args__ = dict(
        mysql_engine='InnoDB',
        mysql_charset='utf8',
    )

    questionId = sqlalchemy.schema.Column(
        sqlalchemy.types.Integer(),
        autoincrement=True,
        primary_key=True,
    )
    qnType = sqlalchemy.schema.Column(
        sqlalchemy.types.String(64),
        nullable=False,
        unique=False,
        default='tw_latexquestion',
    )
    plonePath = sqlalchemy.schema.Column(
        sqlalchemy.types.String(128),
        nullable=False,
        unique=True,
    )
    correctChoices = sqlalchemy.schema.Column(
        # JSON Array of correct answers
        sqlalchemy.types.String(128),
        nullable=False,
        default="[]",
    )
    timesAnswered = sqlalchemy.schema.Column(
        sqlalchemy.types.Integer(),
        nullable=False,
        default=0,
    )
    timesCorrect = sqlalchemy.schema.Column(
        sqlalchemy.types.Integer(),
        nullable=False,
        default=0,
    )
    lastUpdate = sqlalchemy.schema.Column(
        sqlalchemy.types.DateTime(),
        nullable=False,
        default=datetime.utcnow,
    )
    active = sqlalchemy.schema.Column(
        sqlalchemy.types.Boolean(),
        nullable=False,
        default=True,
    )


class Student(ORMBase):
    """Student table: Students of quizzes"""
    __tablename__ = 'student'
    __table_args__ = (
        UniqueConstraint('hostId', 'userName'),
        dict(
            mysql_engine='InnoDB',
            mysql_charset='utf8',
        ),
    )

    studentId = sqlalchemy.schema.Column(
        sqlalchemy.types.Integer(),
        primary_key=True,
        autoincrement=True,
    )
    hostId = sqlalchemy.schema.Column(
        sqlalchemy.types.Integer(),
        sqlalchemy.schema.ForeignKey('host.hostId'),
        nullable=False,
    )
    userName = sqlalchemy.schema.Column(
        sqlalchemy.types.String(64),
        nullable=False,
        index=True,
    )
    eMail = sqlalchemy.schema.Column(
        sqlalchemy.types.String(64),
        nullable=False,
        index=True,
    )


class Answer(ORMBase):
    """Answer table: List of all answers for questions"""
    __tablename__ = 'answer'
    __table_args__ = dict(
        mysql_engine='InnoDB',
        mysql_charset='utf8',
    )

    answerId = sqlalchemy.schema.Column(
        sqlalchemy.types.Integer(),
        primary_key=True,
        autoincrement=True,
    )
    lectureId = sqlalchemy.schema.Column(
        sqlalchemy.types.Integer(),
        sqlalchemy.schema.ForeignKey('lecture.lectureId'),
        nullable=False,
    )
    studentId = sqlalchemy.schema.Column(
        sqlalchemy.types.Integer(),
        sqlalchemy.schema.ForeignKey('student.studentId'),
        nullable=False,
    )
    questionId = sqlalchemy.schema.Column(
        sqlalchemy.types.Integer(),
        sqlalchemy.schema.ForeignKey('question.questionId'),
        nullable=False,
        index=True,
    )
    chosenAnswer = sqlalchemy.schema.Column(
        sqlalchemy.types.Integer(),
        nullable=True,
    )
    correct = sqlalchemy.schema.Column(
        sqlalchemy.types.Boolean(),
        nullable=True,
    )
    timeStart = sqlalchemy.schema.Column(
        sqlalchemy.types.DateTime(),
        nullable=False,
    )
    timeEnd = sqlalchemy.schema.Column(
        sqlalchemy.types.DateTime(),
        nullable=False,
    )
    grade = sqlalchemy.schema.Column(
        sqlalchemy.types.Numeric(precision=4, scale=3, asdecimal=False),
        nullable=True,
    )
    practice = sqlalchemy.schema.Column(
        sqlalchemy.types.Boolean(),
        nullable=False,
        default=False,
    )
    coinsAwarded = sqlalchemy.schema.Column(
        sqlalchemy.types.Integer(),
        nullable=False,
        default=0,
    )
    ugQuestionGuid = sqlalchemy.schema.Column(
        customtypes.GUID(),
        sqlalchemy.schema.ForeignKey('userGeneratedQuestions.ugQuestionGuid'),
        nullable=True,
    )


class AnswerSummary(ORMBase):
    """Answer summary table: The latest results for student"""
    __tablename__ = 'answerSummary'
    __table_args__ = dict(
        mysql_engine='InnoDB',
        mysql_charset='utf8',
    )

    answerSummaryId = sqlalchemy.schema.Column(
        sqlalchemy.types.Integer(),
        primary_key=True,
        autoincrement=True,
    )
    lectureId = sqlalchemy.schema.Column(
        sqlalchemy.types.Integer(),
        sqlalchemy.schema.ForeignKey('lecture.lectureId'),
        nullable=False,
    )
    studentId = sqlalchemy.schema.Column(
        sqlalchemy.types.Integer(),
        sqlalchemy.schema.ForeignKey('student.studentId'),
        nullable=False,
    )
    grade = sqlalchemy.schema.Column(
        sqlalchemy.types.Numeric(precision=4, scale=3, asdecimal=False),
        nullable=False,
        default=0,
    )
    gradeHighWaterMark = sqlalchemy.schema.Column(
        sqlalchemy.types.Numeric(precision=4, scale=3, asdecimal=False),
        nullable=False,
        default=0,
    )
    lecAnswered = sqlalchemy.schema.Column(
        sqlalchemy.types.Integer(),
        nullable=False,
        default=0,
    )
    lecCorrect = sqlalchemy.schema.Column(
        sqlalchemy.types.Integer(),
        nullable=False,
        default=0,
    )
    practiceAnswered = sqlalchemy.schema.Column(
        sqlalchemy.types.Integer(),
        nullable=False,
        default=0,
    )
    practiceCorrect = sqlalchemy.schema.Column(
        sqlalchemy.types.Integer(),
        nullable=False,
        default=0,
    )


class LectureSetting(ORMBase):
    """Settings given to a student when answering questions"""
    __tablename__ = 'lectureSetting'
    __table_args__ = dict(
        mysql_engine='InnoDB',
        mysql_charset='utf8',
    )

    lectureId = sqlalchemy.schema.Column(
        sqlalchemy.types.Integer(),
        sqlalchemy.schema.ForeignKey('lecture.lectureId'),
        primary_key=True,
    )
    studentId = sqlalchemy.schema.Column(
        sqlalchemy.types.Integer(),
        sqlalchemy.schema.ForeignKey('student.studentId'),
        primary_key=True,
    )
    key = sqlalchemy.schema.Column(
        sqlalchemy.types.String(100),
        nullable=False,
        primary_key=True,
    )
    value = sqlalchemy.schema.Column(
        sqlalchemy.types.String(100),
        nullable=False,
    )


class UserGeneratedQuestion(ORMBase):
    """Table of questions submitted from question templates"""
    __tablename__ = 'userGeneratedQuestions'
    __table_args__ = dict(
        mysql_engine='InnoDB',
        mysql_charset='utf8',
    )

    ugQuestionId = sqlalchemy.schema.Column(
        sqlalchemy.types.Integer(),
        primary_key=True,
        autoincrement=True,
    )
    ugQuestionGuid = sqlalchemy.schema.Column(
        customtypes.GUID(),
        nullable=False,
        index=True,
        unique=True,
        default=uuid4,
    )
    questionId = sqlalchemy.schema.Column( # i.e. the question template
        sqlalchemy.types.Integer(),
        sqlalchemy.schema.ForeignKey('question.questionId'),
        nullable=False,
        index=True,
    )
    studentId = sqlalchemy.schema.Column(
        sqlalchemy.types.Integer(),
        sqlalchemy.schema.ForeignKey('student.studentId'),
        nullable=False,
        index=True,
    )
    text = sqlalchemy.schema.Column(
        sqlalchemy.types.Text(),
        nullable=False,
        default='',
    )
    choice_0_answer = sqlalchemy.schema.Column(
        sqlalchemy.types.String(1000),
        nullable=True,
    )
    choice_0_correct = sqlalchemy.schema.Column(
        sqlalchemy.types.Boolean(),
        nullable=True,
    )
    choice_1_answer = sqlalchemy.schema.Column(
        sqlalchemy.types.String(1000),
        nullable=True,
    )
    choice_1_correct = sqlalchemy.schema.Column(
        sqlalchemy.types.Boolean(),
        nullable=True,
    )
    choice_2_answer = sqlalchemy.schema.Column(
        sqlalchemy.types.String(1000),
        nullable=True,
    )
    choice_2_correct = sqlalchemy.schema.Column(
        sqlalchemy.types.Boolean(),
        nullable=True,
    )
    choice_3_answer = sqlalchemy.schema.Column(
        sqlalchemy.types.String(1000),
        nullable=True,
    )
    choice_3_correct = sqlalchemy.schema.Column(
        sqlalchemy.types.Boolean(),
        nullable=True,
    )
    choice_4_answer = sqlalchemy.schema.Column(
        sqlalchemy.types.String(1000),
        nullable=True,
    )
    choice_4_correct = sqlalchemy.schema.Column(
        sqlalchemy.types.Boolean(),
        nullable=True,
    )
    choice_5_answer = sqlalchemy.schema.Column(
        sqlalchemy.types.String(1000),
        nullable=True,
    )
    choice_5_correct = sqlalchemy.schema.Column(
        sqlalchemy.types.Boolean(),
        nullable=True,
    )
    choice_6_answer = sqlalchemy.schema.Column(
        sqlalchemy.types.String(1000),
        nullable=True,
    )
    choice_6_correct = sqlalchemy.schema.Column(
        sqlalchemy.types.Boolean(),
        nullable=True,
    )
    choice_7_answer = sqlalchemy.schema.Column(
        sqlalchemy.types.String(1000),
        nullable=True,
    )
    choice_7_correct = sqlalchemy.schema.Column(
        sqlalchemy.types.Boolean(),
        nullable=True,
    )
    choice_8_answer = sqlalchemy.schema.Column(
        sqlalchemy.types.String(1000),
        nullable=True,
    )
    choice_8_correct = sqlalchemy.schema.Column(
        sqlalchemy.types.Boolean(),
        nullable=True,
    )
    choice_9_answer = sqlalchemy.schema.Column(
        sqlalchemy.types.String(1000),
        nullable=True,
    )
    choice_9_correct = sqlalchemy.schema.Column(
        sqlalchemy.types.Boolean(),
        nullable=True,
    )
    explanation = sqlalchemy.schema.Column(
        sqlalchemy.types.Text(),
        nullable=False,
        default='',
    )
    superseded = sqlalchemy.schema.Column(
        customtypes.GUID(),
        sqlalchemy.schema.ForeignKey('userGeneratedQuestions.ugQuestionGuid'),
        nullable=True,
    )


class UserGeneratedAnswer(ORMBase):
    """Answers from students evaluating user-generated questions"""
    __tablename__ = 'userGeneratedAnswer'
    __table_args__ = dict(
        mysql_engine='InnoDB',
        mysql_charset='utf8',
    )

    ugAnswerId = sqlalchemy.schema.Column(
        sqlalchemy.types.Integer(),
        primary_key=True,
        autoincrement=True,
    )
    studentId = sqlalchemy.schema.Column(
        sqlalchemy.types.Integer(),
        sqlalchemy.schema.ForeignKey('student.studentId'),
        nullable=False,
        index=True,
    )
    ugQuestionGuid = sqlalchemy.schema.Column(
        customtypes.GUID(),
        sqlalchemy.schema.ForeignKey('userGeneratedQuestions.ugQuestionGuid'),
        nullable=False,
        index=True,
    )
    chosenAnswer = sqlalchemy.schema.Column(
        sqlalchemy.types.Integer(),
        nullable=True,
    )
    questionRating = sqlalchemy.schema.Column( # -1 no sense 0 easy -- 50 -- 100 hard
        sqlalchemy.types.Integer(),
        nullable=True,
    )
    comments = sqlalchemy.schema.Column(
        sqlalchemy.types.Text(),
        nullable=False,
        default='',
    )
    studentGrade = sqlalchemy.schema.Column(
        sqlalchemy.types.Numeric(precision=4, scale=3, asdecimal=False),
        nullable=False,
        default=0,
    )


class CoinAward(ORMBase):
    """Record of coins distributed to students"""
    __tablename__ = 'coinAward'
    __table_args__ = dict(
        mysql_engine='InnoDB',
        mysql_charset='utf8',
    )

    coinAwardId = sqlalchemy.schema.Column(
        sqlalchemy.types.Integer(),
        primary_key=True,
        autoincrement=True,
    )
    studentId = sqlalchemy.schema.Column(
        sqlalchemy.types.Integer(),
        sqlalchemy.schema.ForeignKey('student.studentId'),
        nullable=False,
        index=True,
    )
    amount = sqlalchemy.schema.Column(
        sqlalchemy.types.Integer(),
        nullable=False,
    )
    walletId = sqlalchemy.schema.Column(
        sqlalchemy.types.String(100),
        nullable=False,
    )
    txId = sqlalchemy.schema.Column(
        sqlalchemy.types.String(100),
        nullable=False,
    )
    awardTime = sqlalchemy.schema.Column(
        sqlalchemy.types.DateTime(),
        nullable=False,
        default=datetime.utcnow,
    )
