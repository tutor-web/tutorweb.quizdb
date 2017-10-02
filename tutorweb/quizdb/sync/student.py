import random

import numpy.random

from sqlalchemy import func, and_
from sqlalchemy.orm.exc import NoResultFound

from z3c.saconfig import Session

from tutorweb.quizdb import db

# Randomly-chosen questions that should result in an integer value
INTEGER_SETTINGS = set((
    'question_cap',
    'award_lecture_answered',
    'award_lecture_aced',
    'award_tutorial_aced',
    'award_templateqn_aced',
    'award_registered_lecture_answered',
    'award_registered_lecture_aced',
    'award_registered_tutorial_aced',
    'award_registered_templateqn_aced',
    'cap_template_qns',
    'cap_template_qn_reviews',
    'cap_template_qn_nonsense',
    'grade_nmin',
    'grade_nmax',
))
STRING_SETTINGS = set(('iaa_mode', 'grade_algorithm'))
SERVERSIDE_SETTINGS = [
    'prob_template_eval',
    'cap_template_qns',
    'cap_template_qn_reviews',
    'question_cap',
    'award_lecture_answered',
]


def _chooseSettingValue(lgs):
    """Return a new value according to restrictions in the lgs object"""
    if lgs.key in STRING_SETTINGS and (lgs.shape is not None or lgs.max is not None):
        raise ValueError("Cannot choose random value for setting %s" % lgs.key)

    if lgs.shape is not None:
        # Fetch value according to a gamma function
        for i in xrange(10):
            out = numpy.random.gamma(shape=float(lgs.shape), scale=float(lgs.value))
            if lgs.max is None or (lgs.min or 0) <= out < lgs.max:
                if lgs.key in INTEGER_SETTINGS:
                    out = int(round(out))
                return str(out)
        raise ValueError("Cannot pick value that satisfies shape %f / value %f / min %f / max %f" % (
            lgs.shape,
            lgs.value,
            lgs.min,
            lgs.max,
        ))

    if lgs.max is not None:
        # Uniform random choice
        out = random.uniform(lgs.min or 0, lgs.max)
        if lgs.key in INTEGER_SETTINGS:
            out = int(round(out))
        return str(out)

    # Nothing to choose, use default value
    return None


def getStudentSettings(dbLec, dbStudent):
    """Fetch settings for this lecture, customised for the student"""
    latestLectureVersion = (Session.query(func.max(db.LectureGlobalSetting.lectureVersion))
                            .filter_by(lectureId=dbLec.lectureId)
                           ).one()[0]

    # Copy any existing student-specific settings in first
    out = {}
    for lss in (Session.query(db.LectureStudentSetting)
                .filter_by(lectureId=dbLec.lectureId)
                .filter_by(lectureVersion=latestLectureVersion)
                .filter_by(student=dbStudent)
               ):
        out[lss.key] = lss.value

    # Check all global settings for the lecture
    for lgs in (Session.query(db.LectureGlobalSetting)
                .filter_by(lectureId=dbLec.lectureId)
                .filter_by(lectureVersion=latestLectureVersion)
               ):
        if lgs.key in out:
            # Already have a current student-overriden setting, ignore this one
            continue

        # Find any previous setting, if it was created with the same values copy it
        old_set = (Session.query(db.LectureGlobalSetting, db.LectureStudentSetting)
                .join(db.LectureStudentSetting, and_(
                      db.LectureGlobalSetting.lectureId == db.LectureStudentSetting.lectureId,
                      db.LectureGlobalSetting.lectureVersion == db.LectureStudentSetting.lectureVersion,
                      db.LectureGlobalSetting.key == db.LectureStudentSetting.key))
                .filter_by(lectureId=dbLec.lectureId)
                .filter_by(key=lgs.key)
                .filter(db.LectureStudentSetting.student == dbStudent)
                .order_by(db.LectureGlobalSetting.lectureVersion.desc())
                .first())
        if old_set and lgs.equivalent(old_set[0]):
            Session.add(old_set[1].recreate(latestLectureVersion))
            out[lgs.key] = old_set[1].value
            continue

        newValue = _chooseSettingValue(lgs)
        if newValue is None:
            # We don't need a customised value, just use the global one.
            out[lgs.key] = lgs.value
        else:
            # Save new value to DB
            Session.add(db.LectureStudentSetting(
                lectureId=dbLec.lectureId,
                lectureVersion=latestLectureVersion,
                student=dbStudent,
                key=lgs.key,
                value=newValue,
            ))
            out[lgs.key] = newValue
    Session.flush()

    out['lecture_version'] = str(latestLectureVersion)
    return out
