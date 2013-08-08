from hashlib import md5
from datetime import datetime

import sqlalchemy.event
import sqlalchemy.schema
import sqlalchemy.types
from tutorweb.quizdb import ORMBase


class Allocation(ORMBase):
    """Allocation table: Which students are working on which questions"""
    __tablename__ = 'allocation'
    __table_args__ = (
        sqlalchemy.schema.UniqueConstraint('studentId', 'questionId', name='uniq_studid_qnid'),
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
    instance.publicId = md5('%s:%s:%s' % (
        instance.studentId,
        instance.questionId,
        datetime.now()
    )).hexdigest()


class Question(ORMBase):
    """Question table: Per-question stats"""
    __tablename__ = 'question'

    questionId = sqlalchemy.schema.Column(
        sqlalchemy.types.Integer(),
        autoincrement=True,
        primary_key=True,
    )
    plonePath = sqlalchemy.schema.Column(
        sqlalchemy.types.String(64),
        nullable=False,
        unique=True,
    )
    parentPath = sqlalchemy.schema.Column(
        sqlalchemy.types.String(64),
        nullable=False,
        index=True,
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
    )


class Student(ORMBase):
    """Student table: Students of quizzes"""
    __tablename__ = 'student'

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


class Answer(ORMBase):
    """Answer table: List of all answers for questions"""
    __tablename__ = 'answer'

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
        index=True,
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
