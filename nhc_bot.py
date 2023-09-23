from lxml import etree
from html2text import html2text
import requests
from bs4 import BeautifulSoup
from mastodon import Mastodon
from config import API_TOKEN, API_BASE_URL
import re
import argparse
import json

CURRENT_URL = 'https://www.nhc.noaa.gov/index-at.xml'


def process_item(item):
    """process one rss item into a dictionary"""
    return {x.tag: x.text for x in item}


def check_rss_updated(CURRENT_URL):
    our_headers = ["Last-Modified", "etag"]
    try:
        with open('status_data.json', 'r') as f:
            status_data = json.load(f)
    except:
        status_data = {}

    r = requests.head(CURRENT_URL)
    new_data = {key: r.headers[key] for key in our_headers}
    print(f"new etag {new_data['etag']}, old etag {status_data['etag']}")
    return any(status_data.get(x) != new_data.get(x)
               for x in our_headers), new_data


def write_new_status_data(status_data):
    with open('status_data.json', 'w') as f:
        json.dump(status_data, f)


def process_url(url):
    """use lxml to extract the items and process into dicts"""
    r = requests.get(url)
    mytree = etree.fromstring(r.content)
    theitems = mytree.getchildren()[0].findall('item')
    return [process_item(x) for x in theitems]


def process_data(data_list):
    """extract the needed data for Mastodon"""
    out = {}
    out['full_advisory_link'] = data_list[2]['link']
    out['full_advisory_title'] = data_list[2]['title']
    out['summary_title'] = data_list[1]['title']
    out['summary'] = html2text(data_list[1]['description']).replace('\n', ' ')
    soup = BeautifulSoup(data_list[6]['description'], 'html.parser')
    out['graphic_data'] = requests.get(soup.find('img')['src']).content
    out['graphic_link'] = soup.find('a')['href']
    return out


def make_post_content(data_for_post):
    """with the data dictionary, create the text for the post."""
    clean_title = re.sub(r"\(.+\)", '',
                         data_for_post['summary_title']).strip().replace(
                             "Tropical Storm", 'T.S.')
    pattern = r'\.\.\.(.*?)\.\.\.'

    # Use re.sub() to remove the ellipsis and replace with the captured text and a single period
    cleaner_summary = re.sub(pattern, r'\1.', data_for_post['summary'])

    sentences = cleaner_summary.split(". ")

    non_headline = ". ".join(sentences[2:])

    rem = re.match(r"Tropical Storm (\S+) Public Advisory Number (.+)",
                   data_for_post['full_advisory_title'])
    advisory_number = rem.group(2)

    ### F String
    post_content = (
        f"{clean_title}\n\n"
        f"{sentences[0].strip()}.\n\n"
        f"{sentences[1].strip()}.\n\n"
        f"{non_headline}\n\n"
        f"Graphics: {data_for_post['graphic_link']}\n"
        f"Advisory {advisory_number}: {data_for_post['full_advisory_link']}\n\n"
        f"#{rem.group(1)}")

    return post_content


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('--nopost', action='store_true', default=False)

    args = parser.parse_args()
    is_updated, status_data = check_rss_updated(CURRENT_URL)
    if is_updated:

        data_for_post = process_data(process_url(CURRENT_URL))
        post_content = make_post_content(data_for_post)

        if not args.nopost:
            m = Mastodon(access_token=API_TOKEN,
                         api_base_url='https://vmst.io')
            med_dict = m.media_post(data_for_post['graphic_data'],
                                    mime_type='image/png')
            out = m.status_post(post_content, media_ids=med_dict)
            print(
                f"Succesfully posted post id {out['id']} at {out['created_at']}. URL: {out['url']}"
            )
            write_new_status_data(status_data=status_data)
        else:
            print(post_content)
            print(f"Length: {len(post_content)}")
    else:
        print("No updated feed data.")
