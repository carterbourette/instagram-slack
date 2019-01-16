#!/usr/bin/env python3
#----------------------------------------------------------------------------
# Author      : Carter Bourette
# Description : A simple python web scraper to pull instagram content into slack.
#               ...
#----------------------------------------------------------------------------
#
import urllib3
import sys, re, json, time
from datetime import datetime
from bs4 import BeautifulSoup

class InstagramCrawler:

    # Purpose: Create a value object to hold the contents of the post.
    class Post:
        def __init__(self, id='', usr='', msg='', additional='', img_url=''):
            self.id = id
            self.usr = usr
            self.msg = msg
            self.additional = additional
            self.img_url = img_url

        def serialize(self):
            if self.img_url and self.additional:
                return '{ "text": "'+str(self.msg)+'", "attachments": [ { "text": "'+str(self.additional)+'", "image_url": "'+str(self.img_url)+'" } ] }'
            elif self.img_url:
                return '{ "text": "'+str(self.msg)+'", "attachments": [ {"image_url": "'+str(self.img_url)+'" } ] }'
            return '{ "text": "'+self.msg+'", "unfurl_media": true, "unfurl_links": true }'


    def __init__(self, links, file_path='.instagram-crawler', api_hook=None):
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
        self.http = urllib3.PoolManager()
        self.blacklist_dictionary = {}

        self.file_path = file_path
        self.api_hook = api_hook
        self.links = links


    # -------------------------------------------
    # Purpose: Load the blacklisted into memory.
    # Passed-in: n/a.
    def _startup(self):
        try:
            with open(self.file_path, 'r') as file:
                self.blacklist_dictionary = json.loads(file.read())
                file.close()
        except: pass


    # -------------------------------------------
    # Purpose: Write the blacklist to disk.
    # Passed-in: n/a.
    def _cleanup(self):
        with open(self.file_path, 'w') as file:
            self.blacklist_dictionary['updated'] = str(datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
            file.write(json.dumps(self.blacklist_dictionary))
            file.close()



    # -------------------------------------------
    # Purpose: Check to see if a users post id is blacklisted.
    # Passed-in: username and post id.
    def is_safe_id(self, username, id):
        if username in self.blacklist_dictionary.keys() and self.blacklist_dictionary[username] == id:
            return False
        return True


    # -------------------------------------------
    # Purpose: Blacklist a new id.
    # Passed-in: username and post id.
    def blacklist_id(self, username, id):
        self.blacklist_dictionary['latest_post'] = str(datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
        self.blacklist_dictionary[username] = id


    # -------------------------------------------
    # Purpose: Send the post hooks to slacks API.
    # Passed-in: post object.
    def send(self, post):
        # Put together the POST payload, and save emojis by encode using utf-8
        body = post.serialize()

        # Shoot the message to slack using the hook we setup at <workspace>.slack.com
        r = self.http.request('POST', self.api_hook, headers={'Content-Type': 'application/json'},
                                body=body.encode('utf-8'))

        # Add the post id to the blacklist
        self.blacklist_id(post.usr, post.id)


    # -------------------------------------------
    # Purpose: Run the crawler.
    # Passed-in: n/a.
    def start(self):
        self._startup()
        # For each instagram account
        for link in self.links:

            # GET the html code and pipe into soup library
            r = self.http.request('GET', link)

            soup = BeautifulSoup(r.data, 'html.parser')

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
                    def _fetch_post(json_document):
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
                                message = 'https://www.instagram.com/p/' + most_recent_post_dictionary.get('shortcode') + ' '
                            # Otherwise, we'll format the post
                            else:
                                message = 'A new post from <http://instagram.com/' + username + '| @' + username + '>'
                                image = most_recent_post_dictionary.get('display_url')

                                additional_text = most_recent_post_dictionary['edge_media_to_caption']['edges'][0]['node']['text']
                        except Exception as err:
                            pass

                        # Create a post value object to pass to the message sender with the values from instagram
                        return InstagramCrawler.Post(id, username, message, additional_text, image)

                    post = _fetch_post(json_document)

                    # Check to see if the post is blacklisted, otherwise ship it
                    if self.is_safe_id(post.usr, post.id):
                        self.send(post)
                        time.sleep(15)

                    # We can stop looking now
                    break

        # Cleanup/write internal state
        self._cleanup()


#
# When the script is run directly
# Implement the crawler object
if __name__ == "__main__":
    if len(sys.argv) < 3:
        print('usage: python main.py [file location] [slack hook] [url to follow] [url to follow] ...')
        sys.exit(1)

    # Parse command line args
    config = sys.argv[1]
    api_hook = sys.argv[2]
    links = sys.argv[3:]

    # Create the crawler object and begin crawling...
    crawler = InstagramCrawler(file_path=config, api_hook=api_hook, links=links)
    crawler.start()
