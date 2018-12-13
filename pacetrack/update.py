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
from ashes import AshesEnv
from boltons.strutils import slugify
from boltons.fileutils import atomic_save, iter_find_files, mkdir_p
from boltons.iterutils import unique, partition, first
from boltons.timeutils import isoparse

from log import tlog, set_debug
from metrics import (get_revid, get_talk_revid, get_templates, get_talk_templates,
                     get_assessments, get_wikiprojects, get_citations,
                     get_wikidata_item)

CUR_PATH = os.path.dirname(os.path.abspath(__file__))
TEMPLATE_PATH = CUR_PATH + '/templates/'
PROJECT_PATH = os.path.dirname(CUR_PATH)
CAMPAIGNS_PATH = PROJECT_PATH + '/campaigns/'
STATIC_PATH = PROJECT_PATH + '/static/'

RUN_UUID = uuid.uuid4()

DEBUG = False


ASHES_ENV = AshesEnv(TEMPLATE_PATH, filters={'percentage': lambda n: round(n*100, 2)})
ASHES_ENV.load_all()


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
    title = attr.ib(default=None)

    content = attr.ib(default=attr.Factory(list), repr=False)
    assessments = attr.ib(default=attr.Factory(list), repr=False)
    templates = attr.ib(default=attr.Factory(list), repr=False)
    talk_templates = attr.ib(default=attr.Factory(list), repr=False)
    wikiprojects = attr.ib(default=attr.Factory(list), repr=False)
    infoboxes = attr.ib(default=attr.Factory(list), repr=False)
    citations = attr.ib(default=attr.Factory(list), repr=False)
    wikidata_item = attr.ib(default=attr.Factory(list), repr=False)

    results = attr.ib(default=None, repr=False)


def ref_count(pta):
    return len(pta.citations['references_by_id'].keys())


def wikidata_item(pta):
    return len(pta.wikidata_item)


def in_wikiproject(pta, wikiproject=None, case_sensitive=False):
    wikiprojects = pta.wikiprojects
    if not case_sensitive:
        wikiprojects = unique([w.lower() for w in wikiprojects])
        wikiproject = wikiproject.lower()
    return wikiproject in wikiprojects


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
        return {'done': bool(metric_val)}
    cmp_func = getattr(operator, cmp_name, None)
    ret['cur'] = metric_val
    ret['target'] = target_val
    ret['cmp'] = cmp_name
    done = cmp_func(metric_val, target_val)
    ret['done'] = done

    start_val = 0.0  # TODO

    remaining = 0.0 if done else target_val - metric_val
    ret['remaining'] = remaining

    progress = (metric_val - start_val) / (target_val - start_val)
    ret['progress'] = progress

    return ret


def eval_article_goals(goals, pta):
    ret = {}
    for goal in goals:
        # maybe default name to metric name, need to precheck they don't collide
        ret[slugify(goal['name'])] = eval_one_article_goal(goal, pta)
    return ret


class StateNotFound(Exception):
    pass


