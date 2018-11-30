import re
from collections import namedtuple
import requests

def getPageRevIdAtTimestamp(titles, timestamp):
    """Get page revision id at a particular timestamp

    :param titles: a list of page titles
    :param timestamp: in the form of ISO8601 '2018-11-29T20:09:07Z'
    :return: a map from page title to the revision id
    """
    resp = requests.get('https://en.wikipedia.org/w/api.php', params={
        'action': 'query',
        'prop': 'revisions',
        'format': 'json',
        'titles': '|'.join(titles),
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