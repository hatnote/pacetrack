# -*- coding: utf-8 -*-

import os
import sys

from face import Command, Flag, face_middleware, BadCommand

from .log import tlog, LOG_PATH
from .update import DEBUG, get_all_campaign_dirs, load_and_update_campaign


def update_all(campaign_names=None):
    "Update all campaigns configured"
    campaign_names = set(campaign_names or [])
    if campaign_names:
        known_campaigns = set(get_all_campaign_dirs(abspath=False))
        unknown_campaigns = campaign_names - known_campaigns
        if unknown_campaigns:
            raise BadCommand('got unknown campaign names: %s\nexpected one of: %s'
                             % (', '.join(sorted(unknown_campaigns)),
                                ', '.join(sorted(known_campaigns))))
    for campaign_dir in get_all_campaign_dirs():
        if not campaign_names or os.path.split(campaign_dir)[1] in campaign_names:
            cur_pt = load_and_update_campaign(campaign_dir)
    return


def update(posargs_):
    "Update one or more campaigns by name"
    return update_all(campaign_names=posargs_)


def list_campaigns():
    "List available campaigns"
    print('\n'.join(get_all_campaign_dirs(abspath=False)))


def main(argv=None):
    try:
        cmd = Command(name='pacetrack', func=None)
    except Exception:
        import pdb;pdb.post_mortem()

    # subcommands
    update_subcmd = Command(update, posargs={'min_count': 1, 'display': 'campaign_name'})
    # update_subcmd.add('campaign_name')
    cmd.add(update_subcmd)
    cmd.add(update_all)
    cmd.add(list_campaigns)

    # flags
    cmd.add('--debug', missing=DEBUG)

    # middlewares
    cmd.add(mw_cli_log)

    cmd.run()


@face_middleware
def mw_cli_log(next_):
    tlog.critical('start').success('started {0}, logging to {1}', os.getpid(), LOG_PATH)
    with tlog.critical('cli', argv=sys.argv):
        return next_()
