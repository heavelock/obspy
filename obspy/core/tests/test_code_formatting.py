import codecs
import fnmatch
import os
import re
import unittest

import obspy
from obspy.core.util.misc import get_untracked_files_from_git
from obspy.core.util.testing import get_all_py_files

try:
    import flake8
except ImportError:  # pragma: no cover
    HAS_FLAKE8_AT_LEAST_VERSION_3 = False
else:
    if int(flake8.__version__.split(".")[0]) >= 3:
        HAS_FLAKE8_AT_LEAST_VERSION_3 = True
    else:  # pragma: no cover
        HAS_FLAKE8_AT_LEAST_VERSION_3 = False


# List of flake8 error codes to ignore. Keep it as small as possible - there
# usually is little reason to fight flake8.
# NOTE: Keep consistent between..
#   - obspy/core/tests/test_code_formatting.py FLAKE8_IGNORE_CODES
#   - .flake8 --ignore
FLAKE8_IGNORE_CODES = [
    'E121',
    'E123',
    'E126',
    'E133',
    'E24',
    'E226',
    'E402',
    'E704',
    'W503',
    'W504',
]
FLAKE8_EXCLUDE_FILES = [
    "*/__init__.py",
]


_pattern = re.compile(r"^\d+\.\d+\.\d+$")
CLEAN_VERSION_NUMBER = bool(_pattern.match(obspy.__version__))


def _match_exceptions(filename, exceptions):
    for pattern in exceptions:
        if fnmatch.fnmatch(filename, pattern):
            return True
    return False


class CodeFormattingTestCase(unittest.TestCase):
    """
    Test codebase for compliance with the flake8 tool.
    """
    @unittest.skipIf(CLEAN_VERSION_NUMBER,
                     "No code formatting tests for release builds")
    @unittest.skipIf(not HAS_FLAKE8_AT_LEAST_VERSION_3,
                     "Formatting tests require at least flake8 3.0.")
    @unittest.skipIf('OBSPY_NO_FLAKE8' in os.environ, 'flake8 check disabled')
    def test_flake8(self):
        """
        Test codebase for compliance with the flake8 tool.
        """
        # Import the legacy API as flake8 3.0 currently has not official
        # public API - this has to be changed at some point.
        from flake8.api import legacy as flake8
        # --hang-closing allows valid indented closing brackets, see
        # https://github.com/PyCQA/pycodestyle/issues/103#issuecomment-17366719
        style_guide = flake8.get_style_guide(
            ignore=FLAKE8_IGNORE_CODES, hang_closing=True)

        untracked_files = get_untracked_files_from_git() or []
        files = []
        for filename in get_all_py_files():
            if filename in untracked_files:
                continue
            for pattern in FLAKE8_EXCLUDE_FILES:
                if fnmatch.fnmatch(filename, pattern):
                    break
            else:
                files.append(filename)
        report = style_guide.check_files(files)

        # Make sure no error occurred.
        assert report.total_errors == 0

    @unittest.skipIf(CLEAN_VERSION_NUMBER,
                     "No code formatting tests for release builds")
    def test_use_obspy_deprecation_warning(self):
        """
        Tests that ObsPyDeprecationWarning is used rather than the usual
        DeprecationWarning when using `warnings.warn()`
        (because the latter is not shown by Python by default anymore).
        """
        msg = ("File '%s' seems to use DeprecationWarning instead of "
               "obspy.core.util.deprecation_helpers.ObsPyDeprecationWarning:"
               "\n\n%s")
        pattern = r'warn\([^)]*?([\w]*?)DeprecationWarning[^)]*\)'

        failures = []
        for filename in get_all_py_files():
            with codecs.open(filename, "r", encoding="utf-8") as fh:
                content = fh.read()

            for match in re.finditer(pattern, content):
                if match.group(1) != 'ObsPy':
                    failures.append(msg % (filename, match.group(0)))

        self.assertEqual(len(failures), 0, "\n" + "\n".join(failures))


