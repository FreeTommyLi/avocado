# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.
#
# See LICENSE for more details.
#
# Copyright: Red Hat Inc. 2014
# Author: Cleber Rosa <cleber@redhat.com>

"""Journal Plugin"""

import os
import sqlite3
import datetime

from avocado.plugins import plugin
from avocado.result import TestResult


JOURNAL_FILENAME = ".journal.sqlite"

SCHEMA = {'job_info': 'CREATE TABLE job_info (unique_id TEXT UNIQUE)',
          'test_journal': ("CREATE TABLE test_journal ("
                           "tag TEXT, "
                           "time TEXT, "
                           "action TEXT, "
                           "status TEXT, "
                           "flushed BOOLEAN DEFAULT 0)")}


class TestResultJournal(TestResult):

    """
    Test Result Journal class.

    This class keeps a log of the test updates: started running, finished, etc.
    This information can be forwarded live to an avocado server and provide
    feedback to users from a central place.
    """

    command_line_arg_name = '--journal'

    def __init__(self, stream=None, args=None):
        """
        Creates an instance of TestResultJournal.

        :param stream: an instance of :class:`avocado.core.output.View`.
        :param args: an instance of :class:`argparse.Namespace`.
        """
        TestResult.__init__(self, stream, args)
        self.journal_initialized = False

    def _init_journal(self, logdir):
        self.journal_path = os.path.join(logdir, JOURNAL_FILENAME)
        self.journal = sqlite3.connect(self.journal_path)
        self.journal_cursor = self.journal.cursor()
        for table in SCHEMA:
            res = self.journal_cursor.execute("PRAGMA table_info('%s')" % table)
            if res.fetchone() is None:
                self.journal_cursor.execute(SCHEMA[table])
        self.journal.commit()

    def lazy_init_journal(self, state):
        # lazy init because we need the toplevel logdir for the job
        if not self.journal_initialized:
            self._init_journal(state['job_logdir'])
            self._record_job_info(state)
            self.journal_initialized = True

    def _shutdown_journal(self):
        self.journal.close()

    def _record_job_info(self, state):
        res = self.journal_cursor.execute("SELECT unique_id FROM job_info")
        if res.fetchone() is None:
            sql = "INSERT INTO job_info (unique_id) VALUES (?)"
            self.journal_cursor.execute(sql, (state['job_unique_id'], ))
            self.journal.commit()

    def _record_status(self, state, action):
        sql = "INSERT INTO test_journal (tag, time, action, status) VALUES (?, ?, ?, ?)"

        # This shouldn't be required
        if action == "ENDED":
            status = state['status']
        else:
            status = None

        self.journal_cursor.execute(sql,
                                    (state['tagged_name'],
                                     datetime.datetime(1, 1, 1).now().isoformat(),
                                     action,
                                     status))
        self.journal.commit()

    def start_test(self, state):
        self.lazy_init_journal(state)
        TestResult.start_test(self, state)
        self._record_status(state, "STARTED")

    def end_test(self, state):
        self.lazy_init_journal(state)
        TestResult.end_test(self, state)
        self._record_status(state, "ENDED")

    def end_tests(self):
        self._shutdown_journal()


class Journal(plugin.Plugin):

    """
    Test journal
    """

    name = 'journal'
    enabled = True

    def configure(self, parser):
        self.parser = parser
        self.parser.runner.add_argument(
            '--journal', action='store_true',
            help='Records test status changes')
        self.configured = True

    def activate(self, args):
        try:
            if args.journal:
                self.parser.application.set_defaults(journal_result=TestResultJournal)
        except AttributeError:
            pass
