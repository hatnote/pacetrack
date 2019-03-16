# -*- coding: utf-8 -*-
"""
  Pacetrack
  ~~~~~~~~~

  Update script to load data for tracked wikiproject campaigns

"""
from __future__ import unicode_literals, print_function, division

import os
import sys
import gzip
import json
import uuid
import datetime
import operator
from pipes import quote as shell_quote
from argparse import ArgumentParser
from itertools import izip_longest

import urllib3
urllib3.disable_warnings()  # for labs

import attr
from ruamel import yaml
from ashes import AshesEnv
from boltons.strutils import slugify
from boltons.fileutils import atomic_save, iter_find_files, mkdir_p
from boltons.iterutils import unique, partition, first
from boltons.timeutils import isoparse, parse_timedelta
from tqdm import tqdm
from glom import glom, T

import gevent.monkey
gevent.monkey.patch_all()

from log import tlog, LOG_PATH, build_stream_sink
import metrics


CUR_PATH = os.path.dirname(os.path.abspath(__file__))
TEMPLATE_PATH = CUR_PATH + '/templates/'
PROJECT_PATH = os.path.dirname(CUR_PATH)
CAMPAIGNS_PATH = PROJECT_PATH + '/campaigns/'
STATIC_PATH = PROJECT_PATH + '/static/'

RUN_UUID = uuid.uuid4()
UPDATED_DT_FORMAT = '%Y-%m-%d %H:%M:%S'

DEBUG = False

# these paths are relative to the campaign directory
STATE_FULL_PATH_TMPL = '/data/%Y%m/state_full_%Y%m%d_%H%M%S.json.gz'
STATE_PATH_TMPL = '/data/%Y%m/state_%Y%m%d_%H%M%S.json'
STATE_FULL_FN_GLOB = 'state_full_*.json.gz'
STATE_FN_GLOB = 'state_*.json'


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


def eval_one_article_goal(pta, goal):
    ret = {}
    metric_func = getattr(metrics, goal['metric'], None)
    if metric_func is None:
        raise RuntimeError('unexpected metric name: %r' % goal['metric'])
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


def eval_article_goals(pta, goals):
    ret = {}
    for goal in goals:
        # maybe default name to metric name, need to precheck they don't collide
        ret[slugify(goal['name'])] = eval_one_article_goal(pta, goal)
    return ret


class StateNotFound(Exception):
    pass


def get_state_filepaths(data_dir, full=True):
    pattern = STATE_FULL_FN_GLOB if full else STATE_FN_GLOB
    return sorted(iter_find_files(data_dir, pattern))



