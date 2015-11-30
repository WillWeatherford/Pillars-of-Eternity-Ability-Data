import re
import os
import csv
import time
import random
import requests
from bs4 import BeautifulSoup

DELAY = 1
MAIN_URL = 'http://pillarsofeternity.gamepedia.com'
ABIL_SUB = '/Category:Abilities'
ABIL_PAGE = '{}{}'.format(MAIN_URL, ABIL_SUB)

HAS_RE = re.compile(r'^\[\[[a-z\s]+::')
assert HAS_RE.match('[[has damage type::Crush]]')
assert HAS_RE.match('[[has defense::Reflex]]')

SUBCAT_ID = 'mw-subcategories'
SUBCAT_LINK_ID = 'CategoryTreeLabel CategoryTreeLabelNs14 CategoryTreeLabelCategory'

CAT_ID = 'mw-pages'

CSV_PATH = os.path.join('./', 'poe_abil_data.csv')


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
    page_soup = soup_from_url(url)
    table_div = page_soup.find('table', class_='infobox')
    if not table_div:
        print('Table Div not found at {}'.format(url))
        return {}
    rows = [r.find_all('td') for r in table_div.find_all('tr')]
    data = dict([tuple(map(get_strip, r)) for r in rows if len(r) == 2])
    header = table_div.find('th', class_='above')
    data['Ability Name'] = get_strip(header)
    return data


def get_strip(element):
    text = element.get_text().strip('\n').strip()
    match = HAS_RE.match(text)
    if match:
        text = text.strip(match.group()).strip(']]')
    return text


def write_to_csv(data, file_path, fieldnames):
    '''
    Writes data to a CSV document, using fieldnames argument
    constant as column headers.
    '''
    with open(file_path, 'wb') as output_csv:
        writer = csv.DictWriter(output_csv, fieldnames)
        writer.writeheader()
        writer.writerows(data)


def main():
    subcat_urls = get_subcat_urls(ABIL_PAGE)
    abil_urls = [abil_url for subcat_url in subcat_urls
                 for abil_url in get_abil_urls(subcat_url)]
    # now have one url per ability
    abil_data = [get_abil_data(url) for url in abil_urls]
    fieldnames = [k for row in abil_data for k in row.keys()]


def test():
    subcat_urls = get_subcat_urls(ABIL_PAGE)
    abil_urls = get_abil_urls(random.choice(subcat_urls))
    random.shuffle(abil_urls)
    abil_data = [get_abil_data(url) for url in abil_urls[:10]]
    fieldnames = {k for row in abil_data for k in row.keys()}
    # for d in abil_data:
    #     print('-------------------')
    #     for k, v in d.items():
    #         print('{}: {}'.format(k, v))
    write_to_csv(abil_data, CSV_PATH, fieldnames)
    print('Fieldnames:\n{}'.format(fieldnames))

if __name__ == '__main__':
    # main()
    test()