class MatplotlibBackendUsageTestCase(unittest.TestCase):
    patterns = (
        r" *from pylab import",
        r" *from pylab\..*? import",
        r" *import pylab",
        r" *from matplotlib import (.*?, *)*(pyplot|backends)",
        r" *import matplotlib\.(pyplot|backends)")

    def forbidden_match(self, line):
        for pattern in self.patterns:
            if re.match(pattern, line):
                return pattern
        return False

    def test_no_pyplot_regex(self):
        """
        Tests that the regex patterns to match forbidden lines works
        as expected.
        """
        positives = (
            'from pylab import something',
            '    from pylab import something',
            'from pylab.something import something',
            'import pylab',
            '    import pylab',
            'from matplotlib import pyplot',
            '  from matplotlib import pyplot',
            'from matplotlib import backends',
            '  from matplotlib import backends',
            'from matplotlib import dates, backends',
            'import matplotlib.pyplot as plt',
            'import matplotlib.pyplot',
            'import matplotlib.backends',
            '   import matplotlib.backends',
            )
        negatives = (
            '#from pylab import something',
            '# from pylab import something',
            '#    from pylab import something',
            'import os  # from pylab import something',
            '#import pylab',
            '#    import pylab',
            '  #from matplotlib import pyplot',
            '#  from matplotlib import pyplot',
            '#from matplotlib import backends',
            '#  from matplotlib import backends',
            '#from matplotlib import dates, backends',
            ' # import matplotlib.pyplot as plt',
            'import os   # import matplotlib.pyplot',
            ' # import matplotlib.backends',
            'from cryptography.hazmat.backends import default_backend',
            )
        for line in positives:
            self.assertTrue(
                self.forbidden_match(line),
                msg="Line '{}' should be detected as forbidden but it was "
                    "not.".format(line))
        for line in negatives:
            pattern = self.forbidden_match(line)
            self.assertFalse(
                pattern,
                msg="Line '{}' should not be detected as forbidden but it "
                    "was, by pattern '{}'.".format(line, pattern))

    @unittest.skipIf(CLEAN_VERSION_NUMBER,
                     "No code formatting tests for release builds")
    def test_no_pyplot_import_in_any_file(self):
        """
        Tests that no Python file spoils matplotlib backend switching by
        importing e.g. `matplotlib.pyplot` (not enclosed in a def/class
        statement).
        """
        msg = ("File '{}' (line {})\nmatches a forbidden matplotlib import "
               "statement outside of class/def statements\n(breaking "
               "matplotlib backend switching on some systems):\n    '{}'")
        exceptions = [
            os.path.join('io', 'css', 'contrib', 'css28fix.py'),
            os.path.join('*', 'tests', '*'),
            os.path.join('*', '*', 'tests', '*'),
        ]
        exceptions = [os.path.join("*", "obspy", i) for i in exceptions]

        failures = []
        for filename in get_all_py_files():
            if _match_exceptions(filename, exceptions):
                continue
            line_number = 1
            in_docstring = False
            with codecs.open(filename, "r", encoding="utf-8") as fh:
                line = fh.readline()
                while line:
                    # detect start/end of docstring
                    if re.match(r"['\"]{3}", line):
                        in_docstring = not in_docstring
                    # skip if inside docstring
                    if not in_docstring:
                        # stop searching at first unindented class/def
                        if re.match(r"(class)|(def) ", line):
                            break
                        if self.forbidden_match(line) is not False:
                            failures.append(msg.format(
                                filename, line_number, line.rstrip()))
                    line = fh.readline()
                    line_number += 1
        self.assertEqual(len(failures), 0, "\n" + "\n\n".join(failures))


def suite():
    suite = unittest.TestSuite()
    suite.addTest(unittest.makeSuite(CodeFormattingTestCase, 'test'))
    suite.addTest(unittest.makeSuite(MatplotlibBackendUsageTestCase, 'test'))
    return suite


if __name__ == '__main__':
    unittest.main(defaultTest='suite')
