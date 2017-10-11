from plone.app.testing import login

from tutorweb.quizdb import db
from tutorweb.quizdb.sync.student import _chooseSettingValue, getStudentSettings
from tutorweb.quizdb.utils import getDbStudent, getDbLecture

from tutorweb.content.tests.base import setRelations
from .base import IntegrationTestCase
from .base import MANAGER_ID, USER_A_ID, USER_B_ID, USER_C_ID

LOTS_OF_TESTS = 100000

class SyncStudentIntegration(IntegrationTestCase):
    def test_chooseSettingValue(self):
        """Make sure we can generate all the different types of values"""
        def csv(**kwargs):
            return _chooseSettingValue(db.LectureGlobalSetting(**kwargs))

        # Fixed values return None, not the value in question
        self.assertEqual(csv(value=4), None)

        # Random values are all within bounds
        for x in xrange(LOTS_OF_TESTS):
            out = float(csv(max=100))
            self.assertTrue(out >= 0)
            self.assertTrue(out < 100)
        for x in xrange(LOTS_OF_TESTS):
            out = float(csv(min=90, max=100))
            self.assertTrue(out >= 90)
            self.assertTrue(out < 100)

        # Gamma values hit the mean
        out = 0
        for x in xrange(LOTS_OF_TESTS):
            out += float(csv(value=1000000, shape=2))
        out = out / LOTS_OF_TESTS
        self.assertTrue(abs(out - 2000000) < 5000)

        # String values come out unaltered, but can't be randomly chosen
        self.assertEqual(csv(key="iaa_mode", value="fun-size"), None)
        with self.assertRaisesRegexp(ValueError, 'iaa_mode'):
            csv(key="iaa_mode", value="fun-size", shape=2)
        with self.assertRaisesRegexp(ValueError, 'iaa_mode'):
            csv(key="iaa_mode", value="fun-size", max=4)

        # Integer settings get rounded, don't have "3.0" at end
        for x in xrange(LOTS_OF_TESTS):
            self.assertIn(csv(key="grade_nmin", max=9), '0 1 2 3 4 5 6 7 8 9'.split())

    def test_getStudentSettings(self):
        # Create lecture with lots of different forms of setting
        lecObj = self.createTestLecture(qnCount=5, lecOpts=lambda i: dict(settings=[
            dict(key="ut_static", value="0.9"),
            dict(key="ut_uniform:max", value="100"),
            dict(key="ut_uniform2:max", value="0.01"),
        ]))
        self.objectPublish(lecObj)
        dbLec = getDbLecture('/'.join(lecObj.getPhysicalPath()))

        # Get settings for 3 students
        settings1 = {}
        for u in ['andrew', 'betty', 'clara']:
            settings1[u] = getStudentSettings(dbLec, getDbStudent(u))

        # Static settings1 are the same
        self.assertEqual(settings1['andrew']['ut_static'], "0.9")
        self.assertEqual(settings1['betty']['ut_static'], "0.9")
        self.assertEqual(settings1['clara']['ut_static'], "0.9")

        # Random settings1 meet requirements
        self.assertTrue(float(settings1['andrew']['ut_uniform']) < 100)
        self.assertTrue(float(settings1['betty']['ut_uniform']) < 100)
        self.assertTrue(float(settings1['clara']['ut_uniform']) < 100)
        self.assertTrue(settings1['andrew']['ut_uniform'] != settings1['betty']['ut_uniform'] or settings1['betty']['ut_uniform'] != settings1['clara']['ut_uniform'])

        # Other random settings1 meet requirements
        self.assertTrue(float(settings1['andrew']['ut_uniform2']) < 0.01)
        self.assertTrue(float(settings1['betty']['ut_uniform2']) < 0.01)
        self.assertTrue(float(settings1['clara']['ut_uniform2']) < 0.01)
        self.assertTrue(settings1['andrew']['ut_uniform2'] != settings1['betty']['ut_uniform2'] or settings1['betty']['ut_uniform'] != settings1['clara']['ut_uniform2'])

        # Change static setting
        lecObj.settings = [
            dict(key="ut_static", value="0.4"),
            dict(key="ut_uniform:max", value="100"),
            dict(key="ut_uniform2:max", value="0.01"),
        ]
        self.notifyModify(lecObj)

        # Values updated, random values still the same
        settings2 = {}
        for u in ['andrew', 'betty', 'clara']:
            settings2[u] = getStudentSettings(dbLec, getDbStudent(u))
        self.assertEqual(settings2['andrew']['ut_static'], "0.4")
        self.assertEqual(settings2['betty']['ut_static'], "0.4")
        self.assertEqual(settings2['clara']['ut_static'], "0.4")
        self.assertEqual(settings2['andrew']['ut_uniform'], settings1['andrew']['ut_uniform'])
        self.assertEqual(settings2['betty']['ut_uniform'], settings1['betty']['ut_uniform'])
        self.assertEqual(settings2['clara']['ut_uniform'], settings1['clara']['ut_uniform'])
        self.assertEqual(settings2['andrew']['ut_uniform2'], settings1['andrew']['ut_uniform2'])
        self.assertEqual(settings2['betty']['ut_uniform2'], settings1['betty']['ut_uniform2'])
        self.assertEqual(settings2['clara']['ut_uniform2'], settings1['clara']['ut_uniform2'])

        # Change uniform random setting with new bounds
        lecObj.settings = [
            dict(key="ut_static", value="0.4"),
            dict(key="ut_uniform:min", value="99"),
            dict(key="ut_uniform:max", value="100"),
            dict(key="ut_uniform2:max", value="0.01"),
        ]
        self.notifyModify(lecObj)

        # Values updated, given new random values meeting criteria
        settings3 = {}
        for u in ['andrew', 'betty', 'clara']:
            settings3[u] = getStudentSettings(dbLec, getDbStudent(u))
        self.assertEqual(settings3['andrew']['ut_static'], "0.4")
        self.assertEqual(settings3['betty']['ut_static'], "0.4")
        self.assertEqual(settings3['clara']['ut_static'], "0.4")
        self.assertNotEqual(settings3['andrew']['ut_uniform'], settings1['andrew']['ut_uniform'])
        self.assertNotEqual(settings3['betty']['ut_uniform'], settings1['betty']['ut_uniform'])
        self.assertNotEqual(settings3['clara']['ut_uniform'], settings1['clara']['ut_uniform'])
        self.assertTrue(float(settings3['andrew']['ut_uniform']) < 100)
        self.assertTrue(float(settings3['betty']['ut_uniform']) < 100)
        self.assertTrue(float(settings3['clara']['ut_uniform']) < 100)
        self.assertTrue(float(settings3['andrew']['ut_uniform']) >= 99)
        self.assertTrue(float(settings3['betty']['ut_uniform']) >= 99)
        self.assertTrue(float(settings3['clara']['ut_uniform']) >= 99)

        # Other random settings still the same
        self.assertEqual(settings3['andrew']['ut_uniform2'], settings1['andrew']['ut_uniform2'])
        self.assertEqual(settings3['betty']['ut_uniform2'], settings1['betty']['ut_uniform2'])
        self.assertEqual(settings3['clara']['ut_uniform2'], settings1['clara']['ut_uniform2'])

    def test_getStudentSettingsVariants(self):
        # Create lecture that uses settings variants
        lecObj = self.createTestLecture(qnCount=5, lecOpts=lambda i: dict(settings=[
            dict(key="ut_static", value="0.9"),
            dict(key="ut_static:registered", value="1.9"),
            dict(key="ut_uniform:max", value="10"),
            dict(key="ut_uniform:registered:min", value="100"),
            dict(key="ut_uniform:registered:max", value="110"),
        ]))
        self.objectPublish(lecObj)
        dbLec = getDbLecture('/'.join(lecObj.getPhysicalPath()))

        # Add it to a class with A in it
        portal = self.layer['portal']
        login(portal, MANAGER_ID)
        classObj = portal['schools-and-classes'][portal['schools-and-classes'].invokeFactory(
            type_name="tw_class",
            id="hard_knocks",
            title="Unittest Hard Knocks class",
            lectures=[lecObj],
            students=[USER_A_ID],
        )]
        setRelations(classObj, 'lectures', [lecObj])
        self.notifyModify(classObj)
        import transaction ; transaction.commit()

        # Get settings for A&B students
        settings = [getStudentSettings(dbLec, getDbStudent(u)) for u in [USER_A_ID, USER_B_ID]]
        self.assertEqual(
            [s['ut_static'] for s in settings],
            [u'1.9', u'0.9'],
        )
        self.assertEqual(
            [float(s['ut_uniform']) > 10 for s in settings],
            [True, False],
        )

        # Add B&C to the class
        classObj.students = [USER_A_ID, USER_B_ID, USER_C_ID]
        self.notifyModify(classObj)

        # Get settings for all students
        settings = [getStudentSettings(dbLec, getDbStudent(u)) for u in [USER_A_ID, USER_B_ID, USER_C_ID]]
        self.assertEqual(
            [s['ut_static'] for s in settings],
            [u'1.9', u'1.9', u'1.9'], # NB: All part of a class now
        )
        self.assertEqual(
            [float(s['ut_uniform']) > 10 for s in settings],
            [True, False, True], # NB: B does not get a new value, since we chose one last time round and lecture version has not bumped
        )

        # Remove class
        portal['schools-and-classes'].manage_delObjects([classObj.id])
        portal['schools-and-classes'].reindexObject()
        self.notifyDelete(classObj)

        # Get settings for all students
        settings = [getStudentSettings(dbLec, getDbStudent(u)) for u in [USER_A_ID, USER_B_ID, USER_C_ID]]
        self.assertEqual(
            [s['ut_static'] for s in settings],
            [u'0.9', u'0.9', u'0.9'],  # static values update
        )
        self.assertEqual(
            [float(s['ut_uniform']) > 10 for s in settings],
            [True, False, True],  # NB: Random values are kept again.
        )
