"""
Custom Authenticator to use Auth0 OAuth with JupyterHub

Derived using the Github and Google OAuthenticator implementations as examples.

The following environment variables may be used for configuration:

    AUTH0_SUBDOMAIN - The subdomain for your Auth0 account
    OAUTH_CLIENT_ID - Your client id
    OAUTH_CLIENT_SECRET - Your client secret
    OAUTH_CALLBACK_URI - Your callback handler URI

Additionally, if you are concerned about your secrets being exposed by
an env dump(I know I am!) you can set the client_secret, client_id and
oauth_callback_url directly on the config for Auth0OAuthenticator.

One instance of this could be adding the following to your jupyterhub_config.py :

  c.Auth0OAuthenticator.client_id = 'YOUR_CLIENT_ID'
  c.Auth0OAuthenticator.client_secret = 'YOUR_CLIENT_SECRET'
  c.Auth0OAuthenticator.oauth_callback_url = 'YOUR_CALLBACK_URL'

If you are using the environment variable config, all you should need to
do is define them in the environment then add the following line to 
jupyterhub_config.py :

  c.JupyterHub.authenticator_class = 'oauthenticator.auth0.Auth0OAuthenticator'

"""
from markupsafe import Markup
import json
import os
import requests

from tornado.auth import OAuth2Mixin
from tornado import gen, web

from tornado.httpclient import HTTPRequest, AsyncHTTPClient

from jupyterhub.auth import LocalAuthenticator

from .oauth2 import OAuthLoginHandler, OAuthenticator

from traitlets import Unicode

AUTH0_SUBDOMAIN = os.getenv('AUTH0_SUBDOMAIN')

class Auth0Mixin(OAuth2Mixin):
    _OAUTH_AUTHORIZE_URL = "https://%s.auth0.com/authorize" % AUTH0_SUBDOMAIN
    _OAUTH_ACCESS_TOKEN_URL = "https://%s.auth0.com/oauth/token" % AUTH0_SUBDOMAIN


class Auth0LoginHandler(OAuthLoginHandler, Auth0Mixin):
    def get(self):
        buttonScript = requests.get(self.authenticator.webtask_base_url + '?webtask_no_cache=1&client_id=' + self.authenticator.client_id)
        buttonCss = requests.get(self.authenticator.webtask_base_url + '?webtask_no_cache=1&css=true')

        self.authenticator.custom_html = Markup("""
          <style>
          """ + buttonCss.text + """
          </style>

          <div id='frmAuth0Login'></div>

          <script>
            var justNow = new Date (new Date().getTime() - 1);
            document.cookie = "jupyter-hub-tokens=; expires=" + justNow.toGMTString();

            var oauth = {
              client_id : '""" + self.authenticator.client_id + """',
              domain : '""" + AUTH0_SUBDOMAIN + '.auth0.com' + """',
              callbackURL : '""" + self.authenticator.oauth_callback_url + """'
            };

          """ + buttonScript.text + "</script>")
        super(Auth0LoginHandler, self).get()

class Auth0OAuthenticator(OAuthenticator):

    webtask_base_url = Unicode(config=True)

    login_service = "Auth0"

    login_handler = Auth0LoginHandler
    
    @gen.coroutine
    def authenticate(self, handler, data=None):
        code = handler.get_argument("code", False)
        if not code:
            raise web.HTTPError(400, "oauth callback made without a token")
        # TODO: Configure the curl_httpclient for tornado
        http_client = AsyncHTTPClient()

        params = {
            'grant_type': 'authorization_code',
            'client_id': self.client_id,
            'client_secret': self.client_secret,
            'code':code,
            'redirect_uri': self.oauth_callback_url
        }
        url = "https://%s.auth0.com/oauth/token" % AUTH0_SUBDOMAIN

        req = HTTPRequest(url,
                          method="POST",
                          headers={"Content-Type": "application/json"},
                          body=json.dumps(params)
                          )
        
        resp = yield http_client.fetch(req)
        resp_json = json.loads(resp.body.decode('utf8', 'replace'))
        
        access_token = resp_json['access_token']
        
        # Determine who the logged in user is
        headers={"Accept": "application/json",
                 "User-Agent": "JupyterHub",
                 "Authorization": "Bearer {}".format(access_token)
        }
        req = HTTPRequest("https://%s.auth0.com/userinfo" % AUTH0_SUBDOMAIN,
                          method="GET",
                          headers=headers
                          )
        resp = yield http_client.fetch(req)
        resp_json = json.loads(resp.body.decode('utf8', 'replace'))

        return resp_json["email"]


class LocalAuth0OAuthenticator(LocalAuthenticator, Auth0OAuthenticator):

    """A version that mixes in local system user creation"""
    pass

