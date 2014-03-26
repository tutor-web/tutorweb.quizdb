from hashlib import md5
from datetime import datetime

import sqlalchemy.event
import sqlalchemy.schema
import sqlalchemy.types
from sqlalchemy.sql import func

from tutorweb.quizdb import ORMBase


class ForceInt(sqlalchemy.types.TypeDecorator):
    """Round any passed parameter to int"""

    impl = sqlalchemy.types.Integer

    def process_bind_param(self, value, dialect):
        return round(value) if value else value


class Allocation(ORMBase):
    """Allocation table: Which students are working on which questions"""
    __tablename__ = 'allocation'
    __table_args__ = (
        sqlalchemy.schema.UniqueConstraint('studentId', 'questionId', name='uniq_studid_qnid'),
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
    questionId = sqlalchemy.schema.Column(
        sqlalchemy.types.Integer(),
        sqlalchemy.schema.ForeignKey('question.questionId'),
        nullable=False,
    )
    allocationTime = sqlalchemy.schema.Column(
        sqlalchemy.types.DateTime(),
        nullable=False,
        default=datetime.now,
    )


@sqlalchemy.event.listens_for(Allocation, "before_insert")
def generatePublicId(mapper, connection, instance):
    """Generate a sparse ID for this row"""
    #TODO: Surely this shouldn't be predictable?
    instance.publicId = md5('%s:%s:%s' % (
        instance.studentId,
        instance.questionId,
        datetime.now()
    )).hexdigest()


class Lecture(ORMBase):
    """DB -> Plone question lookup table"""
    __tablename__ = 'lecture'
    __table_args__ = dict(
        mysql_engine='InnoDB',
        mysql_charset='utf8',
    )

    lectureId = sqlalchemy.schema.Column(
        sqlalchemy.types.Integer(),
        autoincrement=True,
        primary_key=True,
    )
    plonePath = sqlalchemy.schema.Column(
        sqlalchemy.types.String(128),
        nullable=False,
        unique=True,
        index=True,
    )


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
    plonePath = sqlalchemy.schema.Column(
        sqlalchemy.types.String(128),
        nullable=False,
        unique=True,
    )
    lectureId = sqlalchemy.schema.Column(
        sqlalchemy.types.Integer(),
        sqlalchemy.schema.ForeignKey('lecture.lectureId'),
        nullable=False,
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
        default=datetime.now,
        onupdate=func.now(),
    )
    active = sqlalchemy.schema.Column(
        sqlalchemy.types.Boolean(),
        nullable=False,
        default=True,
    )


class Student(ORMBase):
    """Student table: Students of quizzes"""
    __tablename__ = 'student'
    __table_args__ = dict(
        mysql_engine='InnoDB',
        mysql_charset='utf8',
    )

    studentId = sqlalchemy.schema.Column(
        sqlalchemy.types.Integer(),
        primary_key=True,
        autoincrement=True,
    )
    userName = sqlalchemy.schema.Column(
        sqlalchemy.types.String(64),
        nullable=False,
        unique=True,
        index=True,
    )
    eMail = sqlalchemy.schema.Column(
        sqlalchemy.types.String(64),
        nullable=False,
        unique=True,
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
        nullable=False,
    )
    correct = sqlalchemy.schema.Column(
        sqlalchemy.types.Boolean(),
        nullable=False,
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
    set_grade_alpha = sqlalchemy.schema.Column(
        sqlalchemy.types.Numeric(precision=4, scale=3, asdecimal=False),
        nullable=True,
        default=None,
    )
    set_grade_s = sqlalchemy.schema.Column(
        ForceInt(),
        nullable=True,
        default=None,
    )
