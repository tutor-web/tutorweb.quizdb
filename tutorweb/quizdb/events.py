from z3c.saconfig.interfaces import IEngineCreatedEvent

from tutorweb.quizdb import ORMBase

def createdHandler(event):
    """Create any tables used"""
    ORMBase.metadata.create_all(event.engine)
