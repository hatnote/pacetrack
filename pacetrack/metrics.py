import re
import requests
from collections import namedtuple


MW_API_URL = 'https://en.wikipedia.org/w/api.php'
REST_API_URL = 'https://en.wikipedia.org/api/rest_v1/page/references/%s/%s'


def get_revid_at_timestamp(title, timestamp):
    """Get page revision id at a particular timestamp

    :param title: a page title; note, the MW API only supports a
    single title in titles when using rvstart
    :param timestamp: in the form of ISO8601 '2018-11-29T20:09:07Z'
    :return: a map from page title to the revision id

    """
    resp = requests.get('https://en.wikipedia.org/w/api.php', params={
        'action': 'query',
        'prop': 'revisions',
        'format': 'json',
        'titles': title,
        'rvlimit': '1',
        'rvstart': timestamp
    }).json()
    try:
        ret = {page['title']: page['revisions'][0]['revid'] for page in resp['query']['pages'].values()}
    except KeyError as e:
        return {title: None}
    return ret


def get_templates(oldid):
    """Get a list of templates as well as number of calls per template for a given revision (oldid)

    NOTE: we parse the info from the transclusion expansion report from the parse API, which might be unstable.
    :param oldid:
    :return: a list of
    """
    revisionResponse = requests.get('https://en.wikipedia.org/w/api.php', params={
        'action': 'parse',
        'oldid': oldid,
        'format': 'json',
    }).json()

    templates = revisionResponse['parse']['templates']
    ret = [t['*'].replace('Template:', '') for t in templates]
    return ret


def get_article_wikidata_item(oldid):
    params = {'action': 'query',
              'prop': 'wbentityusage',
              'revids': oldid,
              'format': 'json'}
    resp = requests.get(MW_API_URL, params)
    try:
        wbentities = resp.json()['query']['pages'].values()[0]['wbentityusage']
    except KeyError as e:
        return None
    
    # 'T' aspect means the Wikidata item corresponds to the title of the page
    # I'm assuming there is only corresponding Wikidata item; maybe that's
    # not safe?
    return [q for (q, val) in wbentities.items() if 'T' in val['aspects']][0]


def get_assessments(title):
    # I don't think you can actually get assessments from past
    # versions of an article
    params = {'action': 'query',
              'prop': 'pageassessments',
              'titles': title,
              'formatversion': 2,
              'format': 'json'}
    resp = requests.get(MW_API_URL, params)
    return resp.json()['query']['pages'][0]['pageassessments']
    


def check_existence(title, timestamp):
    try:
        oldid_map = getPageRevIdAtTimestamp(title, timestamp)
    except KeyError as e:
        return False
    return True


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
    talk_templates = get_templates(talk_revid)
    wikiprojects = [tc.replace('WikiProject ', '')  for tc in talk_templates
                    if 'wikiproject' in tc.lower()]

    if wikiproject in wikiprojects:
        return True
    return False


def get_citation_stats(title, oldid):
    article_cites_rest_url = REST_API_URL % (title, oldid)
    
    resp = requests.get(article_cites_rest_url)
    citations = resp.json()

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
    revid_map = get_revid_at_timestamp(title, date)
    revid = revid_map[title]

    talk_revid_map = get_revid_at_timestamp('Talk:' + title, date)
    talk_revid = talk_revid_map['Talk:' + title]
    
    templates = get_templates(revid)
    assessments = get_assessments(title)

    stats = {'wikipedia_exists': revid,
             'wikidata_exists': get_article_wikidata_item(revid),
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
    print stats

    old_date = '2010-12-05T20:00:00Z'
    stats = get_all_stats(title, wikiproject, old_date)
    print stats
    
    import pdb;pdb.set_trace()