@attr.s
class PTCampaignState(object):
    campaign = attr.ib()
    timestamp = attr.ib()
    campaign_results = attr.ib()
    goal_results = attr.ib(repr=False)
    article_results = attr.ib(default=None, repr=False)
    article_list = attr.ib(default=None, repr=False)
    _state_file_save_date = attr.ib(default=None)

    def get_results_struct(self):
        result_spec = {
            'title': 'title',
            'rev_id': 'rev_id',
            'talk_rev_id': 'talk_rev_id',
            'results': (T['results'].items(), sorted, [T[1]]),
        }
        # Note: results (above) is being sorted by key to line up with the
        # goals in the results template.

        ret = glom(self.article_results, [result_spec])

        return ret

    @property
    def is_start_state(self):
        # not really used, but illustrates the intended semantics
        return self.timestamp == self.campaign.start_state.timestamp

    @classmethod
    def from_json_path(cls, campaign, json_path, full):
        with open(json_path, 'rb') as f:
            if json_path.endswith('.gz'):
                f = gzip.GzipFile(fileobj=f)
            state_data = json.load(f)

        campaign_results = state_data.get('campaign_results')
        if not campaign_results:
            print('WARNING: old data, no campaign results present, delete data and reupdate')
        ret = cls(campaign=campaign,
                  timestamp=isoparse(state_data['timestamp']),
                  campaign_results=campaign_results,
                  goal_results=state_data['goal_results'],
                  article_results=state_data['article_results'] if full else None,
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

        latest_file_path = get_state_filepaths(latest_dir, full=full)[-1]

        return cls.from_json_path(campaign, latest_file_path, full=full)

    @classmethod
    def from_timestamp(cls, campaign, timestamp, full=True):
        strf_tmpl = STATE_FULL_PATH_TMPL if full else STATE_PATH_TMPL

        # this handles when a date object is passed in for timestamp
        # (instead of a datetime)
        strf_tmpl = strf_tmpl.replace('000000', '*')

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
                  campaign_results=None,
                  goal_results=None,
                  article_results=None)

        article_list = []
        article_title_list = campaign.article_title_list

        base_desc = 'Scanning %s @ %s' % (campaign.name, timestamp.isoformat().split('.')[0])
        article_title_list = tqdm(article_title_list,
                                  desc=base_desc,
                                  disable=None,  # autodisable on non-tty
                                  unit='article')

        def async_pta_update(pta, attr_func_map):
            jobs = []
            for attr, func in attr_func_map.items():
                _debug_log_func = tlog.wrap('debug')(func)
                cur = gevent.spawn(lambda pta=pta, attr=attr, func=_debug_log_func: setattr(pta, attr, func(pta)))
                jobs.append(cur)
            gevent.wait(jobs, timeout=20)
            return

        for title in article_title_list:
            article_title_list.set_description(base_desc + ' ({:16.16})'.format(title))
            pta = PTArticle(lang=campaign.lang, title=title, timestamp=timestamp)
            pta.talk_title = 'Talk:' + title
            async_pta_update(pta, {'rev_id': metrics.get_revid,
                                   'talk_rev_id': metrics.get_talk_revid})

            if pta.rev_id:
                async_pta_update(pta, {'templates': metrics.get_templates,
                                       'talk_templates': metrics.get_talk_templates,
                                       'assessments': metrics.get_assessments,
                                       'citations': metrics.get_citations,
                                       'wikidata_item': metrics.get_wikidata_item})
                pta.wikiprojects = metrics.get_wikiprojects(pta)  # relies on templates (no network)

            pta.results = eval_article_goals(pta, campaign.goals)

            article_list.append(pta)
        ret.article_list = article_list

        gres = {}  # goal results
        for goal in campaign.goals:
            key = slugify(goal['name'])
            target_ratio = float(goal.get('ratio', 1.0))
            results = [a.results[key]['done'] for a in article_list]
            # TODO: average/median metric value

            done, not_done = partition(results)
            # TODO: need to integrate start state for progress tracking
            ratio = 1.0 if not not_done else float(len(done)) / len(article_list)
            gres[key] = {'done_count': len(done),
                         'not_done_count': len(not_done),
                         'total_count': len(article_list),
                         'ratio': ratio,
                         'target_ratio': target_ratio,
                         'key': key,
                         'name': goal['name'],
                         'desc': goal.get('desc'),
                         'progress': ratio / target_ratio,
                         'done': ratio >= target_ratio}

        ret.campaign_results = glom(gres, {'done_count': (T.values(), ['done_count'], sum),
                                           'not_done_count': (T.values(), ['not_done_count'], sum),
                                           'total_count': (T.values(), ['total_count'], sum)})
        ret.campaign_results['ratio'] = ret.campaign_results['done_count'] / ret.campaign_results['total_count']

        ret.goal_results = gres
        ret.article_results = [attr.asdict(a) for a in article_list]
        return ret

    def save(self):
        """save to campaign_dir/data/YYYYMM/state_YYMMDD_HHMMSS.json
        and campaign_dir/data/YYYYMM/state_full_YYMMDD_HHMMSS.json"""
        if not self.goal_results or not self.article_results:
            raise RuntimeError('only intended to be called after a full results population with from_api()')
        save_timestamp = datetime.datetime.utcnow().isoformat()

        result_path = self.campaign.base_path + self.timestamp.strftime(STATE_PATH_TMPL)
        mkdir_p(os.path.split(result_path)[0])

        result_data = {'campaign_name': self.campaign.name,
                       'timestamp': self.timestamp,
                       'save_date': save_timestamp,
                       'campaign_results': self.campaign_results,
                       'goal_results': self.goal_results,
                       'title_list': self.campaign.article_title_list}
        with atomic_save(result_path) as f:
            json.dump(result_data, f, indent=2, sort_keys=True, default=str)

        full_result_fn = self.timestamp.strftime(STATE_FULL_PATH_TMPL)
        full_result_path = self.campaign.base_path + full_result_fn
        result_data['article_results'] = [attr.asdict(a) for a in self.article_list]
        with atomic_save(full_result_path) as f:
            gzf = gzip.GzipFile(filename=full_result_fn, fileobj=f)
            json.dump(result_data, gzf, default=str)
            gzf.close()

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

    disabled = attr.ib(default=False, repr=False)
    fetch_frequency = attr.ib(default=datetime.timedelta(seconds=3600))
    save_frequency = attr.ib(default=datetime.timedelta(days=1))
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

        if kwargs.get('save_frequency'):
            kwargs['save_frequency'] = parse_timedelta(kwargs['save_frequency'])
        if kwargs.get('fetch_frequency'):
            kwargs['fetch_frequency'] = parse_timedelta(kwargs['fetch_frequency'])

        ret = cls(**kwargs)

        needs_backfill = False
        with tlog.info('load_start_state') as _act:
            try:
                start_state = PTCampaignState.from_timestamp(ret, ret.campaign_start_date)
            except StateNotFound as snf:
                if not auto_start_state:
                    raise
                needs_backfill = True
                _act.failure('start state not found (got {0!r}), backfilling...', snf)

        if needs_backfill:
            with tlog.critical('backfill_start_state', verbose=True):
                ret.load_article_list()
                start_state = PTCampaignState.from_api(ret, ret.campaign_start_date)
                start_state.save()

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

    @tlog.wrap('critical', inject_as='_act')
    def load_article_list(self, _act):
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
            _act['path'] = json_file_path
            _act.success('successfully loaded sparql query json at {path}')
        elif alc['type'] == 'yaml_file':
            yaml_file_path = self.base_path + '/' + alc['path']
            title_key = alc['title_key']
            article_list = yaml.safe_load(open(yaml_file_path, 'rb')).get(title_key)
            self.article_title_list = article_list
            _act['path'] = yaml_file_path
            _act.success('successfully loaded yaml at {path}')
        else:
            raise ValueError('expected supported article list type, not %r' % (alc['type'],))
        return

    def load_all_states(self, full=False):
        """TODO: probably use a function like this to load in all available
        data for charting or pace calculation"""
        pass

    @tlog.wrap('critical', inject_as='_act', verbose=True)
    def record_state(self, timestamp=None, _act=None):
        if not timestamp:
            timestamp = datetime.datetime.utcnow()
        _act['timestamp'] = timestamp.isoformat()
        state = PTCampaignState.from_api(self, timestamp)
        state.save()

        return

    def render_report(self):
        start_state = [{'name': k, 'result': v} for k, v in self.start_state.goal_results.items()]
        start_state.sort(key=lambda g: g['name'])
        latest_state = [{'name': k, 'result': v} for k, v in self.latest_state.goal_results.items()]
        latest_state.sort(key=lambda g: g['name'])
        combined = [{'start': s[0], 'latest': s[1]} for s in izip_longest(start_state, latest_state)]
        # TODO: Also combine goals, so you can show info about targets, etc.

        ctx = {'id': self.id,
               'name': self.name,
               'lang': self.lang,
               'description': self.description,
               'contacts': self.contacts,
               'wikiproject_name': self.wikiproject_name,
               'campaign_start_date': self.campaign_start_date.isoformat(),
               'campaign_end_date': self.campaign_end_date.isoformat(),
               'date_created': self.date_created.isoformat(),
               'date_updated': datetime.datetime.utcnow().strftime(UPDATED_DT_FORMAT),
               'goals': self.goals,
               'article_count': len(self.article_title_list),
               'start_state_goal': start_state,
               'latest_state_goal': latest_state,
               'combined_state': combined
        }
        campaign_static_path = STATIC_PATH + 'campaigns/%s/' % self.id
        mkdir_p(campaign_static_path)
        report_html = ASHES_ENV.render('campaign.html', ctx)
        report_path = campaign_static_path + 'index.html'
        report_json_path = campaign_static_path + 'campaign.json'
        with atomic_save(report_path) as html_f, atomic_save(report_json_path) as json_f:
            html_f.write(report_html)
            json.dump(ctx, json_f, indent=2, sort_keys=True)
        return

    def _get_all_results(self):
        ret = self.latest_state.get_results_struct()
        start = self.start_state.get_results_struct()
        _title_start_map = dict([(r['title'], r) for r in start])
        for res in ret:
            res['start'] = _title_start_map.get(res['title'])
        return ret

    def render_article_list(self):
        all_results = self._get_all_results()
        ctx = {'name': self.name,
               'lang': self.lang,
               'description': self.description,
               'contacts': self.contacts,
               'wikiproject_name': self.wikiproject_name,
               'campaign_start_date': self.campaign_start_date.isoformat(),
               'campaign_end_date': self.campaign_end_date.isoformat(),
               'date_created': self.date_created.isoformat(),
               'date_updated': datetime.datetime.utcnow().strftime(UPDATED_DT_FORMAT),
               'article_count': len(self.article_title_list),
               'all_results': all_results,
               'goals': [{'name': 'Article'}] + sorted(self.goals, key=lambda s: s['name'])}
        campaign_static_path = STATIC_PATH + 'campaigns/%s/' % self.id
        article_list_html = ASHES_ENV.render('articles.html', ctx)
        article_list_path = campaign_static_path + 'articles.html'
        article_list_json_path = campaign_static_path + 'articles.json'
        mkdir_p(os.path.split(article_list_path)[0])
        with atomic_save(article_list_path) as html_f, atomic_save(article_list_json_path) as json_f:
            html_f.write(article_list_html.encode('utf-8'))
            json.dump(ctx, json_f, indent=2, sort_keys=True)
        return

    @tlog.wrap('debug')
    def prune_by_frequency(self, dry_run=False):
        # TODO: make this work for all campaign YYYYMM directories
        # under data dir, not just the most recent one.
        if not self.save_frequency:
            return
        if not self.latest_state:
            self.load_latest_state()
        state_path = self.get_latest_state_path()
        target_dir = os.path.dirname(state_path)

        for full in (True, False):
            state_paths = get_state_filepaths(target_dir, full=full)
            if not state_paths:
                return
            tmpl = os.path.basename(STATE_FULL_PATH_TMPL if full else STATE_PATH_TMPL)
            last_kept_dt = datetime.datetime.strptime(os.path.basename(state_paths[0]), tmpl)
            to_prune = []
            for fsp in state_paths[1:-1]:  # ignore the latest and first
                cur_dt = datetime.datetime.strptime(os.path.basename(fsp), tmpl)
                if last_kept_dt < (cur_dt - self.save_frequency):
                    last_kept_dt = cur_dt
                else:
                    to_prune.append(fsp)

            for p in to_prune:
                with tlog.critical('prune data file', path=p):
                    if dry_run:
                        continue
                    os.remove(p)
        return

    def get_latest_state_path(self, full=True):
        data_base_dir = self.base_path + '/data/'
        data_dirs = next(os.walk(data_base_dir))[1]
        data_dirs = [d for d in data_dirs if d.isdigit()]  # only numeric dir names
        if not data_dirs:
            raise StateNotFound('no numeric data directories found in %r' % data_base_dir)
        latest_dir = data_base_dir + sorted(data_dirs)[-1]

        ret = get_state_filepaths(latest_dir, full=full)[-1]

        return ret

    def load_latest_state(self):
        latest_state_path = self.get_latest_state_path(full=True)
        self.latest_state = PTCampaignState.from_json_path(self, latest_state_path, full=True)

    @tlog.wrap('critical', 'update campaign', verbose=True, inject_as='_act')
    def update(self, _act):
        "does it all"
        final_update_log_path = STATIC_PATH + 'campaigns/%s/update.log' % self.id
        _act['name'] = self.name
        _act['id'] = self.id
        _act['log_path'] = final_update_log_path
        with atomic_save(final_update_log_path) as f:
            cur_update_sink = build_stream_sink(f)
            old_sinks = tlog.sinks
            tlog.set_sinks(old_sinks + [cur_update_sink])
            try:
                self.load_article_list()
                self.load_latest_state()
                self.record_state()  # defaults to now
                self.load_latest_state()
                self.prune_by_frequency()
                self.render_report()
                self.render_article_list()
            finally:
                tlog.set_sinks(old_sinks)
        return


