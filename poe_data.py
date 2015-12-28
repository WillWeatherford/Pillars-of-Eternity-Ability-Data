# to do:
# better result printing
# nice formatted excel data?
# gather definitions from data e.g. for target options
# collect Talents from wiki as well

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
CAT = '/Category:{}'
CAT_SUB = ''.join((MAIN_URL, CAT))
CLASS_ABIL_SUB = '_'.join((CAT_SUB, 'abilities'))
ABIL_PAGE = CAT_SUB.format('Abilities')
TALENT_PAGE = CAT_SUB.format('Talents')

HAS_RE = re.compile(r'(^\[\[[A-Za-z\s]+::)|\]\]')
assert HAS_RE.match('[[has defense::fortitude]]')
assert HAS_RE.match('[[has damage type::Crush]]')
assert HAS_RE.match('[[has defense::Reflex]]')

CHAR_CLASS_ID = 'mw-subcategories'
CHAR_CLASS_LINK_ID = 'CategoryTreeLabel CategoryTreeLabelNs14 CategoryTreeLabelCategory'
CAT_ID = 'mw-pages'

CSV_PATH = os.path.join('./', 'poe_abil_data.csv')

CLASSES = [
    'Barbarian', 'Chanter', 'Cipher', 'Druid', 'Fighter', 'Monk', 'Paladin',
    'Priest', 'Ranger', 'Rogue', 'Wizard'
]
DAMAGE_TYPES = [
    'Burn', 'Freeze', 'Shock', 'Corrode', 'Pierce', 'Crush', 'Slash', 'Raw'
]
DEFENSES = [
    'Deflection', 'Fortitude', 'Reflex', 'Will'
]
TARGETS = [
    'AoE', 'Caster', 'Target'
]

LEVEL_KEY_PATTERN = re.compile(r'(Power|Spell|Invocation) level', re.I)
DEFENSE_KEY_PATTERN = re.compile(r'(Effect|Damage) defended by', re.I)
NULL_KEY_PATTERN = re.compile(r"(Internal name|')")

KEY_PATTERNS = {
    LEVEL_KEY_PATTERN: 'Ability level',
    DEFENSE_KEY_PATTERN: 'Defended by',
    NULL_KEY_PATTERN: '',
}


class ArgMatch(argparse.Action):
    def __call__(self, parser, namespace, values, option_string):
        print 'ArgMatch called; self.default: {}'.format(self.default)
        new_values = [d for d in self.default for v in values
                      if len(v) > 1 and re.compile(v, re.I).match(d)]
        setattr(namespace, self.dest, new_values)


def defaults_from_data(data, key):
    return list({row.get(key, '').title() for row in data})


def parse_args():
    '''
    Parse command line arguments into **kwargs for the main function to
    distribute throughout the program, specifying data queries.
    '''
    parser = argparse.ArgumentParser(
        description='Take specifications on PoE data to find.')
    parser.add_argument('-A', '--argcheck', action='store_true',
                        help='Argument input check only.')

    subparser = parser.add_subparsers(help='Subcommands help.')

    # "scrape" subcommand and arguments
    scrape_parser = subparser.add_parser('scrape', help='Scrape data from '
                                         'wiki to update local data.')
    scrape_parser.set_defaults(func=scrape_wiki)
    scrape_parser.add_argument('-T', '--test', action='store_true',
                               help='Run in test mode, finding 10 abilities '
                               'of a random class.')
    scrape_parser.add_argument('-o', '--overwrite', action='store_true',
                               help='Overwrite local data with scraped data.')

    # "query" subcommand and arguments
    query_parser = subparser.add_parser('query', help='Query local data.')
    query_parser.set_defaults(func=query)
    query_parser.add_argument('-n', '--name', type=str,
                              help='Filter on a specific ability by name.')
    query_parser.add_argument('-c', '--classes', type=str, nargs='*',
                              default=CLASSES, action=ArgMatch,
                              help='Filter on specific char classes. Separate '
                              'classes by spaces, e.g. "Wizard monk".')
    # query_parser.add_argument('-t', '--target', type=str,
    #                           default=TARGETS, action=ArgMatch,
    #                           help='Filter on a specific target type.')
    query_parser.add_argument('-D', '--damage-types', type=str, nargs='*',
                              default=DAMAGE_TYPES, action=ArgMatch,
                              help='Filter on specific damage types. Separate '
                              'damage types by spaces, e.g. "crush pierce".')
    query_parser.add_argument('-d', '--defenses', type=str, nargs='*',
                              default=DEFENSES, action=ArgMatch,
                              help='Filter on specific defenses. Separate '
                              'defenses by spaces, e.g. "will Reflex".')

    args = parser.parse_args()
    print(args)
    print(vars(args))
    return vars(args)


def main(argcheck=False, test=False, func=None, **kwargs):
    print('main() called.')
    if argcheck:
        return
    if test:
        kwargs['num'] = 10
        kwargs['classes'] = [random.choice(CLASSES)]
    if func:
        func(CSV_PATH, **kwargs)


