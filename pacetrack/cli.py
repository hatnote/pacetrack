# -*- coding: utf-8 -*-

import os
import sys

from face import Command, Flag, face_middleware

from .update import DEBUG, main as update_main


def main(argv=None):
    try:
        cmd = Command(name='pacetrack', func=None)
    except Exception:
        import pdb;pdb.post_mortem()

    cmd.add(update_main, name='update')
    cmd.add('--debug', missing=DEBUG)

    cmd.run()
