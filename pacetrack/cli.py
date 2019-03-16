# -*- coding: utf-8 -*-

import os
import sys

from face import Command, Flag, face_middleware, BadCommand

from .log import tlog, LOG_PATH
from .update import DEBUG, get_all_campaign_dirs, load_and_update_campaign, PTCampaign


def update_all(campaign_ids=None, force=False):
    "Update all campaigns configured"
    campaign_ids = set(campaign_ids or [])
    if campaign_ids:
        known_campaigns = set(get_all_campaign_dirs(abspath=False))
        unknown_campaigns = campaign_ids - known_campaigns
        if unknown_campaigns:
            raise BadCommand('got unknown campaign names: %s\nexpected one of: %s'
                             % (', '.join(sorted(unknown_campaigns)),
                                ', '.join(sorted(known_campaigns))))

    for campaign_dir in get_all_campaign_dirs():
        if not campaign_ids or os.path.split(campaign_dir)[1] in campaign_ids:
            cur_pt = load_and_update_campaign(campaign_dir, force=force)
    return


def prune(posargs_):
    campaign_ids = posargs_
    for campaign_dir in get_all_campaign_dirs():
        if not campaign_ids or os.path.split(campaign_dir)[1] in campaign_ids:
            cur_ptc = PTCampaign.from_path(campaign_dir)
            cur_ptc.prune_by_frequency()




def update(posargs_, force=False):
    "Update one or more campaigns by name"
    return update_all(campaign_ids=posargs_, force=force)


def list_campaigns():
    "List available campaigns"
    print('\n'.join(get_all_campaign_dirs(abspath=False)))


def main(argv=None):
    cmd = Command(name='pacetrack', func=None)

    # subcommands
    update_subcmd = Command(update, posargs={'min_count': 1, 'display': 'campaign_id'})
    # update_subcmd.add('campaign_name')
    cmd.add(update_subcmd)
    cmd.add(update_all)
    cmd.add(list_campaigns)
    cmd.add(prune)

    cmd.add('--force', parse_as=True, doc='ignore configured fetch frequency and force updates')

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
