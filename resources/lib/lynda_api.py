import requests
import time
import hashlib
import urllib
import math


class LyndaApi:
    """
    Unofficial client for the API used by Lynda.com's Android app.
    This is used as a replacement to scraping the website which regularly changes.
    This should be much more stable and quicker.
    Reverse engineered using mitmproxy and decompiling the Android app.

    Author: David Moodie
    """

    API_HOST = "https://api-1.lynda.com"
    APP_KEY = "DC325E0DF73140E48DE3C0406B911B04"
    USER_AGENT = "Dalvik/2.1.0 (Linux; U; Android 6.0; Android SDK built for x86 Build/MASTER)"
    HASH_KEY = "DC325E0DF73140E48DE3C0406B911B04F0CFC5A8D3BB4F82878947BD6D0BC3A1"

    def __init__(self, cookiejar=None):
        # Initialise the session
        self._s = requests.Session()
        self._user_cached = None
        self.logged_in = False

        if cookiejar:
            self._s.cookies = cookiejar

            # Check if the given cookies log the user in
            user = self.user()
            if user:
                self.logged_in = True

    def user(self):
        # If we have a user object saved from previous query, return that straight away
        # if self._user_cached:
        #     return self._user_cached

        params = {
            "filter.includes": "ID,Flags,RoleFlag,Products,FirstName,LastName"
        }
        resp = self._get('/user', params).json()
        if 'Status' in resp and resp['Status'] == 'error':
            return None

        user = User(
            resp['ID'],
            resp['FirstName'],
            resp['LastName']
        )
        self._user_cached = user
        return user

    def login_normal(self, username, password):
        endpoint = '/session/login'
        data = {
            'type': 'Password',
            'password.pass': password,
            'password.user': username
        }
        resp = self._post(endpoint, data).json()
        if 'Status' in resp and resp['Status'] == 'ok':
            self.logged_in = True
            return True
        else:
            return False

    def login_ip(self):
        """Logs a user based on their IP. Used for IP-based site licenses.
        TODO: TEST!"""
        endpoint = '/session/login'
        data = {
            'type': 'IP'
        }
        resp = self._post(endpoint, data).json()
        if 'Status' in resp and resp['Status'] == 'ok':
            self.logged_in = True
            return True
        else:
            return False

    def set_token(self, token):
        """Sets the cookie session token directly instead of using a proper login method."""
        self._s.cookies['token'] = token

    def course_search(self, query):
        params = {
            "filter.includes": "Courses.ID,Courses.Title,Courses.DateReleasedUtc,Courses.HasAccess,Courses.PlaylistIds,Courses.DurationInSeconds,Courses.Description",
            "productType": 2,
            "order": "ByRelevancy",
            "start": 0,
            "limit": 20,
            "q": query
        }
        resp = self._get('/search', params).json()
        return self._parse_courses_response(resp['Courses'])

    def user_courses(self):
        endpoint = '/user/history'
        params = {
            "filter.includes": "ID,Title,DateReleasedUtc,PlaylistIds,CourseTimes,DurationInSeconds,AccessDateUtc,Authors,LastVideoViewedId,Flags,Description"
        }
        resp = self._get(endpoint, params).json()
        return self._parse_courses_response(resp)

    def course_thumb(self, course_id):
        width = 480
        endpoint = '/course/{0}/thumb'.format(course_id)
        params = {
            "w": width,
            "h": int(math.ceil(width / 1.7777778)),
            "colorHex": "000000"
        }
        resp = self._get(endpoint, params)
        return resp.url

    def course_chapters(self, course_id):
        endpoint = '/course/{0}'.format(course_id)
        params = {
            "filter.includes": "ID,Chapters.ID,Chapters.Title"
        }
        resp = self._get(endpoint, params).json()
        chapters = []
        for chapter in resp['Chapters']:
            chapters.append(Chapter(
                chapter['ID'],
                chapter['Title']
            ))
        return chapters

    # TODO: Consolidate with course_chapters call (cache initial response?)
    def chapter_videos(self, course_id, chapter_id):
        endpoint = '/course/{0}'.format(course_id)
        params = {
            "filter.includes": "ID,Title,Description,DurationInSeconds,CourseTimes,Flags,DateOriginallyReleasedUtc,DateReleasedUtc,DateUpdatedUtc,URLs,LastVideoViewedId,Chapters.ID,Chapters.Title,Chapters.Videos.HasAccess,Chapters.Videos.ID,Chapters.Videos.DurationInSeconds,Chapters.Videos.CourseID,Chapters.Videos.Title,Chapters.Videos.FileName,Chapters.Videos.Watched,Authors.ID,Authors.Fullname,Authors.Bio,Authors.Thumbnails,Tags.ID,Tags.Type,Tags.Name,SuggestedCourses,PlaylistIds,OwnsCourse,Bookmarked"
        }
        resp = self._get(endpoint, params).json()
        for chapter in resp['Chapters']:
            if chapter['ID'] == chapter_id:
                videos = []
                for video in chapter['Videos']:
                    videos.append(Video(
                        video['ID'],
                        video['Title'],
                        None,
                        video['HasAccess']
                    ))
                return videos

    def video_url(self, course_id, video_id):
        endpoint = '/course/{0}/{1}'.format(course_id, video_id)
        params = {
            "streamType": 1,
            "filter.excludes": "Stream,Formats"
        }
        resp = self._get(endpoint, params).json()
        streams = resp['PrioritizedStreams']['0']
        for stream in streams:
            if stream['StreamType'] == 1 and stream['IsMultiBitrate'] is True:
                return stream['URL']
        raise ValueError('Could not get a stream URL from response')

    def log_video(self, video_id):
        endpoint = '/log/video/{0}'.format(video_id)
        resp = self._get(endpoint).json()
        if resp['Status'] == 'Error':
            raise ValueError('Failed to log video play event')

    def get_cookies(self):
        return self._s.cookies

    def _make_hash(self, url):
        return hashlib.md5(self.HASH_KEY + url + str(int(time.time()))).hexdigest()

    def _headers(self, url):
        return {
            "appkey": self.APP_KEY,
            "timestamp": str(int(time.time())),
            "hash": self._make_hash(url),
            "Accept-Language": "en",
            "User-Agent": self.USER_AGENT
        }

    def _get(self, endpoint, params=None, new_headers=[]):
        url = self.API_HOST + endpoint
        if params:
            urlencoded_params = urllib.urlencode(params)
            url_with_params = url + "?" + urlencoded_params
            headers = self._headers(url_with_params)
        else:
            headers = self._headers(url)
        # Override/add headers
        for h in new_headers:
            headers[h] = new_headers[h]

        resp = self._s.get(url, params=params, headers=headers)
        return resp

    def _post(self, endpoint, data, new_headers=[]):
        url = self.API_HOST + endpoint

        headers = self._headers(url)
        # Override/add headers
        for h in new_headers:
            headers[h] = new_headers[h]

        resp = self._s.post(url, data=data, headers=headers)
        return resp

    # def _batch(self, batches, new_headers=[]):
    #     """Performs a batch request. 'batches' param is a list of tuples like
    #     (endpoint, params) where params is a params dict"""
    #
    #     batch_objects = []
    #     for endpoint, params in batches:
    #         url = endpoint
    #         urlencoded_params = urllib.urlencode(params)
    #         url_with_params = url + "?" + urlencoded_params
    #         batch_objects.append({'url': url_with_params})
    #
    #     endpoint = '/batch2'
    #     data = {
    #         'data': json.dumps({'batch': batch_objects})
    #     }
    #
    #     resp = self._post(endpoint, data, new_headers)
    #     print(resp.text)
    #     return resp

    def _parse_courses_response(self, courses_response):
        """Parses a list of dicts (originally json) into DTO objects"""
        courses = []
        c = 0
        for course in courses_response:
            # Only get the first few course images as requests are slow
            if c < 5:
                thumb_url = self.course_thumb(course['ID'])
            else:
                thumb_url = None
            courses.append(Course(
                course['Title'],
                course['ID'],
                thumb_url,
                course['Description']
            ))
            c += 1
        return courses


class Course:
    def __init__(self, title, course_id, thumb_url, description):
        self.title = title
        self.course_id = course_id
        self.thumb_url = thumb_url
        self.description = description


class Chapter:
    def __init__(self, chapter_id, title):
        self.chapter_id = chapter_id
        self.title = title


class Video:
    def __init__(self, video_id, title, thumb_url, has_access):
        self.video_id = video_id
        self.title = title
        self.thumb_url = thumb_url
        self.has_access = has_access


class User:
    def __init__(self, user_id, first_name, last_name):
        self.user_id = user_id
        self.first_name = first_name
        self.last_name = last_name
        self.name = self.first_name + ' ' + self.last_name
