# -*- coding: utf-8 -*-
from __future__ import unicode_literals
from __future__ import print_function


import re
import datetime

from hyperlink import parse as parse_url
import requests


MW_API_URL = parse_url('https://en.wikipedia.org/w/api.php')
REST_API_BASE_URL = parse_url('https://en.wikipedia.org/api/rest_v1/')
REF_API_BASE_URL = REST_API_BASE_URL.child('page', 'references')

from log import tlog


def format_datetime(dt):
    if isinstance(dt, datetime.date):
        dt = datetime.datetime(dt.year, dt.month, dt.day, 0, 0, 0)
    return dt.isoformat().split('.')[0] + 'Z'


def get_revid(pta):
    return _get_revid_at_timestamp(pta.title, format_datetime(pta.timestamp))


def get_talk_revid(pta):
        return _get_revid_at_timestamp(pta.talk_title, format_datetime(pta.timestamp))


def get_templates(pta):
    return _get_templates(pta.rev_id)


def get_talk_templates(pta):
    return _get_templates(pta.talk_rev_id)


def get_assessments(pta):
    return _get_assessments(pta.title)


def get_wikiprojects(pta):
    return [tc.replace('WikiProject ', '')  for tc in pta.talk_templates
            if 'wikiproject' in tc.lower()]


def get_citations(pta):
    return _get_citations(pta.title, pta.rev_id)


def get_wikidata_item(pta):
    return _get_article_wikidata_item(pta.rev_id)

##

@tlog.wrap('info', inject_as='act')
def get_json(url, params=None, act=None):  # TODO: option for validating status code
    params = dict(params or {})
    for k, v in params.items():
        url = url.set(unicode(k), unicode(v))
    if act:
        act['url'] = unicode(url)
    resp = requests.get(url, params=params)
    return resp.json()


def get_wapi_json(params):
    url = MW_API_URL
    return get_json(url, params)


def _get_revid_at_timestamp(title, timestamp):
    """Get page revision id at a particular timestamp

    :param title: a page title; note, the MW API only supports a
    single title in titles when using rvstart
    :param timestamp: in the form of ISO8601 '2018-11-29T20:09:07Z'
    :return: a map from page title to the revision id

    """
    resp = get_wapi_json(params={
        'action': 'query',
        'prop': 'revisions',
        'format': 'json',
        'titles': title,
        'rvlimit': '1',
        'rvstart': timestamp
    })
    try:
        ret = {page['title']: page['revisions'][0]['revid'] for page in resp['query']['pages'].values()}
        ret = ret.values()[0]
    except KeyError as e:
        ret = None
    return ret


def _get_templates(oldid):
    """Get a list of templates as well as number of calls per template for a given revision (oldid)

    NOTE: we parse the info from the transclusion expansion report from the parse API, which might be unstable.
    :param oldid:
    :return: a list of
    """
    revisionResponse = get_wapi_json(params={
        'action': 'parse',
        'oldid': oldid,
        'format': 'json',
    })

    templates = revisionResponse['parse']['templates']
    ret = [t['*'].replace('Template:', '') for t in templates]
    return ret


def _get_article_wikidata_item(oldid):
    params = {'action': 'query',
              'prop': 'wbentityusage',
              'revids': oldid,
              'format': 'json'}
    resp = get_wapi_json(params)
    try:
        wbentities = resp['query']['pages'].values()[0]['wbentityusage']
    except KeyError as e:
        return []

    return [q for (q, val) in wbentities.items() if 'S' in val['aspects']]


def _get_assessments(title):
    # can't actually get assessments from past versions of an article
    # see: https://phabricator.wikimedia.org/T211485
    params = {'action': 'query',
              'prop': 'pageassessments',
              'titles': title,
              'formatversion': 2,
              'format': 'json'}
    resp = get_wapi_json(params)
    try:
        return resp['query']['pages'][0]['pageassessments']
    except KeyError:
        return {}


def check_infobox(template_calls):
    for template_call in template_calls:
        if 'infobox' in template_call.lower():
            return True
    return False


def check_infobox_wikidata(template_calls):
    wikidata_template_pattern = re.compile(r'infobox(.*)\/wikidata')
    for template_call in template_calls:
        if re.search(wikidata_template_pattern, template_call.lower()):
            return True
    return False


def get_wikiproject(wikiproject, talk_revid):
    talk_templates = _get_templates(talk_revid)
    wikiprojects = [tc.replace('WikiProject ', '')  for tc in talk_templates
                    if 'wikiproject' in tc.lower()]

    if wikiproject in wikiprojects:
        return True
    return False


def _get_citations(title, old_id):
    title = title.replace(' ', '_')  # rest endpoint doesn't like url encoded spaces
    api_url = REF_API_BASE_URL.child(title, unicode(old_id))

    citations = get_json(api_url)

    return citations


def get_citation_stats(title, oldid):
    citations = _get_citations(title, oldid)
    try:
        ref_count = len(citations['references_by_id'].keys())
    except KeyError as e:
        return {'reference_count': 0,
                'reference_wikidata_count': 0,
                'reference_wikidata_percent': 0}

    ref_wikidata_count = len([c for c in citations['references_by_id'].items()
                              if 'https://www.wikidata.org/wiki/Q'
                              in c[1]['content']['html']])
    if ref_count:
        ref_wikidata_percent = ref_wikidata_count / (ref_count * 1.0)
    else:
        ref_wikidata_percent = 0

    return {'reference_count': ref_count,
            'reference_wikidata_count': ref_wikidata_count,
            'reference_wikidata_percent': ref_wikidata_percent}


def get_all_stats(title, wikiproject, date):
    revid = _get_revid_at_timestamp(title, date)

    talk_title = 'Talk:' + title
    talk_revid = _get_revid_at_timestamp(talk_title, date)

    templates = _get_templates(revid)
    assessments = _get_assessments(title)

    stats = {'wikipedia_exists': revid,
             'wikidata_exists': _get_article_wikidata_item(revid),
             'infobox': check_infobox(templates),
             'infobox_wikidata': check_infobox_wikidata(templates),
             'citation_stats': get_citation_stats(title, revid),
             'in_wikiproject': get_wikiproject(wikiproject, talk_revid),
             'quality': assessments.get(wikiproject, {}).get('class'),
             'importance': assessments.get(wikiproject, {}).get('importance'),
             'metadata': {'target_date': date,
                          'revision': revid,
                          'talk_revision': talk_revid}}

    return stats


if __name__ == '__main__':
    title = 'Coffee'
    wikiproject = 'Newspapers'
    date = '2018-12-05T20:00:00Z'

    stats = get_all_stats(title, wikiproject, date)
    print(stats)

    old_date = '2010-12-05T20:00:00Z'
    stats = get_all_stats(title, wikiproject, old_date)
    print(stats)

    import pdb;pdb.set_trace()
