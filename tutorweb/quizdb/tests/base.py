import random
import base64
import os
import tempfile
from unittest import TestCase
import json

import transaction
from App.config import getConfiguration
from Acquisition import aq_parent
from zope.lifecycleevent import ObjectModifiedEvent, ObjectCreatedEvent, ObjectRemovedEvent
import zope.event
from zope.testing.loggingsupport import InstalledHandler

from plone.app.testing import IntegrationTesting, FunctionalTesting, login
from Products.CMFCore.utils import getToolByName
from z3c.saconfig import Session
from zope.configuration import xmlconfig

# Nab test case setup from tutorweb.content
from tutorweb.content.tests.base import (
    USER_A_ID,
    USER_B_ID,
    USER_C_ID,
    USER_D_ID,
    MANAGER_ID,
)
from tutorweb.content.tests.base import TestFixture as ContentTestFixture
from tutorweb.content.tests.base import FunctionalTestCase as ContentFunctionalTestCase
from tutorweb.quizdb import ORMBase

class TestFixture(ContentTestFixture):
    def setUpZope(self, app, configurationContext):
        super(TestFixture, self).setUpZope(app, configurationContext)

        # Create some dummy site configuration to use
        config = getConfiguration()
        config.product_config = getattr(config, 'product_config', {})
        config.product_config['tutorweb.quizdb'] = {
            'coin-rpc-host': 'ut-rpchost',
            'coin-rpc-port': '0818118181',
            'coin-rpc-user': 'ut-rpcuser',
            'coin-rpc-pass': 'ut-rpcpass',
            'coin-rpc-walletpass': 'ut-rpcwalletpass',
        }

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


class TestHelpers(object):
    def findAnswer(self, qnData, correct=True):
        """Return the first correct/incorrect answer for given question"""
        corrAns = json.loads(base64.b64decode(qnData['answer']))['correct']
        if correct:
            return corrAns[0]
        for i in range(len(qnData['choices'])):
            if i not in corrAns:
                return i
        raise ValueError("No incorrect answer");

    def createTestLecture(self, qnCount=10, qnOpts=lambda i: {}, lecOpts=lambda i: {}, tutOpts=lambda i: {}, tutorialObj=None):
        portal = self.layer['portal']
        login(portal, MANAGER_ID)

        # Create some content, merging in specified options
        def createContent(parent, defaults, i=random.randint(1000000, 9999999), optsFn=lambda i: {}):
            opts = dict(id=None, title=None)
            opts.update(defaults)
            opts.update(optsFn(i))

            if not opts['id']:
                opts['id'] = "%s-%d" % (dict(
                    tw_department="dept",
                    tw_tutorial="tut",
                    tw_lecture="lec",
                    tw_latexquestion="qn",
                    tw_questiontemplate="tmplqn",
                    )[opts['type_name']], i)
            if not opts['title']:
                opts['title'] = u"Unittest %s %d" % (opts['type_name'], i)

            obj = parent[parent.invokeFactory(**opts)]
            if not hasattr(self, 'tempObjects'):
                self.tempObjects = []
            self.tempObjects.append(obj)
            return obj

        # Create dept/tutorial/lecture
        if not tutorialObj:
            deptObj = createContent(portal, dict(type_name="tw_department"))
            tutorialObj = createContent(deptObj, dict(type_name="tw_tutorial"), optsFn=tutOpts)
        lectureObj = createContent(tutorialObj, dict(type_name="tw_lecture"), optsFn=lecOpts)

        # Create required questions inside
        for i in xrange(qnCount):
            createContent(lectureObj, dict(
                type_name="tw_latexquestion",
                choices=[dict(text="orange", correct=False), dict(text="green", correct=True)],
                finalchoices=[],
            ), i, optsFn=qnOpts)

        self.objectPublish(lectureObj)
        transaction.commit()
        return lectureObj

    def createTestStudent(self, id):
        portal = self.layer['portal']
        login(portal, MANAGER_ID)

        acl_users = getToolByName(portal, 'acl_users')
        mtool = getToolByName(portal, 'portal_membership')
        acl_users.userFolderAddUser(
            id, 'secret'+id[0],
            ['Member'],[]
        )
        mtool.getMemberById(id).setMemberProperties(dict(
            email=id.split('@', 1)[0] + '@example.com',
            accept=True,
        ))

        login(portal, id)
        student = portal.restrictedTraverse('dept1/tut1/lec1/@@quizdb-sync').getCurrentStudent()
        transaction.commit()

        return student

    def notifyCreate(self, obj):
        obj.reindexObject()
        zope.event.notify(ObjectCreatedEvent(obj))

    def notifyModify(self, obj):
        obj.reindexObject()
        zope.event.notify(ObjectModifiedEvent(obj))

    def notifyDelete(self, obj):
        obj.reindexObject()
        obj.aq_parent.reindexObject()
        zope.event.notify(ObjectRemovedEvent(obj))

    def objectPublish(self, obj):
        login(self.layer['portal'], MANAGER_ID)
        workflowTool = getToolByName(self.layer['portal'], 'portal_workflow')

        status = workflowTool.getStatusOf("simple_publication_workflow", obj) or dict()
        if status.get("review_state", None) != "published":
            workflowTool.doActionFor(obj, 'publish')
        self.notifyModify(obj)

    def allocParseAnswerQueue(self, dbLec, student, rawAnswerQueue, settings, **kwargs):
        """Helper that generates alloc for us"""
        from ..allocation.base import Allocation
        from ..sync.answers import parseAnswerQueue

        alloc = Allocation.allocFor(
            student=student,
            dbLec=dbLec,
            urlBase=self.layer['portal'].absolute_url(),
        )
        return parseAnswerQueue(alloc, rawAnswerQueue, settings, **kwargs)

    def allocGetQuestionAllocation(self, dbLec, student, settings, **kwargs):
        """Helper that generates alloc for us"""
        from ..allocation.base import Allocation
        from ..sync.questions import getQuestionAllocation

        alloc = Allocation.allocFor(
            student=student,
            dbLec=dbLec,
            urlBase=self.layer['portal'].absolute_url(),
        )
        if 'targetDifficulty' in kwargs:
            alloc.targetDifficulty=kwargs['targetDifficulty']
        if 'reAllocQuestions' in kwargs:
            alloc.reAllocQuestions=kwargs['reAllocQuestions']
        return getQuestionAllocation(alloc, settings)


