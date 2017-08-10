from tutorweb.quizdb import db
from tutorweb.quizdb.sync.student import _chooseSettingValue, getStudentSettings
from tutorweb.quizdb.utils import getDbStudent, getDbLecture

from .base import IntegrationTestCase

LOTS_OF_TESTS = 1000

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
            out += float(csv(value=40, shape=2))
        out = out / LOTS_OF_TESTS
        self.assertTrue(abs(out - 40) < 2)

    def test_getStudentSettings(self):
        # Create lecture with lots of different forms of setting
        lecObj = self.createTestLecture(qnCount=5, lecOpts=lambda i: dict(settings=[
            dict(key="ut_static", value="0.9"),
            dict(key="ut_uniform:max", value="100"),
            dict(key="ut_uniform2:max", value="100"),
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
        self.assertTrue(float(settings1['andrew']['ut_uniform2']) < 100)
        self.assertTrue(float(settings1['betty']['ut_uniform2']) < 100)
        self.assertTrue(float(settings1['clara']['ut_uniform2']) < 100)
        self.assertTrue(settings1['andrew']['ut_uniform2'] != settings1['betty']['ut_uniform2'] or settings1['betty']['ut_uniform'] != settings1['clara']['ut_uniform2'])

        # Change static setting
        lecObj.settings = [
            dict(key="ut_static", value="0.4"),
            dict(key="ut_uniform:max", value="100"),
            dict(key="ut_uniform2:max", value="100"),
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
            dict(key="ut_uniform2:max", value="100"),
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
