import calendar
import datetime
import logging
import random
import re

from sqlalchemy.sql import func
from sqlalchemy.orm.exc import NoResultFound
from z3c.saconfig import Session

from tutorweb.quizdb import db
from .base import JSONBrowserView


# logging.getLogger('sqlalchemy.engine').setLevel(logging.DEBUG)


class TutorSettingsView(JSONBrowserView):
    """Show / set current tutor settings, their competencies, rate & extra info"""

    def asDict(self, data):
        tutor = Session.query(db.Tutor).get(self.getCurrentStudent().studentId)
        if tutor is None:
            tutor = db.Tutor(
                tutorId=self.getCurrentStudent().studentId,
                name="tutor-%d" % random.randrange(1000, 9999),
            )
            Session.add(tutor)
            Session.flush()

        if data:
            tutor.name = data.get('name', tutor.name)
            tutor.rate = data.get('rate', tutor.rate)
            tutor.details = data.get('details', tutor.details)

            # Kill any active sessions
            for cs in (Session.query(db.ChatSession)
                    .filter(db.ChatSession.tutorStudent == self.getCurrentStudent())
                    .filter(db.ChatSession.endTime == None)):
                cs.endTime = datetime.datetime.utcnow()

            # Assign new chat session to tutor
            cs = db.ChatSession(tutorId = self.getCurrentStudent().studentId)
            Session.add(cs)
            cs.connectTime = cs.connectTime or datetime.datetime.utcnow()
            Session.flush()
        else:
            # If just viewing, don't mangle chat sessions just yet
            cs = None

        return dict(
            name=tutor.name,
            rate=tutor.rate,
            details=tutor.details,
            chat_session=str(cs.chatSessionGuid) if cs else None,
            competencies=[l.plonePath for l in tutor.competentLectures]
        )


class ProspectiveTutorsView(JSONBrowserView):
    """Show students prospective tutors for the current lecture"""
    def asDict(self, data):
        if 'lec_uri' not in data:
            raise ValueError("Should specify a lecture URI")
        if 'chat_session' in data:
            # Kill any active sessions
            for cs in (Session.query(db.ChatSession)
                    .filter(db.ChatSession.pupilStudent == self.getCurrentStudent())
                    .filter(db.ChatSession.endTime == None)):
                cs.endTime = datetime.datetime.utcnow()

            cs = (Session.query(db.ChatSession)
                .with_lockmode('update')
                .filter(db.ChatSession.chatSessionGuid == data['chat_session'])
                .one())
            if cs.pupilStudent is not None and cs.pupilStudent != self.getCurrentStudent():
                raise ValueError("Tutor is busy with another student")
            cs.pupilStudent = self.getCurrentStudent()
            cs.pupilName = "pupil-%d" % random.randrange(1000, 9999)
            cs.startTime = cs.startTime or datetime.datetime.utcnow()
            cs.maxSeconds = cs.maxSeconds or data.get('max_seconds', 15 * 60)
            Session.flush()

            return dict(
                max_seconds=cs.maxSeconds,
                chat_session=str(cs.chatSessionGuid),
            )

        tutorSessions = (Session.query(db.Tutor, db.ChatSession)
            .join(db.ChatSession, db.Tutor.tutorId == db.ChatSession.tutorId)
            .filter(db.Tutor.tutorId != self.getCurrentStudent().studentId)
            .filter(db.Tutor.competentLectures.contains(self.getDbLecture(data['lec_uri'])))
            .filter(db.ChatSession.pupilId == None)  # i.e. nobody took up this offer yet
            .filter(db.ChatSession.endTime == None)  # i.e. tutor hasn't left yet
            .all())
        return dict(
            currentlyAvailable=[dict(
                name=tutor.name,
                rate=tutor.rate,
                details=tutor.details,
                chat_session=str(session.chatSessionGuid),
            ) for (tutor, session) in tutorSessions],
        )


class SessionStart(JSONBrowserView):
    """Connect to given session, forward them to socket.io server"""

    def asDict(self, data):
        if not data.get('chat_session', None):
            raise ValueError("Should specify a chat_session")
        try:
            cs = Session.query(db.ChatSession).filter(db.ChatSession.chatSessionGuid == data['chat_session']).one()
        except NoResultFound:
            raise ValueError("Chat session %s unknown" % data['chat_session'])

        if cs.endTime is not None:
            raise ValueError("Chat session already finished")
        elif cs.tutorStudent == self.getCurrentStudent():
            userRole = 'tutor'
            userNick = cs.tutor.name
        elif cs.pupilStudent is None or cs.pupilStudent == self.getCurrentStudent():
            userRole = 'pupil'
            userNick = cs.pupilName
        else:
            raise ValueError("Chat session already claimed by another pupil")

        if cs.maxSeconds is not None and cs.startTime is not None:
            remainingSeconds = cs.maxSeconds - (datetime.datetime.utcnow() - cs.startTime).total_seconds()
            if remainingSeconds < 0:
                cs.endTime = datetime.datetime.utcnow()
                raise ValueError("Chat session already finished")
        else:
            remainingSeconds = None

        return dict(
            room_name = str(cs.chatSessionGuid),
            user_role = userRole,
            user_nick = userNick,
            connect_time = calendar.timegm(cs.connectTime.timetuple()) if cs.connectTime else None,
            start_time = calendar.timegm(cs.startTime.timetuple()) if cs.startTime else None,
            max_seconds = cs.maxSeconds,
            remaining_seconds = remainingSeconds,
        )


class SessionEnd(JSONBrowserView):
    """End chat session"""

    def asDict(self, data):
        if not data.get('chat_session', None):
            raise ValueError("Should specify a chat_session")
        cs = Session.query(db.ChatSession).filter(db.ChatSession.chatSessionGuid == data['chat_session']).one()

        if cs.tutorStudent == self.getCurrentStudent():
            userRole = 'tutor'
        elif cs.pupilStudent == self.getCurrentStudent():
            userRole = 'pupil'
        else:
            raise ValueError("You are neither a tutor or a pupil of this session")

        cs.endTime = cs.endTime or datetime.datetime.utcnow()
        if cs.startTime:
            sessionTime = (cs.endTime - cs.startTime).total_seconds()
            if sessionTime > 60:
                cs.coinsAwarded = cs.tutor.rate * sessionTime

        return dict(
            room_name = str(cs.chatSessionGuid),
            user_role = userRole,
            connect_time = calendar.timegm(cs.connectTime.timetuple()) if cs.connectTime else None,
            start_time = calendar.timegm(cs.startTime.timetuple()) if cs.startTime else None,
            end_time = calendar.timegm(cs.endTime.timetuple()) if cs.endTime else None,
            coins_awarded = cs.coinsAwarded,
        )