@attr.s
class PTCampaignState(object):
    campaign = attr.ib()
    timestamp = attr.ib()
    overall_results = attr.ib(repr=False)
    specific_results = attr.ib(default=None, repr=False)
    article_list = attr.ib(default=None, repr=False)
    _state_file_save_date = attr.ib(default=None)

    @property
    def is_start_state(self):
        # not really use, but illustrates the intended semantics
        return self.timestamp == self.campaign.start_state.timestamp

    @classmethod
    def from_json_path(cls, campaign, json_path, full):
        with open(json_path, 'rb') as f:
            state_data = json.load(f)

        ret = cls(campaign=campaign,
                  timestamp=isoparse(state_data['timestamp']),
                  overall_results=state_data['overall_results'],
                  specific_results=state_data['specific_results'] if full else None,
                  # title_list=state_data['title_list'],  # no use for this yet
                  state_file_save_date=state_data['save_date'])
        return ret

    @classmethod
    def from_latest(cls, campaign, full=True):
        data_base_dir = campaign.base_path + '/data/'
        data_dirs = next(os.walk(data_base_dir))[1]
        data_dirs = [d for d in data_dirs if d.isdigit()]  # only numeric dir names
        if not data_dirs:
            raise StateNotFound('no numeric data directories found in %r' % data_base_dir)
        latest_dir = data_base_dir + sorted(data_dirs)[-1]

        if full:
            pattern = 'state_full_*.json'
        else:
            pattern = 'state_*.json'

        latest_file_path = sorted(iter_find_files(latest_dir, pattern))[-1]

        return cls.from_json_path(campaign, latest_file_path, full=full)

    @classmethod
    def from_timestamp(cls, campaign, timestamp, full=True):
        # TODO: support for hour/minute when present in timestamp
        if full:
            strf_tmpl = '/data/%Y%m/state_full_%Y%m%d_*.json'
        else:
            strf_tmpl = '/data/%Y%m/state_%Y%m%d_*.json'

        start_pattern = timestamp.strftime(strf_tmpl)
        dir_path = campaign.base_path + os.path.split(start_pattern)[0]
        file_paths = sorted(iter_find_files(dir_path, os.path.split(start_pattern)[1]))
        try:
            first_path = file_paths[0]
        except IndexError:
            raise StateNotFound('no state found for campaign %r at timestamp %s'
                                % (campaign, timestamp))

        return cls.from_json_path(campaign, first_path, full=full)

    @classmethod
    def from_api(cls, campaign, timestamp=None):
        timestamp = timestamp if timestamp is not None else datetime.datetime.utcnow()
        ret = cls(campaign=campaign,
                  timestamp=timestamp,
                  overall_results=None,
                  specific_results=None)

        article_list = []
        for title in campaign.article_title_list:
            pta = PTArticle(lang=campaign.lang, title=title, timestamp=timestamp)
            pta.talk_title = 'Talk:' + title
            pta.rev_id = get_revid(pta)
            pta.talk_rev_id = get_talk_revid(pta)

            if pta.rev_id:
                pta.templates = get_templates(pta)
                pta.talk_templates = get_talk_templates(pta)
                pta.assessments = get_assessments(pta)
                pta.wikiprojects = get_wikiprojects(pta)
                pta.citations = get_citations(pta)
                pta.wikidata_item = get_wikidata_item(pta)

            pta.results = eval_article_goals(campaign.goals, pta)

            article_list.append(pta)
        ret.article_list = article_list

        ores = {}  # overall results
        for goal in campaign.goals:
            key = slugify(goal['name'])
            target_ratio = float(goal.get('ratio', 1.0))
            results = [a.results[key]['done'] for a in article_list]
            # TODO: average/median metric value

            done, not_done = partition(results)
            # TODO: need to integrate start state for progress tracking
            ratio = 1.0 if not not_done else float(len(done)) / len(article_list)
            ores[key] = {'done_count': len(done),
                         'not_done_count': len(not_done),
                         'total_count': len(article_list),
                         'ratio': ratio,
                         'target_ratio': target_ratio,
                         'key': key,
                         'name': goal['name'],
                         'progress': ratio / target_ratio,
                         'done': ratio >= target_ratio}
        ret.overall_results = ores
        ret.specific_results = [attr.asdict(a) for a in article_list]
        return ret

    def save(self):
        """save to campaign_dir/data/YYYYMM/state_YYMMDD_HHMMSS.json
        and campaign_dir/data/YYYYMM/state_full_YYMMDD_HHMMSS.json"""
        if not self.overall_results or not self.specific_results:
            raise RuntimeError('only intended to be called after a full results population with from_api()')
        save_timestamp = datetime.datetime.utcnow().isoformat()

        result_path = self.campaign.base_path + self.timestamp.strftime('/data/%Y%m/state_%Y%m%d_%H%M%S.json')
        mkdir_p(os.path.split(result_path)[0])

        result_data = {'campaign_name': self.campaign.name,
                       'timestamp': self.timestamp,
                       'save_date': save_timestamp,
                       'overall_results': self.overall_results,
                       'title_list': self.campaign.article_title_list}
        with atomic_save(result_path) as f:
            json.dump(result_data, f, indent=2, sort_keys=True, default=str)

        full_result_path = self.campaign.base_path + self.timestamp.strftime('/data/%Y%m/state_full_%Y%m%d_%H%M%S.json')
        result_data['specific_results'] = [attr.asdict(a) for a in self.article_list]
        with atomic_save(full_result_path) as f:
            json.dump(result_data, f, default=str)

        return


def to_date(dordt):
    if isinstance(dordt, datetime.date):
        return dordt
    elif isinstance(dordt, datetime.datetime):
        return dordt.date()
    raise ValueError('expected date or datetime, not: %r' % (dordt,))


def validate_campaign_id(_, __, id_text):
    if slugify(id_text) == id_text:
        return
    raise ValueError('expected campaign id to consist of lowercase printable characters,'
                     ' with no punctuation except for underscores, like "%s", not %r'
                     % (slugify(id_text), id_text))


