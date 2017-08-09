import random

import numpy.random

from sqlalchemy import func

from z3c.saconfig import Session

from tutorweb.quizdb import db


def _chooseSettingValue(lgs):
    """Return a new value according to restrictions in the lgs object"""
    if lgs.shape is not None:
        # Fetch value according to a gamma function
        for i in xrange(10):
            out = numpy.random.gamma(shape=float(lgs.shape), scale=float(lgs.value) / float(lgs.shape))
            if lgs.max is None or (lgs.min or 0) <= out < lgs.max:
                return str(out)
        raise ValueError("Cannot pick value that satisfies shape %f / value %f / min %f / max %f" % (
            lgs.shape,
            lgs.value,
            lgs.min,
            lgs.max,
        ))

    if lgs.max is not None:
        # Uniform random choice
        return str(random.uniform(lgs.min or 0, lgs.max))

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
