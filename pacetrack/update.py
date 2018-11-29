# -*- coding: utf-8 -*-
"""
  Pacetrack
  ~~~~~~~~~

  Update script to load data for tracked wikiproject campaigns

"""
import os
import sys
import json
import uuid
import traceback
from time import strftime
from pipes import quote as shell_quote
from argparse import ArgumentParser

from boltons.fileutils import atomic_save

from log import tlog, set_debug

CUR_PATH = os.path.dirname(os.path.abspath(__file__))
PROJECT_PATH = os.path.dirname(CUR_PATH)
CAMPAIGNS_PATH = PROJECT_PATH + '/campaigns/'

RUN_UUID = uuid.uuid4()

DEBUG = False


def to_unicode(obj):
    try:
        return unicode(obj)
    except UnicodeDecodeError:
        return unicode(obj, encoding='utf8')



class PaceTracker(object):
    pass



def get_argparser():
    desc = 'Update data for tracked projects'
    prs = ArgumentParser(description=desc)
    prs.add_argument('--debug', default=DEBUG, action='store_true')
    return prs


def get_command_str():
    return ' '.join([sys.executable] + [shell_quote(v) for v in sys.argv])


def process_one(campaign_dir):
    # load config
    # load article list
    # fetch data
    # output timestamped json file to campaign_dir/data/_timestamp_.json
    # generate static pages
    print campaign_dir


def process_all():
    for campaign_dir in os.listdir(CAMPAIGNS_PATH):
        process_one(campaign_dir)


@tlog.wrap('critical')
def main():
    tlog.critical('start').success('started {0}', os.getpid())
    parser = get_argparser()
    args = parser.parse_args()

    try:
        if args.debug:
            set_debug(True)
        process_all()
        print 'success'
    except Exception:
        pass



if __name__ == '__main__':
    main()