@attr.s
class PTCampaign(object):
    id = attr.ib(validator=validate_campaign_id)
    name = attr.ib()
    lang = attr.ib()
    description = attr.ib()
    contacts = attr.ib()
    wikiproject_name = attr.ib()
    campaign_start_date = attr.ib()
    campaign_end_date = attr.ib()
    date_created = attr.ib()
    goals = attr.ib(repr=False)
    article_list_config = attr.ib(repr=False)

    article_title_list = attr.ib(default=None, repr=False)
    start_state = attr.ib(default=None, repr=False)
    latest_state = attr.ib(default=None, repr=False)  # populate with load_latest_state()

    base_path = attr.ib(default=None, repr=False)

    @classmethod
    def from_path(cls, path, auto_start_state=True):
        config_data = yaml.safe_load(open(path + '/config.yaml', 'rb'))

        kwargs = dict(config_data)
        kwargs['article_list_config'] = dict(kwargs.pop('article_list'))
        kwargs['base_path'] = path

        ret = cls(**kwargs)

        try:
            start_state = PTCampaignState.from_timestamp(ret, ret.campaign_start_date)
        except StateNotFound as snf:
            if not auto_start_state:
                raise
            print('start state not found (got %r), backfilling...' % snf)
            ret.load_article_list()
            start_state = PTCampaignState.from_api(ret, ret.campaign_start_date)
            start_state.save()
            print('backfilling complete')

        ret.start_state = start_state

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

    def load_all_states(self, full=False):
        """TODO: probably use a function like this to load in all available
        data for charting or pace calculation"""
        pass

    def record_state(self, timestamp=None):
        if not timestamp:
            timestamp = datetime.datetime.utcnow()
        start_state = PTCampaignState.from_api(self, timestamp)
        start_state.save()
        return

    def render_report(self):
        ctx = {'id': self.id,
               'name': self.name,
               'lang': self.lang,
               'description': self.description,
               'contacts': self.contacts,
               'wikiproject_name': self.wikiproject_name,
               'campaign_start_date': self.campaign_start_date.isoformat(),
               'campaign_end_date': self.campaign_end_date.isoformat(),
               'date_created': self.date_created.isoformat(),
               'date_updated': datetime.datetime.utcnow().strftime('%Y-%m-%d %H:%M:%s'),
               'goals': self.goals,
               'article_count': len(self.article_title_list),
               'start_state_overall': [{'name': k, 'result': v} for k, v in self.start_state.overall_results.items()],
               'latest_state_overall': [{'name': k, 'result': v} for k, v in self.latest_state.overall_results.items()],
        }
        report_html = ASHES_ENV.render('campaign.html', ctx)
        report_path = STATIC_PATH + ('campaigns/%s/index.html' % self.id)
        mkdir_p(os.path.split(report_path)[0])
        with atomic_save(report_path) as f:
            f.write(report_html)
        return

    def render_article_list(self):
        latest = []
        for article in self.latest_state.specific_results:
            results = sorted(article['results'].items())
            res = {'title': article['title'],
                    'results': [r[1] for r in results]}
            latest.append(res)
        ctx = {'name': self.name,
               'lang': self.lang,
               'description': self.description,
               'contacts': self.contacts,
               'wikiproject_name': self.wikiproject_name,
               'campaign_start_date': self.campaign_start_date.isoformat(),
               'campaign_end_date': self.campaign_end_date.isoformat(),
               'date_created': self.date_created.isoformat(),
               'date_updated': datetime.datetime.utcnow().strftime('%Y-%m-%d %H:%M:%s'),
               'article_count': len(self.article_title_list),
               'latest': latest,
               'goals': [{'name': 'Article'}] + sorted(self.goals, key=lambda s: s['name'])}
        article_list_html = ASHES_ENV.render('articles.html', ctx)
        article_list_path = STATIC_PATH + ('campaigns/%s/articles.html' % self.id)
        mkdir_p(os.path.split(article_list_path)[0])
        with atomic_save(article_list_path) as f:
            f.write(article_list_html)
        return

    def load_latest_state(self):
        self.latest_state = PTCampaignState.from_latest(self)

    def update(self):
        "does it all"
        self.load_article_list()
        self.load_latest_state()
        self.record_state()  # defults to now
        self.load_latest_state()
        self.render_report()
        self.render_article_list()


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
    # TODO: if data doesn't exist for the campaign's start date, just
    # automatically populate it before doing the current time.
    print(pt)
    pt.update()
    print()
    print('Results:')
    for res in pt.latest_state.specific_results:
        print('  ', (res['title'], res['results']))
    print()
    print('Overall results:')
    for key, results in pt.latest_state.overall_results.items():
        print(' - {name}  ({done_count}/{total_count})  Done: {done}'.format(**results))
    print()
    return pt


def process_all():
    for campaign_dir in os.listdir(CAMPAIGNS_PATH):
        if not campaign_dir.startswith('.'):
            cur_pt = process_one(CAMPAIGNS_PATH + campaign_dir)
    # import pdb;pdb.set_trace()

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
