# to do:
# better result printing for query
# nice formatted excel data? colors, sorted, specific col header values
# gather definitions from data e.g. for target options

# better use of Type (Talent, wizard spell, priest spell, aura, Command,
#    phrase, invocation)
# decoding of percentage and degree signs
# some wrong values e.g. damage type = Average for Arduous delay
# missing + sign on accuracy for spells

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

ABIL_TYPES = [
    'Talent', 'Spell', 'Power', 'Phrase', 'Invocation', 'Command', 'Aura'
]
CLASSES = [
    'Barbarian', 'Chanter', 'Cipher', 'Druid', 'Fighter', 'Monk', 'Paladin',
    'Priest', 'Ranger', 'Rogue', 'Wizard'
]
DAMAGE_TYPES = [
    'Burn', 'Freeze', 'Shock', 'Corrode', 'Pierce', 'Crush', 'Slash', 'Raw'
]
DEFENSES = ['Deflection', 'Fortitude', 'Reflex', 'Will']
TARGETS = ['AoE', 'Caster', 'Target']


FIELDNAMES = [
    'Ability Name', 'Class', 'Type', 'Character Level', 'Ability Level', 'Learning Costs', 'Requirements',
    'Activation', 'Uses', 'Resources', 'Activation Requirements',
    'Area/Target', 'Range', 'Accuracy', 'Casting Time',
    'Defended by', 'Damage Type', 'Damage', 'Interrupt',
    'Effects', 'Duration', 'Linger',
    'Influenced Item', 'Influenced Ability', 'Influenced Talent',
]

CPS_KEYS = [
    'Value', 'Equipment Slot', 'Combat Type', 'Abilities', 'Enchantment',
    'Bonus', 'Handing', 'Enhancements', 'Max. stack'
]

USELESS_KEYS = [
    "'", 'Internal name', 'Restoration', 'Related Talents', 'Talents', 'Speed'
]

USELESS_KEYS.extend(CPS_KEYS)


KEY_PATTERNS = [

    (r'^([\sA-Za-z/]+)$',
     lambda k, v: (k.title(),
                   re.sub(r'^\[\[has\s([\sa-z]+)::(?P<value>[^\]]+)\]\]',
                          lambda m: m.group('value'),
                          re.sub(r'\[\d\]$', '', v), flags=re.I))),

    (r"^(" + "|".join(USELESS_KEYS) + ")$",
     lambda k, v: ('', '')),

    (r'^(Effect)$',
     lambda k, v: ('Effects', v)),

    (r'^Learning Costs$',
     lambda k, v: (k,
                   re.sub(r'(?P<num>\d{1,5})(\s)?(?P<cp>cp)',
                          lambda m: ' '.join((m.group('num'), m.group('cp'))),
                          v, flags=re.I))),

    (r'^Activation Requirements$',
     lambda k, v: (k,
                   re.sub(r'.*(Combat).*', 'Combat Only', v, flags=re.I))),

    (r'^(Speed|Casting Time)$',
     lambda k, v: ('Casting Time',
                   re.sub(r'^Immediate$', 'Instant', v, flags=re.I))),

    (r'^(Power|Spell|Invocation|Phrase)\sLevel$',
     lambda k, v: ('Ability Level', v)),

    (r'^(Wounds|Phrases|Focus)$',
     lambda k, v: ('Resources', ' '.join((v, k)))),

    (r'^Influenced\s(Ability|Talent)$',
     lambda k, v: ('Influenced Ability/Talent', v)),

    # GOOD
    (r'^(Learned)$',
     lambda k, v: ('Character Level', ''.join([c for c in v if c.isdigit()]))),

    (r'^Group$',
     lambda k, v: ('Class',
                   re.sub(r'(-specific|Class-neutral|Rewarded Talent)', '',
                          v, flags=re.I))),

    (r'^((Effect|Damage)\s)?Defended By$',
     lambda k, v: ('Defended By',
                   re.sub(r'^(?P<target>' + list_pat(DEFENSES) + ').+target.+(?P<aoe>' + list_pat(DEFENSES) + ').+(explosion|area|blast).*$',
                          lambda m: ''.join((m.group('target'), ' (Target), ', m.group('aoe'), ' (AoE)')),
                          re.sub(r'Reflexes', 'Reflex', v, flags=re.I)))),

    # 'Reflexes for damage, Will for affliction.',
    # 'Reflexes for damage and Fortitude for status effect.'
    # ends up with a period at the end for some of them

    (r'^Damage Type$',
     lambda k, v: (k, re.sub(r'ignores armor', 'Raw', v, flags=re.I))),

    (r'^Interrupt$',
     lambda k, v: (k, re.sub(r'(\s?sec(onds)?)', ' sec',
                             re.sub(r'\([a-z]+\)', '', v, flags=re.I),
                             flags=re.I))),

    (r'^Duration$',
     lambda k, v: (k, re.sub(r'(\ssec(onds)?|\(?base\)?\s|over\s|\.0)', '', v,
                             flags=re.I))),

    (r'^Area/Target$',
        lambda k, v: (k, re.sub(r'roe only', 'Foe Only',
                                re.sub(r'Cricle', 'Circle', v, flags=re.I),
                                flags=re.I)))

    # Range: standardize 10.0m, 10, 10 m, --> 10m
    # Requirements: move level to "Character Level"

]

