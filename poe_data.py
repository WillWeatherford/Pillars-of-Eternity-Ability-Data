# to do:
# better result printing for query
# nice formatted excel data? colors, sorted, specific col header values
# gather definitions from data e.g. for target options

# combine "Changes" and influenced ability/item?
# better use of Type (Talent, wizard spell, priest spell, aura, exhortation,
#    phrase, invocation)
# decoding of percentage and degree signs
# merge "Changes" with "Effects" ?

# fix:
# Damage : [[has damage::18-35 + Might*2% (Extra Damage)]]

# Fieldnames

# Ability Name    Requirements    Casting Time    Damage  Learning costs
# Max. stack  Area/Target Type    Resources   Accuracy    Damage Type
# Influenced Talent   Activation  Linger  Uses    Effects Interrupt
# Activation Requirements Class   Damage type Level   Ability level
# Range   Changes Defended by Influenced Item Influenced Ability  Duration


import re
import os
import csv
import time
import random
import requests
import argparse
from collections import defaultdict
from bs4 import BeautifulSoup, NavigableString

DELAY = 10
MAX_TRIES = 10
MAIN_URL = 'http://pillarsofeternity.gamepedia.com'
CAT = '/Category:{}'
CAT_SUB = ''.join((MAIN_URL, CAT))
CLASS_ABIL_SUB = '_'.join((CAT_SUB, 'abilities'))
ABIL_PAGE = CAT_SUB.format('Abilities')
TALENT_PAGE = CAT_SUB.format('Talents')

CHAR_CLASS_ID = 'mw-subcategories'
CHAR_CLASS_LINK_ID = ' '.join(('CategoryTreeLabel',
                               'CategoryTreeLabelNs14',
                               'CategoryTreeLabelCategory'))
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

CPS_KEYS = [
    'Value', 'Equipment slot', 'Combat Type', 'Abilities', 'Enchantment',
    'Bonus', 'Handing', 'Enhancements', 'Max. stack'
]

USELESS_KEYS = [
    'Restoration', 'Related Talents', 'Talents', 'Speed'
]

USELESS_KEYS.extend(CPS_KEYS)

HAS = ('damage', 'defense', 'damage type', 'duration', 'effect(s)?')

KEY_PATTERNS = {
    r"^(Internal name|')$":
        lambda k, v: ('', ''),

    r'^(Effect)$':
        lambda k, v: ('Effects', v),

    r'^(Speed)$':
        lambda k, v: ('Casting Time', v),

    r'^(Effect|Damage) defended by$':
        lambda k, v: ('Defended by', v),

    r'^(Power|Spell|Invocation|Phrase) level$':
        lambda k, v: ('Ability level', v),

    r'^(Wounds|Phrases|Focus)$':
        lambda k, v: ('Resources', ' '.join((v, k))),

    r'^(Learned)$':
        lambda k, v: ('Char Level', ''.join([c for c in v if c.isdigit()])),

    r'^Group$':
    lambda k, v: ('Class', re.sub(
                  r'^(?P<class>' + '|'.join(CLASSES) + ')-specific',
                  lambda m: m.group('class'), v, flags=re.I)),

    r'^(Duration|Defended by|Damage(\stype)?|Effect(s)?)$':
        lambda k, v: (k.capitalize(), re.sub(
            r'^\[\[has (' + r'|'.join(HAS) + ')::(?P<value>[^\]]+)\]\]',
            lambda m: re.sub(r'ignores Armor', 'Raw', m.group('value'),
                             flags=re.I),
            v, flags=re.I)),
}

HAS_PAT = r'^\[\[has (' + r'|'.join(HAS) + ')::(?P<value>[^\]]+)\]\]'
D_EXAMPLE = '[[has damage::1-6 + Might*2% (Extra Damage)]]'
RESULT = '1-6 + Might*2% (Extra Damage)'

assert re.match(r'Damage(\stype)?', 'Damage')
assert re.match(r'Damage(\stype)?', 'Damage type')
assert re.match(HAS_PAT, D_EXAMPLE)
assert re.sub(HAS_PAT, lambda m: m.group('value'), D_EXAMPLE) == RESULT


class ArgMatch(argparse.Action):
    def __call__(self, parser, namespace, values, option_string):
        print 'ArgMatch called; self.default: {}'.format(self.default)
        new_values = [d for d in self.default for v in values
                      if len(v) > 1 and re.compile(v, re.I).match(d)]
        setattr(namespace, self.dest, new_values)


def defaults_from_data(data, key):
    return {row.get(key, '').title() for row in data}


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
    scrape_parser.add_argument('-c', '--classes', type=str, nargs='*',
                               default=CLASSES, action=ArgMatch,
                               help='Filter on specific char classes. Separate'
                               ' classes by spaces, e.g. "Wizard monk".')

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
    query_parser.add_argument('-v', '--verbosity', type=int, default=0,
                              help='Filter on specific defenses. Separate '
                              'defenses by spaces, e.g. "will Reflex".')

    args = parser.parse_args()
    print(args)
    print(vars(args))
    return vars(args)


def main(argcheck=False, func=None, **kwargs):
    print('main() called.')
    if argcheck:
        return
    if func:
        func(CSV_PATH, **kwargs)


def read_from_csv(file_path):
    with open(file_path, 'r') as input_csv:
        reader = csv.DictReader(input_csv)
        return [row for row in reader]


