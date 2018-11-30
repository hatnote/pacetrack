# -*- coding: utf-8 -*-
"""
  Pacetrack
  ~~~~~~~~~

  Update script to load data for tracked wikiproject campaigns

"""
from __future__ import print_function

import os
import sys
import json
import uuid
import traceback
from time import strftime
from pipes import quote as shell_quote
from argparse import ArgumentParser

import attr
from ruamel import yaml
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


@attr.s
class PaceTracker(object):
    name = attr.ib()
    lang = attr.ib()
    requested_by = attr.ib()
    wikiproject_name = attr.ib()
    campaign_start_date = attr.ib()
    campaign_end_date = attr.ib()
    date_created = attr.ib()
    article_list = attr.ib(repr=False)

    @classmethod
    def from_path(cls, path):
        print(path)
        config_data = yaml.safe_load(open(path + '/config.yaml', 'rb'))

        # TODO: add sparql query and wikiproject support
        article_list_filename = config_data.pop('article_list', "article_list.yaml")
        article_list_path = path + '/' + article_list_filename
        article_list = yaml.safe_load(open(article_list_path, 'rb'))
        kwargs = dict(config_data)
        kwargs['article_list'] = article_list['articles'] or []
        return cls(**kwargs)

    @classmethod
    def create_from_config(cls, name):
        """
        make a directory in campaign path
        make a data in that
        initialize the config
        etc.
        """
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
    pt = PaceTracker.from_path(campaign_dir)
    print(pt)


def process_all():
    for campaign_dir in os.listdir(CAMPAIGNS_PATH):
        process_one(CAMPAIGNS_PATH + campaign_dir)


@tlog.wrap('critical')
def main():
    tlog.critical('start').success('started {0}', os.getpid())
    parser = get_argparser()
    args = parser.parse_args()

    try:
        if args.debug:
            set_debug(True)
        process_all()
        print('success')
    except Exception:
        raise  # TODO



if __name__ == '__main__':
    main()
