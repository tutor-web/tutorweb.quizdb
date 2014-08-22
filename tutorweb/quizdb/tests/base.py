import base64
import os
import tempfile
from unittest import TestCase
import json

from plone.app.testing import IntegrationTesting, FunctionalTesting
from z3c.saconfig import Session
from zope.configuration import xmlconfig

# Nab test case setup from tutorweb.content
from tutorweb.content.tests.base import (
    USER_A_ID,
    USER_B_ID,
    USER_C_ID,
    MANAGER_ID,
)
from tutorweb.content.tests.base import TestFixture as ContentTestFixture
from tutorweb.content.tests.base import FunctionalTestCase as ContentFunctionalTestCase
from tutorweb.quizdb import ORMBase

class TestFixture(ContentTestFixture):
    def setUpZope(self, app, configurationContext):
        super(TestFixture, self).setUpZope(app, configurationContext)
        import tutorweb.quizdb
        xmlconfig.include(configurationContext, 'configure.zcml', tutorweb.quizdb)
        self.createTempDatabase(configurationContext)
        configurationContext.execute_actions()

    def tearDownZope(self, app):
        if self.dbFileName:
            os.unlink(self.dbFileName)

    def createTempDatabase(self, configurationContext):
        """Create database and update ZCML"""
        fileno, self.dbFileName = tempfile.mkstemp(suffix='.twquizdb.db')
        xmlconfig.string("""
          <configure xmlns="http://namespaces.zope.org/zope"
                     xmlns:db="http://namespaces.zope.org/db">
            <include package="z3c.saconfig" file="meta.zcml" />
            <db:engine name="tutorweb.quizdb" url="sqlite:///%s" />
            <db:session engine="tutorweb.quizdb" />
          </configure>
        """ % self.dbFileName, context=configurationContext)


FIXTURE = TestFixture()

TUTORWEB_QUIZDB_INTEGRATION_TESTING = IntegrationTesting(
    bases=(FIXTURE,),
    name="tutorweb.quizdb:Integration",
    )
TUTORWEB_QUIZDB_FUNCTIONAL_TESTING = FunctionalTesting(
    bases=(FIXTURE,),
    name="tutorweb.quizdb:Functional",
    )


class IntegrationTestCase(TestCase):
    layer = TUTORWEB_QUIZDB_INTEGRATION_TESTING

    def tearDown(self):
        """Drop all DB tables and recreate"""
        Session().execute("DROP TABLE allocation")
        Session().execute("DROP TABLE lecture")
        Session().execute("DROP TABLE lectureSetting")
        Session().execute("DROP TABLE question")
        Session().execute("DROP TABLE student")
        Session().execute("DROP TABLE answer")
        Session().execute("DROP TABLE answerSummary")
        Session().execute("DROP TABLE userGeneratedQuestions")
        Session().execute("DROP TABLE userGeneratedAnswer")
        ORMBase.metadata.create_all(Session().bind)


class FunctionalTestCase(ContentFunctionalTestCase):
    layer = TUTORWEB_QUIZDB_FUNCTIONAL_TESTING

    def getJson(self, path, body=None ,user=USER_A_ID, expectedStatus=200):
        """Call view, decode JSON results"""
        browser = self.getBrowser(None, user=user)
        browser.handleErrors = False
        browser.raiseHttpErrors = False
        if body:
            browser.post(path, json.dumps(body))
        else:
            browser.open(path)
        self.assertEqual(browser.headers['content-type'], 'application/json')
        self.assertEqual(
            browser.headers['Status'][0:3],
            str(expectedStatus),
            msg="Status %s didn't match %s: %s" % (
                browser.headers['Status'][0:3],
                str(expectedStatus),
                browser.contents,
            )
        )
        return json.loads(browser.contents)

    def tearDown(self):
        """Drop all DB tables and recreate"""
        Session().execute("DROP TABLE allocation")
        Session().execute("DROP TABLE lecture")
        Session().execute("DROP TABLE lectureSetting")
        Session().execute("DROP TABLE question")
        Session().execute("DROP TABLE student")
        Session().execute("DROP TABLE answer")
        Session().execute("DROP TABLE answerSummary")
        Session().execute("DROP TABLE userGeneratedQuestions")
        Session().execute("DROP TABLE userGeneratedAnswer")
        ORMBase.metadata.create_all(Session().bind)

    def findAnswer(self, qnData, correct=True):
        """Return the first correct/incorrect answer for given question"""
        corrAns = json.loads(base64.b64decode(qnData['answer']))['correct']
        if correct:
            return corrAns[0]
        for i in range(len(qnData['choices'])):
            if i not in corrAns:
                return i
        raise ValueError("No incorrect answer");
