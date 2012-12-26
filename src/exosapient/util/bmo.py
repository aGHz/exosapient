from xo.scraping import ParseError, RequestError, Page, FormPage, DummyPage, Session
from exosapient.model.local import bmo_number, bmo_pass, bmo_security,\
                                   bmo_personal_phrase, bmo_personal_image


def run():
    bmo = BMO()
    return bmo


class BMO(object):
    session = None

    def __init__(self, login=True, cookie_jar=None):
        self.session = Session(jar=cookie_jar)
        if login:
            self.login()

    def login(self):
        self.bmohome = BMOHomePage(session=self.session)
        self.card = self.bmohome.next()
        self.security = self.card.next(number=bmo_number)
        self.password = self.security.next(answer=bmo_security[self.security.question])
        if not self.password.personal_phrase == bmo_personal_phrase:
            raise SecurityError('Personal phrase does not match: "{0}"'.format(self.password.personal_phrase))
        if not self.password.personal_image == bmo_personal_image:
            raise SecurityError('Personal image does not match: "{0}"'.format(self.password.personal_image))
        self.overview = self.password.next(password=bmo_pass)

    def __ansistr__(self):
        out = []
        return "\n".join(out)


class BMOHomePage(Page):
    def __init__(self, url='http://www.bmo.com/home', *args, **kwargs):
        return super(BMOHomePage, self).__init__(url=url, *args, **kwargs)

    @Page.parser
    def parse(self):
        link = self.soup.find(lambda e: e.name == 'a' and e.string == 'Online Banking')
        if not link:
            raise ParseError('"Online Banking" link not found')

        self.link = link['href']
        return self

    @Page.self_referrer
    def next(self):
        return CardNumberPage(url=self.link, session=self.session)

class CardNumberPage(FormPage):
    @Page.parser
    def parse(self):
        form = self.soup.find('form', id='regSignInForm')
        if not form:
            raise ParseError('form#regSignInForm not found')

        self.form = form
        self.parse_form()
        if 'FBC_Number' not in self.form_data:
            raise ParseError('input[name="FBC_Number"] not found')
        return self

    @Page.self_referrer
    def next(self, number):
        self.form_data.update({'FBC_Number': number, 'pm_fp': self._fingerprints()})
        action = self.form_action + '?product=5' # according to JS submitTo()
        page = SecurityQuestion(url=action, data=self.form_data, session=self.session, _parse=False)
        try:
            page.parse()
        except ParseError:
            # It seems BMO somehow honors the 'remember me' setting for the scraper,
            # so the page could actually be directly a PasswordPage
            page = PasswordPage(url=page.url, body=page.body, session=self.session)
            return DummyPage(page, question='Security question skipped')
        else:
            return page

    def _fingerprints(self):
        # this replicates the function post_fingerprints in pm_fp.js
        data = {
            'version': '1',
            # fingerprint_browser
            'pm_fpua': 'mozilla/5.0 (macintosh; intel mac os x 10_7_4) applewebkit/537.11 (khtml, like gecko) chrome/23.0.1271.64 safari/537.11|5.0 (Macintosh; Intel Mac OS X 10_7_4) AppleWebKit/537.11 (KHTML, like Gecko) Chrome/23.0.1271.64 Safari/537.11|MacIntel|en-US',
            # fingerprint_display
            'pm_fpsc': '24|1920|1200|1117',
            # fingerprint_software
            'pm_fpsw': '',
            # fingerprint_timezone
            'pm_fptz': '-5',
            # fingerprint_language
            'pm_fpln': 'lang=en-US|syslang=|userlang=',
            # fingerprint_java
            'pm_fpjv': '1',
            # fingerprint_cookie
            'pm_fpco': '1',
            }
        return 'version%3D1%26pm%5Ffpua%3Dmozilla%2F5%2E0%20%28macintosh%3B%20intel%20mac%20os%20x%2010%5F7%5F4%29%20applewebkit/537%2E11%20%28khtml%2C%20like%20gecko%29%20chrome/23%2E0%2E1271%2E64%20safari/537%2E11%7C5%2E0%20%28Macintosh%3B%20Intel%20Mac%20OS%20X%2010%5F7%5F4%29%20AppleWebKit/537%2E11%20%28KHTML%2C%20like%20Gecko%29%20Chrome/23%2E0%2E1271%2E64%20Safari/537%2E11%7CMacIntel%7Cen%2DUS%26pm%5Ffpsc%3D24%7C1920%7C1200%7C1117%26pm%5Ffpsw%3D%26pm%5Ffptz%3D%2D5%26pm%5Ffpln%3Dlang%3Den%2DUS%7Csyslang%3D%7Cuserlang%3D%26pm%5Ffpjv%3D1%26pm%5Ffpco%3D1'


class SecurityQuestion(FormPage):
    @Page.parser
    def parse(self):
        form = self.soup.find('form', id='regChallengeQuestion')
        if not form:
            raise ParseError('form[id="regChallengeQuestion"] not found')

        self.form = form
        self.parse_form()
        if 'answer' not in self.form_data:
            raise ParseError('input[name="answer"] not found')

        try:
            q = form.select('label#lblregSecurityQuestion')[0]
        except Exception:
            raise ParseError('label#lblregSecurityQuestion not found')
        self.question = q.text

        return self

    @Page.self_referrer
    def next(self, answer):
        self.form_data.update({'answer': answer})
        return PasswordPage(url=self.form_action, data=self.form_data, session=self.session)


class PasswordPage(FormPage):
    @Page.parser
    def parse(self):
        form = self.soup.find('form', id='regSignInForm')
        if form is None:
            raise ParseError('form[id="regSignInForm"] not found')

        self.form = form
        self.parse_form()
        if 'FBC_Password' not in self.form_data:
            raise ParseError('input[name="FBC_Password"] not found')

        self.personal_phrase = None
        self.personal_image = None
        for dt in form.find_all('dt'):
            if dt.text.strip() == 'Personal Phrase:':
                try:
                    self.personal_phrase = dt.find_next_sibling('dd').text.strip()
                except Exception:
                    raise ParseError('dt[content="Personal Phrase:"] + dd not found')
            elif dt.text.strip() == 'Personal Image:':
                try:
                    self.personal_image = dt.find_next_sibling('dd').find('img')['alt']
                except Exception:
                    raise ParseError('dt[content="Personal Image:"] + dd > img not found')

        return self

    @Page.self_referrer
    def next(self, password):
        self.form_data.update({'FBC_Password': password})
        return OverviewPage(url=self.form_action, data=self.form_data, session=self.session)


class OverviewPage(Page):
    @Page.parser
    def parse(self):
        return self


class SecurityError(Exception):
    pass
