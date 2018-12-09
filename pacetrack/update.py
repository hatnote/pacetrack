# -*- coding: utf-8 -*-
"""
  Pacetrack
  ~~~~~~~~~

  Update script to load data for tracked wikiproject campaigns

"""
from __future__ import unicode_literals
from __future__ import print_function

import os
import sys
import json
import uuid
import datetime
import operator
import traceback
from time import strftime
from pipes import quote as shell_quote
from argparse import ArgumentParser

import attr
from ruamel import yaml
from boltons.strutils import slugify
from boltons.fileutils import atomic_save
from boltons.iterutils import unique, partition

from log import tlog, set_debug
from metrics import (get_revid, get_templates, get_talk_templates,
                     get_assessments, get_wikiprojects, get_citations)

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
class PTArticle(object):
    lang = attr.ib()
    title = attr.ib()
    timestamp = attr.ib()

    rev_id = attr.ib(default=None)
    talk_rev_id = attr.ib(default=None, repr=False)

    content = attr.ib(default=None, repr=False)
    assessments = attr.ib(default=None, repr=False)
    templates = attr.ib(default=None, repr=False)
    talk_templates = attr.ib(default=None, repr=False)
    infoboxes = attr.ib(default=None, repr=False)
    citations = attr.ib(default=None, repr=False)
    wikidata_item = attr.ib(default=None, repr=False)


def ref_count(pta):
    return len(pta.citations)


def template_count(pta, template_name=None, template_regex=None, case_sensitive=False):
    tmpl_names = pta.templates
    if not case_sensitive:
        tmpl_names = unique([t.lower() for t in tmpl_names])
        template_name = template_name.lower()
    if not template_name:
        return len(tmpl_names)
    # TODO: regex support
    return len([t for t in tmpl_names if template_name in t])


def eval_one_article_goal(goal, pta):
    ret = {}
    metric_func = globals()[goal['metric']]
    metric_args = goal.get('metric_args', {})
    metric_val = metric_func(pta, **metric_args)
    target_val = goal['target']['value']
    cmp_name = goal['target'].get('cmp', 'ge')
    if cmp_name == 'bool':
        return bool(metric_val)
    cmp_func = getattr(operator, cmp_name, None)
    ret['cur'] = metric_val
    ret['target'] = target_val
    ret['cmp'] = cmp_name
    ret['done'] = cmp_func(metric_val, target_val)
    return ret


def eval_article_goals(goals, pta):
    ret = {}
    for goal in goals:
        # maybe default name to metric name, need to precheck they don't collide
        ret[slugify(goal['name'])] = eval_one_article_goal(goal, pta)
    return ret


@attr.s
class PTCampaign(object):
    name = attr.ib()
    lang = attr.ib()
    requested_by = attr.ib()
    wikiproject_name = attr.ib()
    campaign_start_date = attr.ib()
    campaign_end_date = attr.ib()
    date_created = attr.ib()
    goals = attr.ib(repr=False)
    article_list_config = attr.ib(repr=False)
    target_timestamp = attr.ib(default=attr.Factory(datetime.datetime.utcnow))
    article_title_list = attr.ib(default=None, repr=False)
    article_list = attr.ib(default=None, repr=False)
    base_path = attr.ib(default=None, repr=False)

    @classmethod
    def from_path(cls, path, timestamp=None):
        config_data = yaml.safe_load(open(path + '/config.yaml', 'rb'))

        kwargs = dict(config_data)
        kwargs['article_list_config'] = dict(kwargs.pop('article_list'))
        kwargs['base_path'] = path

        assert 'target_timestamp' not in kwargs
        if timestamp is not None:
            kwargs['target_timestamp'] = timestamp

        ret = cls(**kwargs)

        return ret

    @classmethod
    def create_from_config(cls, name):
        """
        make a directory in campaign path
        make a data in that
        initialize the config
        etc.
        """
        pass

    def load_article_list(self):
        """
        # TODO: add sparql query and wikiproject support
        article_list_filename = config_data.pop('article_list', "article_list.yaml")
        article_list_path = path + '/' + article_list_filename
        article_list = yaml.safe_load(open(article_list_path, 'rb'))
        """
        alc = self.article_list_config
        if alc['type'] == 'sparql_json_file':
            json_file_path = self.base_path + '/' + alc['path']
            json_data = json.load(open(json_file_path))
            title_key = alc['title_key']
            article_list = [e[title_key] for e in json_data]
            self.article_title_list = article_list
        else:
            raise ValueError('expected supported article list type, not %r' % (alc['type'],))
        return

    def load_articles(self):
        "create a bunch of stub PTArticles"
        article_list = []
        for title in self.article_title_list:
            cur_pta = PTArticle(lang=self.lang, title=title, timestamp=self.target_timestamp)
            cur_pta.rev_id = get_revid(cur_pta)
            article_list.append(cur_pta)
        self.article_list = article_list
        return

    def populate_article_features(self):
        "look at current goals, find which attributes are needed to compute the relevant metrics"
        for art in self.article_list:
            art.templates = get_templates(art)
            art.talk_templates = get_talk_templates(art)
            art.assessments = get_assessments(art)
            art.wikiprojects = get_wikiprojects(art)
            art.citations = get_citations(art)
        return

    def compute_status(self):
        "look at goals and the now-populated PTArticles, and compute the progress, pace, etc."
        for art in self.article_list:
            art.results = eval_article_goals(self.goals, art)

        ores = {}  # overall results
        for goal in self.goals:
            key = slugify(goal['name'])
            target_ratio = float(goal.get('ratio', 1.0))

            results = [a.results[key]['done'] for a in self.article_list]
            done, not_done = partition(results)
            ratio = 1.0 if not not_done else float(len(done)) / len(not_done)
            ores[key] = {'done_count': len(done),
                         'not_done_count': len(not_done),
                         'total_count': len(self.article_list),
                         'ratio': ratio,
                         'key': key,
                         'name': goal['name'],
                         'done': ratio >= target_ratio,
                         'target_ratio': target_ratio}
        self.overall_results = ores
        return

    def render_report(self):
        pass

    def process(self):
        "does it all"
        self.load_article_list()
        self.load_articles()
        self.populate_article_features()
        self.compute_status()
        self.render_report()



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
    pt = PTCampaign.from_path(campaign_dir)
    print(pt)
    pt.process()
    print()
    print('Results:')
    for art in pt.article_list:
        print('  ', (art.title, art.results))
    print()
    print('Overall results:')
    for key, results in pt.overall_results.items():
        print(' - {name}  ({done_count}/{total_count})  Done: {done}'.format(**results))
    print()
    return pt


def process_all():
    for campaign_dir in os.listdir(CAMPAIGNS_PATH):
        cur_pt = process_one(CAMPAIGNS_PATH + campaign_dir)
    import pdb;pdb.set_trace()

@tlog.wrap('critical')
def main():
    tlog.critical('start').success('started {0}', os.getpid())
    parser = get_argparser()
    args = parser.parse_args()

    try:
        if args.debug:
            set_debug(True)
        process_all()
    except Exception:
        raise  # TODO



if __name__ == '__main__':
    main()
