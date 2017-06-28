# Copyright 2017: GoDaddy Inc.

import time

from netmet.utils import asyncer
from tests.unit import test


class AsyncerTestCase(test.TestCase):

    def tearDown(self):
        asyncer.die()
        super(AsyncerTestCase, self).tearDown()

    def test_asyncer_regular_call(self):

        @asyncer.asyncme
        def method(a, b=2):
            return a + b

        self.assertEqual(4, method(2))
        self.assertEqual(7, method(3, b=4))
        self.assertEqual([], asyncer._THREADS)

    def test_asyncer_async_call(self):
        s = []

        @asyncer.asyncme
        def method(a):
            time.sleep(a)
            s.append(a)

        method.async_call(0.2)
        method.async_call(0.1)

        self.assertEqual(2, len(asyncer._THREADS))
        asyncer.die()
        self.assertEqual(0, len(asyncer._THREADS))
        self.assertEqual([0.1, 0.2], s)

    def test_die_empty(self):
        asyncer.die()