#!/usr/bin/env python3.12

import unittest
import logging
import re
import argparse

import os
import sys

from enum import Enum, auto
from shutil import copy

# Monkey-patch the unittest library so that it doesn't
# remove tests from the test suite after running them
unittest.BaseTestSuite._cleanup = False

logging.basicConfig(
    level=logging.DEBUG,
    format="[ %(filename)-34s ]:%(lineno)-3d  [%(levelname)4s]  %(message)s"
)

class GraderRunOptions(Enum):
    RUN_BITRATE_ADAPTATION_UNIT_TESTS = auto()
    RUN_NAMESERVER_UNIT_TESTS = auto()
    RUN_INTEGRATION_TESTS = auto()
    RUN_PART_A = auto()
    RUN_PART_B = auto()
    RUN_ALL_TESTS = auto()

class Grader:

    TESTS_DIRECTORY = "./tests"
    RESULTS_FILE_NAME = "test_results.txt"
    POINTS_PATTERN = re.compile(r"@points:\s*(\d+)")

    def __init__(self):
        self.testResultsFile = open(self.RESULTS_FILE_NAME, "w")
        self.testLoader = unittest.TestLoader()
        self.testRunner = unittest.TextTestRunner(stream=self.testResultsFile, verbosity=2, durations=True)

    def __del__(self):
        self.testResultsFile.close()

    def loadTests(self):
        unitTestSuite = self.testLoader.discover(start_dir=self.TESTS_DIRECTORY, pattern="Test*.py")
        integrationTestSuite = self.testLoader.discover(start_dir=self.TESTS_DIRECTORY, pattern="Integration*.py")
        def collectTests(testSuite):
            result = []
            def collectRecursive(suite):
                nonlocal result
                for test in suite:
                    if isinstance(test, unittest.TestSuite):
                        collectRecursive(test)
                    else:
                        result.append(test)
            collectRecursive(testSuite)
            return result
        self.allUnitTests = collectTests(unitTestSuite)
        self.allIntegrationTests = collectTests(integrationTestSuite)

    def runTests(self, runMode):
        self.selectedUnitTests = unittest.TestSuite()
        self.selectedIntegrationTests = unittest.TestSuite()
        match runMode:
            case GraderRunOptions.RUN_BITRATE_ADAPTATION_UNIT_TESTS | GraderRunOptions.RUN_PART_A:
                # Select bitrate adaptation unit tests
                self.selectedUnitTests.addTests(
                    test for test in self.allUnitTests if test.__class__.__name__.startswith("TestBitrateAdaptation")
                )
            case GraderRunOptions.RUN_NAMESERVER_UNIT_TESTS:
                # Select nameserver unit tests
                self.selectedUnitTests.addTests(
                    test for test in self.allUnitTests if test.__class__.__name__.startswith("TestNameServer")
                )
            case GraderRunOptions.RUN_INTEGRATION_TESTS:
                # Select integration tests
                self.selectedIntegrationTests.addTests(self.allIntegrationTests)
            case GraderRunOptions.RUN_PART_B:
                # Select nameserver unit tests + integration tests
                self.selectedUnitTests.addTests(
                    test for test in self.allUnitTests if test.__class__.__name__.startswith("TestNameServer")
                )
                self.selectedIntegrationTests.addTests(self.allIntegrationTests)
            case GraderRunOptions.RUN_ALL_TESTS:
                # Select unit and integration tests
                self.selectedUnitTests.addTests(self.allUnitTests)
                self.selectedIntegrationTests.addTests(self.allIntegrationTests)
        # Run selected tests
        self.unitTestsResults = self.testRunner.run(self.selectedUnitTests)
        self.integrationTestsResults = self.testRunner.run(self.selectedIntegrationTests)

    def extractTestPointsValue(self, test):
        match = self.POINTS_PATTERN.search(test._testMethodDoc)
        if not match:
            raise RuntimeError
        return int(match.group(1))

    def grade(self, testSuite, testResults):
        totalPoints = 0
        awardedPoints = 0
        failedTests = [test for test, _ in testResults.failures + testResults.errors]
        def gradeRecursive(suite):
            nonlocal totalPoints, awardedPoints
            for test in suite:
                if isinstance(test, unittest.TestSuite):
                    gradeRecursive(test)
                else:
                    testName = f"{test.__class__.__name__}.{test._testMethodName}"
                    pointsWorth = self.extractTestPointsValue(test)
                    totalPoints += pointsWorth
                    print(f"{testName:60}", end="")
                    if test not in failedTests:
                        awardedPoints += pointsWorth
                        print(f"SUCCESS (+{pointsWorth} points)")
                    else:
                        print("FAILED!")
        gradeRecursive(testSuite)
        return awardedPoints, totalPoints

    def printResults(self):

        print()
        print("-----------------")
        print("GRADING REPORT:")
        print("-----------------")
        print()
        if self.selectedUnitTests.countTestCases() > 0:
            print("Unit tests:")
            unitAwarded, unitTotal = self.grade(self.selectedUnitTests, self.unitTestsResults)
            print()
        if self.selectedIntegrationTests.countTestCases() > 0:
            print("Integration tests:")
            integrationAwarded, integrationTotal = self.grade(self.selectedIntegrationTests, self.integrationTestsResults)
            print()
        print("-----------------")
        print("SUMMARY REPORT:")
        print("-----------------")
        if self.selectedUnitTests.countTestCases() > 0:
            print(f"Unit tests: [{unitAwarded}/{unitTotal}]")
        if self.selectedIntegrationTests.countTestCases() > 0:
            print(f"Integration tests: [{integrationAwarded}/{integrationTotal}]")
        print()

if __name__ == "__main__":

    parser = argparse.ArgumentParser(description="Assignment 2 grader")
    group = parser.add_mutually_exclusive_group(required=False)
    group.add_argument("--all", action="store_true", help="run all tests (default)")
    group.add_argument("--miproxy", action="store_true", help="run only the bitrate adaptation unit tests")
    group.add_argument("--nameserver", action="store_true", help="run only the nameserver unit tests")
    group.add_argument("--integration", action="store_true", help="run only the integration tests")
    group.add_argument("--partA", action="store_true", help="run the tests for part A grading (bitrate adaptation unit tests) [same as --miproxy]")
    group.add_argument("--partB", action="store_true", help="run the tests for part B grading (nameserver unit tests + integration tests)")

    args = parser.parse_args()

    if not os.path.exists("./webserver.py"):
        print("Invoke grader.py from within the grader directory!")
        sys.exit(1)

    if not os.path.exists("../miProxy/miProxy"):
        print("Compile miProxy before testing!")
        sys.exit(1)

    if not os.path.exists("../nameserver/nameserver"):
        print("Compile nameserver before testing!")
        sys.exit(1)

    # Get the student's solutions
    copy("../miProxy/miProxy", "./miProxy")
    copy("../nameserver/nameserver", "./nameserver")

    # Grade the solutions
    grader = Grader()
    grader.loadTests()
    grader.runTests(GraderRunOptions.RUN_BITRATE_ADAPTATION_UNIT_TESTS if args.miproxy \
        else GraderRunOptions.RUN_NAMESERVER_UNIT_TESTS if args.nameserver \
        else GraderRunOptions.RUN_INTEGRATION_TESTS if args.integration \
        else GraderRunOptions.RUN_PART_A if args.partA \
        else GraderRunOptions.RUN_PART_B if args.partB \
        else GraderRunOptions.RUN_ALL_TESTS
    )
    grader.printResults()