class IntegrationTestCase(TestCase, TestHelpers):
    layer = TUTORWEB_QUIZDB_INTEGRATION_TESTING

    def setUp(self):
        super(IntegrationTestCase, self).setUp()

        self.objectPublish(self.layer['portal']['dept1']['tut1']['lec1'])
        self.objectPublish(self.layer['portal']['dept1']['tut1']['lec2'])

    def tearDown(self):
        """Drop all DB tables and recreate"""
        Session().execute("DROP TABLE allocation")
        Session().execute("DROP TABLE lecture")
        Session().execute("DROP TABLE lectureGlobalSetting")
        Session().execute("DROP TABLE lectureStudentSetting")
        Session().execute("DROP TABLE lectureQuestions")
        Session().execute("DROP TABLE question")
        Session().execute("DROP TABLE student")
        Session().execute("DROP TABLE answer")
        Session().execute("DROP TABLE answerSummary")
        Session().execute("DROP TABLE userGeneratedQuestions")
        Session().execute("DROP TABLE userGeneratedAnswer")
        Session().execute("DROP TABLE coinAward")
        ORMBase.metadata.create_all(Session().bind)

    def assertTrue(self, expr, thing=None, msg=None):
        if thing is not None:
            raise ValueError("Did you really mean to use assertTrue?")
        return TestCase.assertTrue(self, expr, msg=msg)

class FunctionalTestCase(ContentFunctionalTestCase, TestHelpers):
    layer = TUTORWEB_QUIZDB_FUNCTIONAL_TESTING

    def setUp(self):
        super(FunctionalTestCase, self).setUp()
        self.loghandlers = dict(
            sqlalchemy=InstalledHandler('sqlalchemy.engine'),
            sync=InstalledHandler('tutorweb.quizdb.browser.sync'),
            syncm=InstalledHandler('tutorweb.quizdb.sync'),
        )

        self.objectPublish(self.layer['portal']['dept1']['tut1']['lec1'])
        self.objectPublish(self.layer['portal']['dept1']['tut1']['lec2'])

    def tearDown(self):
        portal = self.layer['portal']
        login(portal, MANAGER_ID)

        # Remove any temporary Plone objects
        for l in reversed(getattr(self, 'tempObjects', [])):
            del aq_parent(l)[l.id]

        # Drop all DB tables & recreate
        Session().execute("DROP TABLE allocation")
        Session().execute("DROP TABLE lecture")
        Session().execute("DROP TABLE lectureGlobalSetting")
        Session().execute("DROP TABLE lectureStudentSetting")
        Session().execute("DROP TABLE lectureQuestions")
        Session().execute("DROP TABLE question")
        Session().execute("DROP TABLE student")
        Session().execute("DROP TABLE answer")
        Session().execute("DROP TABLE answerSummary")
        Session().execute("DROP TABLE userGeneratedQuestions")
        Session().execute("DROP TABLE userGeneratedAnswer")
        Session().execute("DROP TABLE coinAward")
        ORMBase.metadata.create_all(Session().bind)

        transaction.commit()
        super(FunctionalTestCase, self).tearDown()

    def getJson(self, path, body=None ,user=USER_A_ID, expectedStatus=200):
        """Call view, decode JSON results"""
        browser = self.getBrowser(None, user=user)
        browser.handleErrors = False
        browser.raiseHttpErrors = False
        if isinstance(expectedStatus, list):
            expectedStatuses = [str(x) for x in expectedStatus]
        else:
            expectedStatuses = [str(expectedStatus)]
        if body:
            browser.post(path, json.dumps(body))
        else:
            browser.open(path)
        self.assertEqual(browser.headers['content-type'], 'application/json')
        self.assertTrue(
            browser.headers['Status'][0:3] in expectedStatuses,
            msg="Status %s didn't match %s: %s" % (
                browser.headers['Status'][0:3],
                "/".join(expectedStatuses),
                json.loads(browser.contents),
            )
        )
        return json.loads(browser.contents)

    def assertTrue(self, expr, thing=None, msg=None):
        if thing is not None:
            raise ValueError("Did you really mean to use assertTrue?")
        return TestCase.assertTrue(self, expr, msg=msg)

    def logs(self, name='sqlalchemy'):
        return [x.getMessage() for x in self.loghandlers[name].records]
