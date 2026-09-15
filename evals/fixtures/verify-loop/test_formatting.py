import unittest

from formatting import display_title


class FormattingTests(unittest.TestCase):
    def test_plain_title(self):
        self.assertEqual(display_title("Read"), "Read")


if __name__ == "__main__":
    unittest.main()
