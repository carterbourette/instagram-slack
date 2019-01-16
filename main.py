#!/usr/bin/env python3

"""A simple python web scraper to pull instagram content into slack."""

import requests
import sys, re, json, time
from datetime import datetime
from bs4 import BeautifulSoup

class InstagramCrawler:
    """A container to hold the Instagram crawling logic"""

    class Post:
        """Create a value object to hold the contents of the post."""

        def __init__(self, id='', usr='', msg='', additional='', img_url=''):
            self.id = id
            self.usr = usr
            self.msg = msg
            self.additional = additional
            self.img_url = img_url

        def serialize(self):
            if self.img_url and self.additional:
                return '{ "text": "%s", "attachments": [ { "text": "%s", "image_url": "%s" } ] }' % (self.msg, self.additional, self.img_url,)
            elif self.img_url:
                return '{ "text": "%s", "attachments": [ {"image_url": "%s" } ] }' % (self.msg, self.img_url,)
            return '{ "text": "%s", "unfurl_media": true, "unfurl_links": true }' % (self.msg,)


    def __init__(self, links, file_path='.instagram-crawler', api_hook=None):
        self.blacklist_dictionary = {}

        self.base_url = 'https://www.instagram.com'
        self.file_path = file_path
        self.api_hook = api_hook
        self.links = links


    def _startup(self):
        """Load the blacklisted into memory."""
        try:
            with open(self.file_path, 'r') as file:
                self.blacklist_dictionary = json.loads(file.read())
                file.close()
        except: pass


    def _cleanup(self):
        """Write the blacklist to disk."""
        with open(self.file_path, 'w') as file:
            self.blacklist_dictionary['updated'] = str(datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
            file.write(json.dumps(self.blacklist_dictionary))
            file.close()


    def is_safe_id(self, username, id):
        """Check to see if a users post id is blacklisted."""
        return not self.blacklist_dictionary.get(username, None) == id


    def blacklist_id(self, username, id):
        """Blacklist a new id."""
        self.blacklist_dictionary['latest_post'] = str(datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
        self.blacklist_dictionary[username] = id


    def send(self, post):
        """Send the post to slacks API"""
        # Put together the POST payload, and save emojis by encode using utf-8
        body = post.serialize()

        # Shoot the message to slack using the hook we setup at <workspace>.slack.com
        r = requests.post(self.api_hook, headers={'Content-Type': 'application/json'}, data=body.encode('utf-8'))

        # Add the post id to the blacklist
        self.blacklist_id(post.usr, post.id)

        # A time delay gives slack time to crawl between posts
        time.sleep(15)


    def start(self):
        """Run the crawler."""

        self._startup()
        # For each instagram account
        for link in self.links:

            # Get the html code and pipe into our html parser
            r = requests.get(link)

            soup = BeautifulSoup(r.text, 'html.parser')

            # Search through all of the script tags on the page to find the one with the data
            for a in soup.find_all('script'):
                test_string = str(a)

                # Find the definition of the "sharedData" variable and parse out the JSON
                if re.search('window._sharedData = {', str(test_string)):
                    # Discard the javascript code from the JSON object
                    start = test_string.find('{')
                    end = test_string.rfind('}') + 1

                    json_document = test_string[start:end]

                    # With the JSON doc, compile all the data we need for the slack post
                    # Note: we're going to ignore any key errors
                    # TODO: Find a way to .get(var, None) of nested dicts
                    try:
                        dictionary = json.loads(json_document)
                        user_dictionary = dictionary['entry_data']['ProfilePage'][0]['graphql']['user']
                        most_recent_post_dictionary = user_dictionary['edge_owner_to_timeline_media']['edges'][0]['node']

                        # Gather data to send to slack
                        id = most_recent_post_dictionary.get('id')
                        username = user_dictionary.get('username')
                        image = None
                        additional_text = None

                        # If the post is a video we'll let slack unfurl it
                        if most_recent_post_dictionary.get('is_video'):
                            message = self.base_url + '/p/' + most_recent_post_dictionary.get('shortcode') + ' '
                        # Otherwise, we'll format the post as per slacks guidelines
                        else:
                            message = 'A new post from <%s/%s| @%s>' % (self.base_url, username, username)
                            image = most_recent_post_dictionary.get('display_url')

                            additional_text = most_recent_post_dictionary['edge_media_to_caption']['edges'][0]['node']['text']

                        post = InstagramCrawler.Post(id, username, message, additional_text, image)

                        # Check to see if the post is blacklisted, otherwise ship it
                        if self.is_safe_id(post.usr, post.id):
                            self.send(post)

                    except Exception as err:
                        pass

                    # We can stop looking now
                    break

        # Cleanup/write our internal state when we finish
        self._cleanup()


def main(argv):
    if len(argv) < 3:
        print('usage: python main.py [file location] [slack hook] [url to follow] [url to follow] ...')
        sys.exit(1)

    # Parse command line args
    config = argv[1]
    api_hook = argv[2]
    links = argv[3:]

    # Create the crawler object and begin crawling
    crawler = InstagramCrawler(file_path=config, api_hook=api_hook, links=links)
    crawler.start()


# When the script is run directly callout to the executable logic
if __name__ == "__main__":
    main(sys.argv)
