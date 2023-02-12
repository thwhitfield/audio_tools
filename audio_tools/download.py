"""Functions which can be used to download mp3s from a website, especially from the history of
rome website."""

import requests
from bs4 import BeautifulSoup
import re
from pathlib import Path
from urllib.request import urlopen

def get_list_of_mp3s_from_url(url):
    """Get list of all the mp3s from a url

    Args:
        url (str): Url to scrape all mp3 links from

    Returns:
        mp3_list (list of str): List of the scraped mp3 links
    """

    r = requests.get(url)
    soup = BeautifulSoup(r.content, 'html.parser')

    mp3_list = []
    
    for a in soup.find_all('a', href=re.compile(r'http.*\.mp3')):
        mp3_list.append(a['href'])
    
    return mp3_list

def download_list_of_mp3_urls(mp3_list, output_folder = '.'):
    """Download a list of mp3s from the provided list of urls.
    
    Args:
        mp3_list (list of str): List of urls to the mp3s which are to be downloaded
        output_folder (str): Path to the output folder where the files should be downloaded.
            (Default: '.')

    Returns:
        None
    """

    for url in mp3_list:
        filename = url.split('/')[-1]
        filepath = Path(output_folder) / filename

        r = urlopen(url)

        with open(filepath, 'wb') as f:
            f.write(r.read())

def get_history_of_rome_mp3_urls(rome_archive_url = 'https://thehistoryofrome.typepad.com/the_history_of_rome/archives.html'):
    """Get list of all the history of rome mp3 files by scraping the history of rome archives
    page.
    
    Args:
        rome_archive_url (str): Link to the history of rome url. (Default: 'https://thehistoryofrome.typepad.com/the_history_of_rome/archives.html')

    Returns:
        mp3_links (list): 
    """

    r = requests.get(rome_archive_url)
    soup = BeautifulSoup(r.content, 'html.parser')

    archive_links = [li.contents[0]['href'] for li in soup.find_all('li', attrs = {'class':'archive-list-item'})]

    mp3_links = []

    for link in archive_links:
        mp3_links = mp3_links + get_list_of_mp3s_from_url(link)

    mp3_links = [link for link in mp3_links if 'historyofrome' in link]

    return mp3_links
