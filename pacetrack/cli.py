# -*- coding: utf-8 -*-

import os
import sys
import subprocess

from boltons.fileutils import mkdir_p
from face import Command, Flag, face_middleware, UsageError
from glom import glom, T

from .log import tlog, LOG_PATH, JSUB_LOG_PATH, enable_debug_log
from .update import DEBUG, get_all_campaign_dirs, load_and_update_campaign, PTCampaign, render_home
from ._version import __version__


def print_version():
    'Print the pacetrack version and exit'
    print('pacetrack version %s' % __version__)


def _build_jsub_update(args_, force, campaign_id):
    name = 'pt_update_' + campaign_id
    jsub_campaign_logs_path = JSUB_LOG_PATH + ('%s/' % campaign_id)

    mkdir_p(jsub_campaign_logs_path)

    jsub_out_path = jsub_campaign_logs_path + campaign_id + '_out.log'
    jsub_err_path = jsub_campaign_logs_path + campaign_id + '_err.log'

    ret = ['jsub', '-mem', '2048m', '-once', '-N', name, '-o', jsub_out_path, '-e', jsub_err_path]

    ret.append(args_.argv[0])  # executable
    ret.append('update')

    if force:
        ret.append('--force')

    ret.append(campaign_id)

    return ret


def _run_jsub_update(args_, force, campaign_id):
    argv = _build_jsub_update(args_, force, campaign_id)

    with tlog.critical('jsub', argv=argv):
        subprocess.check_call(argv)

    return


def update_all(campaign_ids=None, jsub=False, force=False, args_=None):
    "Update all campaigns configured"
    if jsub and not args_:
        raise RuntimeError('jsub requires parsed arguments (args_)')

    campaign_ids = set(campaign_ids or [])
    if campaign_ids:
        known_campaigns = set(get_all_campaign_dirs(abspath=False))
        unknown_campaigns = campaign_ids - known_campaigns
        if unknown_campaigns:
            raise UsageError('got unknown campaign names: %s\nexpected one of: %s'
                             % (', '.join(sorted(unknown_campaigns)),
                                ', '.join(sorted(known_campaigns))))

    for campaign_dir in get_all_campaign_dirs():
        cur_campaign_id = os.path.split(campaign_dir)[1]
        if campaign_ids and cur_campaign_id not in campaign_ids:
            continue
        if jsub:
            _run_jsub_update(args_, force, cur_campaign_id)
            continue

        cur_pt = load_and_update_campaign(campaign_dir, force=force)
    return


def prune(posargs_, dry_run):
    campaign_ids = posargs_
    for campaign_dir in get_all_campaign_dirs():
        if not campaign_ids or os.path.split(campaign_dir)[1] in campaign_ids:
            cur_ptc = PTCampaign.from_path(campaign_dir)
            cur_ptc.prune_by_frequency(dry_run=dry_run)


def update(campaign_ids, args_, jsub=False, force=False):
    "Update one or more campaigns by name"
    return update_all(campaign_ids, force=force, jsub=jsub, args_=args_)


def list_campaigns():
    "List available campaigns"
    print('\n'.join(get_all_campaign_dirs(abspath=False)))


def list_states(posargs_):  # TODO
    "List available state timestamps for a given campaign name"
    pass


def render_all():
    "Render reports for all campaigns using the freshest data already fetched."
    campaign_dirs = get_all_campaign_dirs()
    all_ptcs = []
    for cd in campaign_dirs:
        with tlog.critical('load_campaign_dir', path=cd) as _act:
            ptc = PTCampaign.from_path(cd)
            _act['name'] = ptc.name
        ptc.render()
        all_ptcs.append(ptc)
    render_home(all_ptcs)
    return


def main(argv=None):
    cmd = Command(name='pacetrack', func=None)

    # subcommands
    update_subcmd = Command(update, posargs={'min_count': 1, 'display': 'campaign_id', 'provides': 'campaign_ids'})
    # update_subcmd.add('campaign_name')
    cmd.add(update_subcmd)
    cmd.add(update_all)
    cmd.add(render_all)
    cmd.add(list_campaigns)
    cmd.add(print_version, name='version')
    # cmd.add(prune)  # mostly for testing

    cmd.add('--jsub', parse_as=True, doc='run commands through the WMF Labs job grid (for production use only)')
    cmd.add('--force', parse_as=True, doc='ignore configured fetch frequency and force updates')
    cmd.add('--dry-run', parse_as=True, doc='log actions without performing them (e.g., do not remove files)')

    # flags
    cmd.add('--debug', doc='increase logging level', parse_as=True, missing=DEBUG)

    # middlewares
    cmd.add(mw_cli_log)

    try:
        cmd.run()
    except Exception:
        # TODO: once face is stable, this can become part of the middleware
        if os.getenv('PACETRACK_ENABLE_DEBUG'):
            import pdb;pdb.post_mortem()
        raise


@face_middleware
def mw_cli_log(next_, debug):
    if debug:
        enable_debug_log()
    tlog.critical('start').success('started {0}, logging to {1}', os.getpid(), LOG_PATH)
    with tlog.critical('cli', argv=sys.argv):
        return next_()
