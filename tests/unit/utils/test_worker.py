# Copyright 2017: Godaddy Inc.

import time

from netmet.utils import worker
from tests.unit import test


class LonelyWorkerTestCase(test.TestCase):

    def tearDown(self):
        super(LonelyWorkerTestCase, self).tearDown()
        worker.LonelyWorker.destroy()

    def test_get_not_initalized(self):
        self.assertIsNone(worker.LonelyWorker.get())

    def test_create_and_get(self):
        worker.LonelyWorker.create()
        self.assertIsInstance(worker.LonelyWorker.get(), worker.LonelyWorker)

    def test_singletone(self):
        worker.LonelyWorker.create()
        first = worker.LonelyWorker.get()
        worker.LonelyWorker.create()
        second = worker.LonelyWorker.get()
        self.assertIs(first, second)

    def test_force_update(self):
        # check it doesn't fail if not inited
        worker.LonelyWorker.force_update()

        worker.LonelyWorker.create()
        worker.LonelyWorker.force_update()
        self.assertTrue(worker.LonelyWorker.get()._force_update)

    def test_destroy(self):
        worker.LonelyWorker.create()
        worker.LonelyWorker.destroy()
        self.assertIsNone(worker.LonelyWorker.get())

    def test_periodic_worker(self):

        class LonelyWorkerInt(worker.LonelyWorker):
            _period = 0.1

            def _job(self):
                if not getattr(self, "counter", False):
                    self.counter = 1
                else:
                    self.counter += 1
                return True

        class AfterJob(object):

            def __init__(self):
                self.counter = 0

            def job(self):
                self.counter += 1

        try:
            after_job = AfterJob()
            LonelyWorkerInt.create(callback_after_job=after_job.job)
            time.sleep(0.01)
            self.assertEqual(1, LonelyWorkerInt.get().counter)
            self.assertEqual(1, after_job.counter)
            time.sleep(0.23)
            self.assertEqual(3, LonelyWorkerInt.get().counter)
            self.assertEqual(3, after_job.counter)
        finally:
            LonelyWorkerInt.destroy()
