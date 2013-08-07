import datetime

import sqlalchemy.event
import sqlalchemy.schema
import sqlalchemy.types
from tutorweb.quizdb import ORMBase


class Allocation(ORMBase):
    """Allocation table: Which students are working on which questions"""
    __tablename__ = 'allocation'

    allocationId = sqlalchemy.schema.Column(
        sqlalchemy.types.Integer(),
        primary_key=True,
        autoincrement=True,
    )
    allocationPublicId = sqlalchemy.schema.Column(
        sqlalchemy.types.String(64),
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
    )
    allocationTime = sqlalchemy.schema.Column(
        sqlalchemy.types.DateTime(),
        nullable=False,
        default=datetime.now,
    )


@sqlalchemy.event.listens_for(Allocation, "before_insert")
def generatePublicId(mapper, connection, instance):
    """Generate a sparse ID for this row"""
    #TODO: Encrypt / faff about with raw data?
    instance.allocationPublicId = (
        instance.studentId +
        instance.questionId +
        instance.allocationTime
    )


class Question(ORMBase):
    """Question table: Per-question stats"""
    __tablename__ = 'question'

    questionId = sqlalchemy.schema.Column(
        sqlalchemy.types.Integer(),
        primary_key=True,
        autoincrement=True,
    )
    questionPath = sqlalchemy.schema.Column(
        sqlalchemy.types.String(64),
        nullable=False,
    )
    timesAskedFor = sqlalchemy.schema.Column(
        sqlalchemy.types.Integer(),
        nullable=False,
        default=0,
    )
    timesCorrect = sqlalchemy.schema.Column(
        sqlalchemy.types.Integer(),
        nullable=False,
        default=0,
    )


class Student(ORMBase):
    """Student table: Students of quizzes"""
    __tablename__ = 'answer'

    studentId = sqlalchemy.schema.Column(
        sqlalchemy.types.Integer(),
        primary_key=True,
        autoincrement=True,
    )
    studentPloneId = sqlalchemy.schema.Column(
        sqlalchemy.types.String(64),
        nullable=False,
    )


class Answer(ORMBase):
    """Answer table: List of all answers for questions"""
    __tablename__ = 'question'

    answerId = sqlalchemy.schema.Column(
        sqlalchemy.types.Integer(),
        primary_key=True,
        autoincrement=True,
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
    )
    chosenAnswer = sqlalchemy.schema.Column(
        sqlalchemy.types.Integer(),
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
