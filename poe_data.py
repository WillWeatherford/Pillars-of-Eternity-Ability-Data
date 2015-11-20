import csv
import requests
from bs4 import BeautifulSoup

DELAY = 1
MAIN_URL = 'http://pillarsofeternity.gamepedia.com'
ABIL_SUB = '/Category:Abilities'
ABIL_PAGE = '{}{}'.format(MAIN_URL, ABIL_SUB)

SUBCAT_ID = 'mw-subcategories'
SUBCAT_LINK_ID = 'CategoryTreeLabel'


def get_subcat_links(main_soup):
    subcat_div = main_soup.get('div', id=SUBCAT_ID)
    links = subcat_div.get_all('div', _class=SUBCAT_LINK_ID)
    urls = ['{}{}'.format(MAIN_URL, l.get('href')) for l in links]
    return urls


def get_main_soup():
    response = requests.get(ABIL_PAGE)
    soup = BeautifulSoup(response.text)
    return soup


def write_to_csv(data, file_path, fieldnames):
    '''
    Writes data to a CSV document, using fieldnames argument
    constant as column headers.
    '''
    with open(file_path, 'w') as output_csv:
        writer = csv.DictWriter(output_csv, fieldnames)
        writer.writerows(data)


def main():
    main_soup = get_main_soup()
    subcat_links = get_subcat_links(main_soup)
    for l in subcat_links:
        print(l)



if __name__ == '__main__':
    main()