def get_command_str():
    return ' '.join([sys.executable] + [shell_quote(v) for v in sys.argv])


def load_and_update_campaign(campaign_dir, force=False):
    with tlog.critical('load_campaign_dir', path=campaign_dir) as _act:
        ptc = PTCampaign.from_path(campaign_dir)
        _act['name'] = ptc.name
        if ptc.disabled:
            _act.failure("campaign {name!r} disabled, skipping.")
            return ptc
    ptc.load_latest_state()
    now = datetime.datetime.utcnow()
    next_fetch = now if not ptc.latest_state else ptc.latest_state.timestamp + ptc.fetch_frequency
    if not force and next_fetch > now:
        tlog.critical('skip_fetch').success('{cid} not out of date, skipping until next fetch at {next_fetch}. ',
                                            cid=ptc.id, next_fetch=next_fetch)
        return ptc
    ptc.update()
    print()
    print('Goal results:')
    for key, results in ptc.latest_state.goal_results.items():
        print(' - {name}  ({done_count}/{total_count})  Done: {done}'.format(**results))
    print()
    return ptc


def get_all_campaign_dirs(abspath=True):
    # TODO: check for config.yaml in the directory?
    ret = [CAMPAIGNS_PATH + cd if abspath else cd for cd in os.listdir(CAMPAIGNS_PATH) if not cd.startswith('.')]
    return sorted(ret)



if __name__ == '__main__':
    main()
