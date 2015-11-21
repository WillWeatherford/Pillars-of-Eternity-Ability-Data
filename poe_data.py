import csv
import time
import requests
from bs4 import BeautifulSoup

DELAY = 1
MAIN_URL = 'http://pillarsofeternity.gamepedia.com'
ABIL_SUB = '/Category:Abilities'
ABIL_PAGE = '{}{}'.format(MAIN_URL, ABIL_SUB)

SUBCAT_ID = 'mw-subcategories'
SUBCAT_LINK_ID = 'CategoryTreeLabel CategoryTreeLabelNs14 CategoryTreeLabelCategory'

CAT_ID = 'mw-pages'


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
    page_soup = soup_from_url(url)
    table_div = page_soup.find('table', class_='infobox')

    rows = [r.find_all('td') for r in table_div.find_all('tr')]
    tuples = [(r[0].get_text(), r[1].get_text()) for r in rows if len(r) == 2]
    data = dict(tuples)

    header = table_div.find('th', class_='above')
    data['Ability Name'] = header.get_text()



def write_to_csv(data, file_path, fieldnames):
    '''
    Writes data to a CSV document, using fieldnames argument
    constant as column headers.
    '''
    with open(file_path, 'w') as output_csv:
        writer = csv.DictWriter(output_csv, fieldnames)
        writer.writerows(data)


def main():
    subcat_urls = get_subcat_urls(ABIL_PAGE)
    abil_urls = [abil_url for subcat_url in subcat_urls
                 for abil_url in get_abil_urls(subcat_url)]
    # now have one url per ability
    abil_data = [get_abil_data(url) for url in abil_urls]


if __name__ == '__main__':
    # main()
    data = get_abil_data(url)
    for k, v in data:
        print('{}: {}'.format(k, v))