list_pat = lambda l: r'(' + '|'.join(l) + ')'
group_list_pat = lambda l: list_pat([r'(?P<{}>{})'.format(k, p) for k, p in l])

ABIL_TYPES_PATTERN = list_pat(ABIL_TYPES)


ALIGN_PATTERNS = [
    ('Foe', r'(foe|enem(y|ies))\s(only)?'),
    ('Friendly', r'friendly|all(y|ies)'),
    # ('Hazard', r".*[^" + list_pat([FOE_PATTERN, FRIENDLY_PATTERN]) + "]")
    ('Hazard', r'(any|every)(one|body)|hazard|(any|all) in the area'),
    ('Self', r'self')
]

TARGET_PATTERNS = [
    ('Cone', r'cone'),
    ('Aura', r'from\scaster|aura'),
    ('AoE', r'aoe|circle|area|radius'),
    ('Target', r'single|target|an emeny|an ally'),
]

ALIGN_PATTERNS = group_list_pat(ALIGN_PATTERNS)
TARGET_PATTERNS = group_list_pat(TARGET_PATTERNS)
AREA_PATTERN = r'(?P<radius>\d{1,2}(\.\d{1,2})?)(\s)?m?(\s(wall|radius|circle|area(\sof\seffect)?|aoe))?'


# Improvements:
#   some spells have multiple target types
#       split on '+'
#   30m Wall instead of Radius
#   if self, no Foe, Ally etc
def parse_area_target(string):
    if not string:
        return ''

    matches = [re.search(pat, string, flags=re.I)
               for pat in (ALIGN_PATTERNS, TARGET_PATTERNS)]
    aligns, targets = [', '.join([k for k, v in m.groupdict().items() if v])
                       if m else '' for m in matches]
    # types = [[k for k, v in m.groupdict().items() if v][0] if m else '' for m in matches ]

    target_val = join_data(aligns, targets, ' ')

    area_match = re.search(AREA_PATTERN, string, flags=re.I)
    area_val = ''.join((area_match.group('radius'),
                        'm Radius')) if area_match else ''

    print('aligns: {}\ntargets: {}\narea: {}\n'.format(aligns, targets,
                                                       area_val))
    return target_val, area_val


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
    scrape_parser.add_argument('-t', '--talents', action='store_false',
                               help='Ignore talents in scraping, mostly for '
                               'testing purposes.')
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
            and row['Area/Target'] in targets
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
                talents=True, overwrite=True, **kwargs):
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

    if talents:
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
            for pattern, func in KEY_PATTERNS:
                if re.match(pattern, key, flags=re.I):
                    # print('pattern match')
                    # print('before: {}: {}'.format(key, val))
                    key, val = func(key, val)
                    # print('after: {}: {}'.format(key, val))
            if key and not key.isspace() and not val.isspace():
                data[key] = val

    description_p = table_div.find_next_sibling('p')
    if description_p:
        data['Description'] = get_text(description_p)

    data['Uses'] = join_data(data['Uses'], data.pop('Restoration', ''), ' ')
    data['Effects'] = join_data(data['Effects'], data.pop('Changes', ''), '; ')
    data['Target'], data['Area'] = parse_area_target(
        ' '.join((data['Area/Target'], data['Description'])))

    if not data['Type']:
        data['Type'] = get_type(page_soup)

    return data


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


def join_data(val1, val2, joiner):
    if not (val1 and val2):
        joiner = ''
    return joiner.join((val1, val2))


def get_type(page_soup):
    cat_div = page_soup.find('div', attrs={'id': 'catlinks',
                                           'class': 'catlinks'})
    try:
        links = cat_div.find_all('li')
        text = ' '.join([get_text(li) for li in links])
        match = re.match(ABIL_TYPES_PATTERN, text, flags=re.I)
        return match.group()
    except AttributeError:
        return ''


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