def query(file_path, verbosity=0, name=None, classes=CLASSES,
          damage_types=DAMAGE_TYPES, defenses=DEFENSES, targets=TARGETS,
          *args, **kwargs):
    print('query() called.')
    data = read_from_csv(file_path)
    targets = defaults_from_data(data, 'Area/Target')
    if name:
        try:
            print(data[name])
            return
        except KeyError:
            raise KeyError('Ability named "{}" is not found in the database.'
                           ''.format(name))
    # data = data.values()
    data = [row for row in data if row
            and row['Class'] in classes
            and row['Damage type'] in damage_types
            and row['Defended by'] in defenses
            and row['Area/target'] in targets
            ]
    print('{} Query Results Found:'.format(len(data)))
    for row in data:
        if not verbosity:
            print(row['Ability Name'])
        else:
            for k, v in row.items():
                if v:
                    print(': '.join((k, v)))


def scrape_wiki(file_path, test=False, classes=CLASSES, num=9999,
                overwrite=True, **kwargs):
    '''
    Makes HTML requests to pillarsofeternity.gamepedia.com, gathering urls
    for each character class, then urls for each ability of that class.
    Finally returns a list of dictionaries; each dictionary holds the data
    for an ability.
    '''
    if test:
        num = 10
        classes = [random.choice(CLASSES)]

    char_class_urls = get_char_class_urls(classes)
    abil_urls = {name: url for char_class_url in char_class_urls
                 for name, url in get_abil_urls(char_class_url).items()}

    abil_urls.update(get_abil_urls(TALENT_PAGE))

    wiki_data = [get_abil_data(name, url)
                 for name, url in abil_urls.items()[:num]]

    if overwrite:
        local_data = []
    else:
        local_data = read_from_csv(file_path)
    # if overwrite is true vs false?
    # if overwrite is false:
    # check ability name along with link. if abil name is already in local
    # data, ignore it
    wiki_data.extend(local_data)

    final_data = filter(None, wiki_data)

    write_to_csv(final_data, file_path)


def soup_from_url(url, tries=0):
    # print('Requesting {}...'.format(url))
    time.sleep(DELAY)
    try:
        response = requests.get(url)
        soup = BeautifulSoup(response.text)
        return soup
    except requests.RequestException as e:
        if tries >= MAX_TRIES:
            raise e
        return soup_from_url(url, tries + 1)


def get_char_class_urls(classes):
    return [CLASS_ABIL_SUB.format(c) for c in classes]


def get_abil_urls(url, div_attrs={}, link_attrs={}):
    page_soup = soup_from_url(url)
    div = page_soup.find('div', attrs={'id': CAT_ID})
    links = div.find_all('a')
    urls = {get_text(l): ''.join((MAIN_URL, l.get('href'))) for l in links}
    return {k: v for k, v in urls.items()
            if all((k, v, not k.isspace(), not v.isspace()))}


def get_abil_data(name, url):
    print('Getting ability data from {}'.format(url))
    page_soup = soup_from_url(url)
    table_div = page_soup.find('table', attrs={'class': 'infobox'})
    if not table_div:
        print('Table Div not found at {}'.format(url))
        return {}

    data = defaultdict(str, {'Ability Name': name})
    rows = [r.find_all(['td', 'th']) for r in table_div.find_all('tr')]
    print('{} infobox rows found for {}.'.format(len(rows), name))
    for row in rows:
        if len(row) == 2:
            key = get_text(row[0])
            val = get_text(row[1])
            for pattern, func in KEY_PATTERNS.items():
                if re.match(pattern, key, flags=re.I):
                    print('pattern match')
                    print('before: {}: {}'.format(key, val))
                    key, val = func(key, val)
                    print('after: {}: {}'.format(key, val))
            if key and not key.isspace() and not val.isspace():
                data[key] = val

    data['Uses'] = ' '.join((data['Uses'], data['Restoration']))
    for k in USELESS_KEYS:
        data.pop(k, None)

    # if page_soup finds Talent, data['Type'] = 'Talent'
    # Aura; Exhortation
    # Else data['Type'] = 'Ability'

    description_p = table_div.find_next_sibling('p')
    if description_p:
        data['Description'] = get_text(description_p)
    else:
        print('Description paragraph not found at {}'.format(url))

    return data


# Improvements:
# some wrong values e.g. damage type = Average for Arduous delay
# missing + sign on accuracy for spells

def get_text(element):
    '''
    Gather and parse text from a table cell element from a wiki info table.
    '''
    error = element.find('span', attrs={'data-title': 'Error'})
    if error:
        error.decompose()

    for br in element.find_all('br'):
        comma_string = NavigableString(', ')
        br.replace_with(comma_string)

    if isinstance(element, NavigableString):
        text = unicode(element, errors='ignore')
    else:
        text = element.get_text()
    text = text.replace('\n', ' ').strip().encode('utf8', errors='ignore')
    text = ''.join((text[:1].title(), text[1:]))
    # text = text.replace(u'\xb0', u'degree')
    # text = re.sub(HAS_VALUE_PATTERN, lambda m: m.group('value'), text)
    return text


def write_to_csv(data, file_path):
    '''
    Writes data to a CSV document, using fieldnames argument
    constant as column headers.
    '''
    print('writing {} rows to CSV'.format(len(data)))
    fieldnames = list({k for row in data for k in row.keys() if k})
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
