import re
import os
import csv
import time
import random
import requests
import argparse
from bs4 import BeautifulSoup, NavigableString

DELAY = 10
MAIN_URL = 'http://pillarsofeternity.gamepedia.com'
ABIL_SUB = '/Category:Abilities'
ABIL_PAGE = '{}{}'.format(MAIN_URL, ABIL_SUB)

HAS_RE = re.compile(r'^\[\[[A-Za-z\s]+::')
assert HAS_RE.match('[[has defense::fortitude]]')
assert HAS_RE.match('[[has damage type::Crush]]')
assert HAS_RE.match('[[has defense::Reflex]]')

SUBCAT_ID = 'mw-subcategories'
SUBCAT_LINK_ID = 'CategoryTreeLabel CategoryTreeLabelNs14 CategoryTreeLabelCategory'

CAT_ID = 'mw-pages'

CSV_PATH = os.path.join('./', 'poe_abil_data.csv')


CLASSES = [
    'Barbarian'
    'Chanter'
    'Cipher'
    'Druid'
    'Fighter'
    'Monk'
    'Paladin'
    'Priest'
    'Ranger'
    'Rogue'
    'Wizard'
]


def soup_from_url(url):
    time.sleep(DELAY)
    response = requests.get(url)
    soup = BeautifulSoup(response.text)
    return soup


def get_subcat_urls(url):
    abil_soup = soup_from_url(url)
    subcat_div = abil_soup.find('div', id=SUBCAT_ID)
    links = subcat_div.find_all('a', class_=SUBCAT_LINK_ID)
    urls = ['{}{}'.format(MAIN_URL, l.get('href')) for l in links]
    return urls

# combine these functions? use args and kwargs


def get_abil_urls(url):
    page_soup = soup_from_url(url)
    cat_div = page_soup.find('div', id=CAT_ID)
    links = cat_div.find_all('a')
    urls = ['{}{}'.format(MAIN_URL, l.get('href')) for l in links]
    return urls


def get_abil_data(url):
    print('Getting ability data from {}'.format(url))
    data = {}
    page_soup = soup_from_url(url)
    table_div = page_soup.find('table', class_='infobox')
    if not table_div:
        print('Table Div not found at {}'.format(url))
        return data

    header = table_div.find('th', class_='above')
    data['Ability Name'] = get_text(header)

    rows = [r.find_all('td') for r in table_div.find_all('tr')]
    for row in rows:
        if len(row) == 2:
            data[get_text(row[0])] = get_text(row[1])
    return data


def get_text(element):
    # if it has a "warning" element, remove that
    error = element.find('span', attrs={'data-title': 'Error'})
    if error:
        error.decompose()
    if isinstance(element, NavigableString):
        text = unicode(element)
        text.replace(u'\xb0', u'degree')
    else:
        text = element.get_text()
    print('Text before: {}'.format(text))
    text = text.replace('\n', ' ').replace(']]', '').strip().encode('utf8')
    print('Text before regex match: {}'.format(text))
    match = HAS_RE.match(text)
    if match:
        print('Match.group(): {}'.format(match.group()))
        text = text.replace(match.group(), '', 1)
        print('Text after regex match: {}'.format(text))
    return text


def write_to_csv(data, file_path):
    '''
    Writes data to a CSV document, using fieldnames argument
    constant as column headers.
    '''
    fieldnames = list({k for row in data for k in row.keys()})
    i = fieldnames.index('Ability Name')
    an = fieldnames.pop(i)
    fieldnames.insert(0, an)
    print('Fieldnames:\n{}'.format(fieldnames))
    with open(file_path, 'wb') as output_csv:
        writer = csv.DictWriter(output_csv, fieldnames)
        writer.writeheader()
        writer.writerows(data)


def scrape_wiki():
    subcat_urls = get_subcat_urls(ABIL_PAGE)
    abil_urls = [abil_url for subcat_url in subcat_urls
                 for abil_url in get_abil_urls(subcat_url)]
    return [get_abil_data(url) for url in abil_urls]


def main(**kwargs):
    print('main() called.')
    print('args: {}'.format(kwargs))
    print('kwargs: {}'.format(kwargs))
    abil_data = scrape_wiki()
    write_to_csv(abil_data, CSV_PATH)


def test(num=10, **kwargs):
    print('test() called.')
    print('args: {}'.format(kwargs))
    print('kwargs: {}'.format(kwargs))
    subcat_urls = get_subcat_urls(ABIL_PAGE)
    abil_urls = get_abil_urls(random.choice(subcat_urls))
    random.shuffle(abil_urls)
    abil_data = [get_abil_data(url) for url in abil_urls[:num]]
    write_to_csv(abil_data, CSV_PATH)


# use sub-parser to call a function straight from a positional arg.
def parse_args():
    parser = argparse.ArgumentParser(description='Take specifications on PoE data to find.')
    # parser.add_argument('command', type=str, help='Command option.',
    #                     choices=['test', 'scrape', 'random'])
    # parser.add_argument('num', type=int, help='Number of abilities to find.', default=9999)
    parser.add_argument('-T', '--test', action='store_true', help='Run in test mode, finding 10 abilities of a random class.')
    parser.add_argument('-n', '--name', type=str, help='Filter on a specific ability by name.')
    parser.add_argument('-c', '--class', type=str,
                        help='Filter on a specific character class.')
    parser.add_argument('-t', '--target', type=str, help='Filter on a specific target type.')
    parser.add_argument('-D', '--damage', type=str, help='Filter on a specific damage type.')
    args = parser.parse_args()
    print(args)
    print(type(args))
    print(dir(args))
    print(vars(args))
    return vars(args)


if __name__ == '__main__':
    kwargs = parse_args()
    if kwargs.get('test'):
        test(**kwargs)
    else:
        main(**kwargs)


# positional args:
# none - display existing info
# scrape - get info from web
#
# optional flags (for column headers)
# -c --class = show or get info only for that class
# -d --damagetype = show or get info only on that damagetype
# -f --defendedby
# level, target type etc
#
