import re
from collections import namedtuple
import requests


MW_API_URL = 'https://en.wikipedia.org/w/api.php'
REST_API_URL = 'https://en.wikipedia.org/api/rest_v1/page/references/%s/%s'


def getPageRevIdAtTimestamp(title, timestamp):
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
    return {page['title']: page['revisions'][0]['revid'] for page in resp['query']['pages'].values()}


def getTemplatesForRevision(oldid):
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
    revisionText = revisionResponse['parse']['text']['*']
    transclusionReport = revisionText[revisionText.find('<!--\nTransclusion expansion time report'):]
    TemplateCalls = namedtuple('TemplateCalls', ('template', 'calls'))
    templatePattern = re.compile(' (\d+) Template:(.*)\n', re.MULTILINE)
    matches = re.finditer(templatePattern, transclusionReport)

    return [TemplateCalls(match.group(2), int(match.group(1))) for match in matches]


def getCiteQStats(oldid):
    """Get citation stats that is using CiteQ vs non-CiteQ"""
    templatecalls = getTemplatesForRevision(oldid)
    noCiteQTemplates = {'Cite_web', 'Cite_web'}
    citeQTemplates = {'Cite_Q', 'Cite_q'}
    nonCiteQCounts = sum([entry.calls for entry in templatecalls if entry.template in noCiteQTemplates])
    citeQCounts = sum([entry.calls for entry in templatecalls if entry.template in citeQTemplates])
    return (citeQCounts, nonCiteQCounts)


def get_article_wikidata_item(oldid):
    params = {'action': 'query',
              'prop': 'wbentityusage',
              'revids': oldid,
              'format': 'json'}
    resp = requests.get(MW_API_URL, params)
    wbentities = resp.json()['query']['pages'].values()[0]['wbentityusage']
    # 'T' aspect means the Wikidata item corresponds to the title of the page
    # I'm assuming there is only corresponding Wikidata item; maybe that's
    # not safe?
    return [q for (q, val) in wbentities.items() if 'T' in val['aspects']][0]


def get_pageassessments(title):
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
        if 'infobox' in template_call.template.lower():
            return True
    return False


def check_infobox_wikidata(template_calls):
    wikidata_template_pattern = re.compile(r'infobox(.*)\/wikidata')
    for template_call in template_calls:
        if re.search(wikidata_template_pattern, template_call.template.lower()):
            return True
    return False


def check_wikiproject(wikiproject, assessments):
    if wikiproject in assessments.keys():
        return True
    return False


def get_citation_stats(title, oldid):
    article_cites_rest_url = REST_API_URL % (title, oldid)
    
    resp = requests.get(article_cites_rest_url)
    citations = resp.json()
    
    ref_count = len(citations['references_by_id'].keys())
    ref_wikidata_count = len([c for c in citations['references_by_id'].items()
                              if 'https://www.wikidata.org/wiki/Q'
                              in c[1]['content']['html']])
    ref_wikidata_percent = ref_wikidata_count / (ref_count * 1.0)
    
    return {'reference_count': ref_count,
            'reference_wikidata_count': ref_wikidata_count,
            'reference_wikidata_percent': ref_wikidata_percent}

if __name__ == '__main__':
    test_article = 'The Register-Guard'

    existence_2005 = check_existence(test_article, '2005-01-01T00:00:00Z')
    existence_2018 = check_existence(test_article, '2018-11-29T20:00:00Z')

    oldid_map = getPageRevIdAtTimestamp(test_article, '2018-11-30T00:00:00Z')
    oldid = oldid_map[test_article]    

    citation_stats = get_citation_stats(test_article, oldid)
    templates = getTemplatesForRevision(oldid)
    wd_item = get_article_wikidata_item(oldid)
    assessments = get_pageassessments(test_article)

    import pdb;pdb.set_trace()

