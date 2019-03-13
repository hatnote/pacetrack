# -*- coding: utf-8 -*-

import os
import sys

from face import Command, Flag, face_middleware

from .log import tlog
from .update import DEBUG, update_all, list_campaigns


def main(argv=None):
    try:
        cmd = Command(name='pacetrack', func=None)
    except Exception:
        import pdb;pdb.post_mortem()

    # subcommands
    cmd.add(update_all)
    cmd.add(list_campaigns)

    # flags
    cmd.add('--debug', missing=DEBUG)

    # middlewares
    cmd.add(mw_cli_log)

    cmd.run()


@face_middleware
def mw_cli_log(next_):
    tlog.critical('start').success('started {0}', os.getpid())
    with tlog.critical('cli', argv=sys.argv):
        return next_()
