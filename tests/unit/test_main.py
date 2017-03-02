# Copyright 2017: Godaddy Inc.

import testtools


class TestCase(testtools.TestCase):

    def test_noop(self):
        self.assertEqual(4, 2 + 2)