def read_from_csv(file_path):
    with open(file_path, 'r') as input_csv:
        reader = csv.DictReader(input_csv)
        return {row['Ability Name']: row for row in reader}


def query(file_path, name=None, classes=CLASSES, damage_types=DAMAGE_TYPES,
          defenses=DEFENSES, targets=TARGETS, *args, **kwargs):
    print('query() called.')
    data = read_from_csv(file_path)
    if name:
        try:
            print(data[name])
            return
        except KeyError:
            raise KeyError('Ability named "{}" is not found in the database.'
                           ''.format(name))
    data = data.values()
    data = [row for row in data if row
            and row['Class'] in classes
            and row['Damage type'] in damage_types
            and row['Defended by'] in defenses
            # and row['Area/Target'] in targets
            ]
    print('{} Query Results Found:'.format(len(data)))
    for row in data:
        for k, v in row.items():
            if v:
                print(': '.join((k, v)))


def scrape_wiki(file_path, classes=CLASSES, num=9999,
                overwrite=True, **kwargs):
    '''
    Makes HTML requests to pillarsofeternity.gamepedia.com, gathering urls
    for each character class, then urls for each ability of that class.
    Finally returns a list of dictionaries; each dictionary holds the data
    for an ability.
    '''
    char_class_urls = get_char_class_urls(classes)
    abil_urls = [abil_url for char_class_url in char_class_urls
                 for abil_url in get_abil_urls(char_class_url)]
    abil_urls.extend(get_abil_urls(TALENT_PAGE))
    wiki_data = dict([get_abil_data(url) for url in abil_urls[:num]])

    local_data = read_from_csv(file_path)
    # if overwrite is true vs false?
    # if overwrite is false:
    # check ability name along with link. if abil name is already in local
    # data, ignore it
    local_data.update(wiki_data)

    write_to_csv(local_data.values(), file_path)


def get_char_class_urls(classes):
    return [CLASS_ABIL_SUB.format(c) for c in classes]
    # return get_links_by_div(url, MAIN_URL,
    #                         div_attrs={'id': CHAR_CLASS_ID},
    #                         link_attrs={'class': CHAR_CLASS_LINK_ID})


def get_abil_urls(url):
    return get_links_by_div(url, div_attrs={'id': CAT_ID})


def get_links_by_div(page_url, div_attrs={}, link_attrs={}):
    page_soup = soup_from_url(page_url)
    div = page_soup.find('div', attrs=div_attrs)
    links = div.find_all('a', attrs=link_attrs)
    urls = [''.join((MAIN_URL, l.get('href'))) for l in links]
    return urls


def soup_from_url(url):
    print('Requesting {}...'.format(url))
    time.sleep(DELAY)
    response = requests.get(url)
    soup = BeautifulSoup(response.text)
    return soup


def get_abil_data(url):
    print('Getting ability data from {}'.format(url))
    data = {}
    page_soup = soup_from_url(url)
    table_div = page_soup.find('table', class_='infobox')
    if not table_div:
        print('Table Div not found at {}'.format(url))
        return '', data

    header = table_div.find('th', class_='above')
    abil_name = get_text(header)
    data['Ability Name'] = abil_name

    description_p = table_div.find_next_sibling('p')
    description = get_text(description_p)
    data['Description'] = description

    rows = [r.find_all('td') for r in table_div.find_all('tr')]
    for row in rows:
        if len(row) == 2:
            key = get_text(row[0])
            for pattern, better_key in KEY_PATTERNS.items():
                key = re.sub(pattern, better_key, key)
            val = get_text(row[1])
            if key and val:
                data[key] = val
    if not data.get('Effects', ''):
        data['Effects'] = description

    return abil_name, data


# Improvements:
# some wrong values e.g. damage type = Average for Arduous delay
# newline seperated in Effects mushed together
# some irrelevant e.g. internal_name
# query from edit page???
def get_text(element):
    '''
    Gather and parse text from a table cell element from a wiki info table.
    '''
    error = element.find('span', attrs={'data-title': 'Error'})
    if error:
        error.decompose()
    if isinstance(element, NavigableString):
        text = unicode(element)
        text = text.replace(u'\xb0', u'degree')
    else:
        text = element.get_text()
    text = text.replace('\n', ' ').strip().encode('utf8')
    text = re.sub(HAS_RE, '', text)
    return text


def write_to_csv(data, file_path):
    '''
    Writes data to a CSV document, using fieldnames argument
    constant as column headers.
    '''
    print('writing {} rows to CSV'.format(len(data)))
    fieldnames = list({k for row in data for k in row.keys()})
    i = fieldnames.index('Ability Name')
    an = fieldnames.pop(i)
    fieldnames.insert(0, an)
    print('Fieldnames:\n{}'.format(fieldnames))
    with open(file_path, 'wb') as output_csv:
        writer = csv.DictWriter(output_csv, fieldnames)
        writer.writeheader()
        writer.writerows(data)


if __name__ == '__main__':
    kwargs = parse_args()
    main(**kwargs)
